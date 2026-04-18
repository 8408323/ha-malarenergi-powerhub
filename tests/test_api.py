"""Tests for api.py — uses aioresponses to mock HTTP, no real network calls."""
import re
import struct
from datetime import datetime, timezone

import aiohttp
import pytest
from aioresponses import aioresponses

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.malarenergi_powerhub.api import (
    BASE_URL,
    POWER_BASE_URL,
    AuthError,
    FacilityAttributes,
    FacilityControl,
    FcrStatus,
    Invitation,
    InvitationCreated,
    MonthlyInsights,
    NotificationSettings,
    PhaseTelemetry,
    PowerApiClient,
    PowerDiagnostics,
    PowerHubApiClient,
    PowerHubDevice,
    PowerTelemetry,
    _decode_hourly_energy_proto,
    _decode_phase_telemetry_proto,
    _decode_telemetry_proto,
    bankid_start,
    bankid_poll,
)

FAKE_TOKEN = "eyJhbGciOiJIUzI1NiJ9.fake.token"
FACILITY_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# PowerHubApiClient
# ---------------------------------------------------------------------------

class TestGetFacilities:
    async def test_returns_parsed_facility(self):
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(
                    f"{BASE_URL}/account/facility",
                    payload=[{
                        "facilityid": FACILITY_ID,
                        "street": "EXAMPLE STREET",
                        "houseNumber": 11,
                        "entrance": None,
                        "city": "EXAMPLE CITY",
                        "postcode": "00000",
                        "countrycode": "SE",
                        "latitude": 0.0,
                        "longitude": 0.0,
                        "annualPrediction": 0,
                        "fuseType": "",
                        "utilityid": "fb71138f",
                        "utilityName": "735999",
                        "metadata": {
                            "netId": "VLS",
                            "region": "SE3",
                            "meterId": "00000000000000000000",
                        },
                        "facilityOwnerName": "Test User",
                        "facilityOwnerId": "00000000-0000-0000-0000-000000000002",
                        "attributes": {},
                    }],
                )
                facilities = await client.get_facilities()

        assert len(facilities) == 1
        f = facilities[0]
        assert f.facility_id == FACILITY_ID
        assert f.street == "EXAMPLE STREET"
        assert f.house_number == 11
        assert f.region == "SE3"
        assert f.meter_id == "00000000000000000000"

    async def test_deduplicates_facility_id(self):
        """API sometimes returns same facility twice — should deduplicate."""
        entry = {
            "facilityid": FACILITY_ID,
            "street": "X",
            "houseNumber": 1,
            "entrance": None,
            "city": "Y",
            "postcode": "",
            "countrycode": "SE",
            "latitude": 0,
            "longitude": 0,
            "annualPrediction": 0,
            "fuseType": "",
            "utilityid": "",
            "utilityName": "",
            "metadata": {"region": "SE3", "meterId": "123"},
            "facilityOwnerName": "",
            "facilityOwnerId": "",
            "attributes": {},
        }
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(f"{BASE_URL}/account/facility", payload=[entry, entry])
                facilities = await client.get_facilities()
        assert len(facilities) == 1

    async def test_raises_auth_error_on_401(self):
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(f"{BASE_URL}/account/facility", status=401)
                with pytest.raises(AuthError):
                    await client.get_facilities()


TS = 1776204000000  # a fixed timestamp for tests


class TestGetTodayConsumption:
    async def test_returns_meter_data_points(self):
        url = (
            f"{BASE_URL}/facility/{FACILITY_ID}/facility_consumption_meter"
            f"?interval=DAY&type=START&timestamp={TS}"
        )
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(url, payload={
                    "facilityid": FACILITY_ID,
                    "start": TS, "end": TS + 86400000, "count": 3,
                    "data": [
                        {"timestamp": TS,         "value": 100.0},
                        {"timestamp": TS + 900000, "value": 150.0},
                        {"timestamp": TS + 1800000,"value": 200.0},
                    ],
                })
                points = await client.get_today_consumption(FACILITY_ID, TS)

        assert len(points) == 3
        assert points[0].value_wh == 100.0
        assert points[1].timestamp_ms == TS + 900000

    async def test_returns_empty_list_when_no_data(self):
        url = (
            f"{BASE_URL}/facility/{FACILITY_ID}/facility_consumption_meter"
            f"?interval=DAY&type=START&timestamp=0"
        )
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(url, payload={
                    "facilityid": FACILITY_ID, "data": [],
                    "count": 0, "start": 0, "end": 0,
                })
                points = await client.get_today_consumption(FACILITY_ID, 0)
        assert points == []


class TestGetSpotPrice:
    async def test_returns_price_points(self):
        url = (
            f"{BASE_URL}/facility/{FACILITY_ID}/nordpool_spot_price"
            f"?interval=DAY&type=START&timestamp={TS}"
        )
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(url, payload={
                    "facilityid": FACILITY_ID,
                    "data": [
                        {"timestamp": TS,          "value": 77.88},
                        {"timestamp": TS + 900000, "value": 80.12},
                    ],
                    "count": 2, "start": 0, "end": 0,
                })
                points = await client.get_spot_price_today(FACILITY_ID, TS)
        assert len(points) == 2
        assert points[0]["value"] == pytest.approx(77.88)


# ---------------------------------------------------------------------------
# BankID flow
# ---------------------------------------------------------------------------

class TestBankIdStart:
    async def test_returns_transaction_id(self):
        async with aiohttp.ClientSession() as session:
            with aioresponses() as m:
                m.get(
                    f"{BASE_URL}/bankid/auth",
                    payload={
                        "transactionId": "00000000-0000-0000-0000-00000000bbb1",
                        "autoStartToken": "00000000-0000-0000-0000-00000000bbb2",
                    },
                )
                txid, token = await bankid_start(session)
        assert txid == "00000000-0000-0000-0000-00000000bbb1"
        assert token == "00000000-0000-0000-0000-00000000bbb2"


class TestBankIdPoll:
    async def test_yields_pending_then_complete(self):
        txid = "00000000-0000-0000-0000-00000000bbb1"
        async with aiohttp.ClientSession() as session:
            with aioresponses() as m:
                # First poll: pending with QR
                m.get(
                    f"{BASE_URL}/bankid/check/{txid}",
                    payload={
                        "status": "pending",
                        "qrCode": "bankid.abc.1.hash",
                        "token": None,
                        "hintCode": "outstandingTransaction",
                    },
                )
                # Second poll: complete with token
                m.get(
                    f"{BASE_URL}/bankid/check/{txid}",
                    payload={
                        "status": "complete",
                        "qrCode": None,
                        "token": FAKE_TOKEN,
                        "hintCode": None,
                    },
                )

                results = []
                async for status, qr, token in bankid_poll(session, txid):
                    results.append((status, qr, token))

        assert results[0] == ("pending", "bankid.abc.1.hash", None)
        assert results[1] == ("complete", None, FAKE_TOKEN)

    async def test_yields_failed_on_error(self):
        txid = "bad-txid"
        async with aiohttp.ClientSession() as session:
            with aioresponses() as m:
                m.get(
                    f"{BASE_URL}/bankid/check/{txid}",
                    payload={"status": "failed", "qrCode": None, "token": None,
                             "hintCode": "startFailed"},
                )
                results = []
                async for status, qr, token in bankid_poll(session, txid):
                    results.append((status, qr, token))

        assert results[0][0] == "failed"
        assert results[0][2] is None


class TestGetMonthConsumption:
    async def test_returns_meter_response_with_correct_fields(self):
        url = (
            f"{BASE_URL}/facility/{FACILITY_ID}/facility_consumption_meter"
            f"?interval=MONTH&type=START&timestamp={TS}"
        )
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(url, payload={
                    "facilityid": FACILITY_ID,
                    "min": 6.0, "max": 231.0, "avg": 109.25,
                    "start": TS, "end": TS + 86400000 * 30,
                    "count": 2,
                    "data": [
                        {"timestamp": TS, "value": 100.0},
                        {"timestamp": TS + 86400000, "value": 231.0},
                    ],
                })
                result = await client.get_month_consumption(FACILITY_ID, TS)

        assert result.facility_id == FACILITY_ID
        assert result.start_ms == TS
        assert result.end_ms == TS + 86400000 * 30
        assert result.value_min == 6.0
        assert result.value_max == 231.0
        assert result.avg == 109.25
        assert len(result.data) == 2
        assert result.data[1].value_wh == 231.0


class TestGetInvitations:
    async def test_exposes_code_for_unclaimed_and_null_for_claimed(self):
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(
                    f"{BASE_URL}/account/invitation",
                    payload=[
                        {
                            "id": "unclaimed-id",
                            "code": "ELX4CULD",
                            "claimed": None,
                            "expires": "2026-04-18T07:58:30+0200",
                            "created": "2026-04-15T07:58:30+0200",
                            "accessedFacilities": [],
                        },
                        {
                            "id": "claimed-id",
                            "code": None,
                            "claimed": "2026-04-12T22:17:35+0200",
                            "expires": "2026-04-15T22:17:07+0200",
                            "created": "2026-04-12T22:17:07+0200",
                            "accessedFacilities": [],
                        },
                    ],
                )
                result = await client.get_invitations()

        assert len(result) == 2
        assert all(isinstance(inv, Invitation) for inv in result)
        assert result[0].code == "ELX4CULD"
        assert result[0].claimed is False
        assert result[1].code is None
        assert result[1].claimed is True


class TestCreateInvitation:
    async def test_posts_and_returns_result(self):
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.post(
                    f"{BASE_URL}/account/invitation",
                    payload={
                        "status": 0,
                        "success": True,
                        "data": {
                            "id": "7adfa928-4081-4c3e-a27d-55c3833fd383",
                            "code": "ELX4CULD",
                            "created": "2026-04-15T07:58:30+0200",
                            "expires": "2026-04-18T07:58:30+0200",
                            "accessedFacilities": [],
                        },
                        "dataType": "JSON",
                    },
                )
                result = await client.create_invitation(FACILITY_ID)

        assert isinstance(result, InvitationCreated)
        assert result.invitation_id == "7adfa928-4081-4c3e-a27d-55c3833fd383"
        assert result.code == "ELX4CULD"
        assert result.expires == "2026-04-18T07:58:30+0200"

    async def test_raises_auth_error_on_401(self):
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.post(f"{BASE_URL}/account/invitation", status=401)
                with pytest.raises(AuthError):
                    await client.create_invitation(FACILITY_ID)


class TestDeleteInvitation:
    INVITATION_ID = "7adfa928-4081-4c3e-a27d-55c3833fd383"

    async def test_deletes_without_error(self):
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.delete(
                    f"{BASE_URL}/account/invitation/{self.INVITATION_ID}",
                    status=204,
                )
                await client.delete_invitation(self.INVITATION_ID)  # must not raise

    async def test_raises_auth_error_on_401(self):
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.delete(
                    f"{BASE_URL}/account/invitation/{self.INVITATION_ID}",
                    status=401,
                )
                with pytest.raises(AuthError):
                    await client.delete_invitation(self.INVITATION_ID)


class TestGetMonthProduction:
    async def test_returns_meter_response_for_production(self):
        url = (
            f"{BASE_URL}/facility/{FACILITY_ID}/facility_production_meter"
            f"?interval=MONTH&type=START&timestamp={TS}"
        )
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(url, payload={
                    "facilityid": FACILITY_ID,
                    "min": 0.0, "max": 55.0, "avg": 22.5,
                    "start": TS, "end": TS + 86400000 * 30,
                    "count": 2,
                    "data": [
                        {"timestamp": TS, "value": 0.0},
                        {"timestamp": TS + 86400000, "value": 55.0},
                    ],
                })
                result = await client.get_month_production(FACILITY_ID, TS)

        assert result.facility_id == FACILITY_ID
        assert result.value_min == 0.0
        assert result.value_max == 55.0
        assert len(result.data) == 2


class TestGetYearConsumption:
    async def test_returns_meter_response_for_year(self):
        year_ts = 1735686000000  # 2025-01-01T00:00:00+01:00
        url = (
            f"{BASE_URL}/facility/{FACILITY_ID}/facility_consumption_meter"
            f"?interval=YEAR&type=START&timestamp={year_ts}"
        )
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(url, payload={
                    "facilityid": FACILITY_ID,
                    "min": 800.0, "max": 3200.0, "avg": 1800.0,
                    "start": year_ts, "end": year_ts + 86400000 * 365,
                    "count": 12,
                    "data": [{"timestamp": year_ts + i * 2_592_000_000, "value": 1000.0 + i * 100}
                             for i in range(12)],
                })
                result = await client.get_year_consumption(FACILITY_ID, year_ts)

        assert result.facility_id == FACILITY_ID
        assert result.count == 12
        assert result.value_min == pytest.approx(800.0)
        assert result.value_max == pytest.approx(3200.0)
        assert len(result.data) == 12


class TestGetMonthlyInsights:
    def _full_payload(self):
        return {
            "facilityId": FACILITY_ID,
            "monthTimestamp": TS,
            "priceComparison": {
                "yourAveragePrice": 0.85,
                "monthlyAveragePrice": 0.92,
                "trend": "BELOW",
            },
            "yearComparison": {
                "currentYearValue": 1200.0,
                "previousYearValue": 1100.0,
                "percentageChange": 9.09,
                "trend": "UP",
            },
            "powerPeaks": {
                "dailyPeaks": [
                    {"timestamp": TS, "value": 5.5},
                    {"timestamp": TS + 86400000, "value": 4.2},
                ],
            },
            "baseload": {
                "baseload": 0.8,
                "baseloadKwh": 580.0,
                "baseloadPercentage": 48.3,
                "totalKwh": 1200.0,
            },
            "offPeakScore": {
                "offPeakScore": 72.0,
                "rating": "GOOD",
            },
        }

    async def test_returns_full_insights(self):
        url = (
            f"{BASE_URL}/facility/{FACILITY_ID}/insights/monthly/{TS}"
            f"?meterType=consumption&region=SE3"
        )
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(url, payload=self._full_payload())
                result = await client.get_monthly_insights(FACILITY_ID, TS)

        assert isinstance(result, MonthlyInsights)
        assert result.facility_id == FACILITY_ID
        assert result.month_timestamp_ms == TS
        assert result.your_average_price == pytest.approx(0.85)
        assert result.monthly_average_price == pytest.approx(0.92)
        assert result.price_trend == "BELOW"
        assert result.current_year_value == pytest.approx(1200.0)
        assert result.previous_year_value == pytest.approx(1100.0)
        assert result.year_percentage_change == pytest.approx(9.09)
        assert result.year_trend == "UP"
        assert len(result.daily_peaks) == 2
        assert result.baseload_kw == pytest.approx(0.8)
        assert result.baseload_kwh == pytest.approx(580.0)
        assert result.baseload_percentage == pytest.approx(48.3)
        assert result.total_kwh == pytest.approx(1200.0)
        assert result.off_peak_score == pytest.approx(72.0)
        assert result.off_peak_rating == "GOOD"

    async def test_handles_null_optional_sections(self):
        """priceComparison and offPeakScore can be null (e.g. production meters)."""
        url = (
            f"{BASE_URL}/facility/{FACILITY_ID}/insights/monthly/{TS}"
            f"?meterType=consumption&region=SE3"
        )
        payload = self._full_payload()
        payload["priceComparison"] = None
        payload["offPeakScore"] = None
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(url, payload=payload)
                result = await client.get_monthly_insights(FACILITY_ID, TS)

        assert result.your_average_price is None
        assert result.monthly_average_price is None
        assert result.price_trend is None
        assert result.off_peak_score is None
        assert result.off_peak_rating is None
        # non-nullable fields still populated
        assert result.current_year_value == pytest.approx(1200.0)


# ---------------------------------------------------------------------------
# Protobuf decoders
# ---------------------------------------------------------------------------

# Protobuf tag bytes used in the wire helpers below.
# Tags are encoded as (field_number << 3) | wire_type.
# Wire type 0 = varint, wire type 2 = length-delimited, wire type 5 = 32-bit.
_TAG_FIELD1_VARINT  = b'\x08'   # field 1, varint
_TAG_FIELD2_FIXED32 = b'\x15'   # field 2, 32-bit (float)
_TAG_FIELD3_FIXED32 = b'\x1d'   # field 3, 32-bit
_TAG_FIELD4_FIXED32 = b'\x25'   # field 4, 32-bit
_TAG_FIELD5_FIXED32 = b'\x2d'   # field 5, 32-bit
_TAG_FIELD6_FIXED32 = b'\x35'   # field 6, 32-bit
_TAG_FIELD7_FIXED32 = b'\x3d'   # field 7, 32-bit
_TAG_FIELD8_FIXED32 = b'\x45'   # field 8, 32-bit
_TAG_FIELD9_FIXED32 = b'\x4d'   # field 9, 32-bit
_TAG_FIELD10_FIXED32 = b'\x55'  # field 10, 32-bit
_TAG_RECORD_LEN_DELIM = b'\x0a' # field 1, length-delimited (outer record tag)


def _make_telemetry_bytes(ts_s: int, import_kw: float, export_kw: float) -> bytes:
    """Build a minimal _decode_telemetry_proto wire payload for one record."""
    sub = _TAG_FIELD1_VARINT                                 # field 1 varint tag
    v = ts_s
    while True:
        b = v & 0x7F
        v >>= 7
        sub += bytes([b | 0x80]) if v else bytes([b])
        if not v:
            break
    sub += _TAG_FIELD6_FIXED32 + struct.pack('<f', import_kw)   # field 6 fixed32
    sub += _TAG_FIELD7_FIXED32 + struct.pack('<f', export_kw)   # field 7 fixed32
    return _TAG_RECORD_LEN_DELIM + bytes([len(sub)]) + sub


def _make_phase_telemetry_bytes(
    ts_s: int,
    l1_a: float, l2_a: float, l3_a: float,
    p_l1_imp: float, p_l1_exp: float,
    p_l2_imp: float, p_l2_exp: float,
    p_l3_imp: float, p_l3_exp: float,
) -> bytes:
    """Build a minimal _decode_phase_telemetry_proto payload for one record."""
    sub = _TAG_FIELD1_VARINT
    v = ts_s
    while True:
        b = v & 0x7F
        v >>= 7
        sub += bytes([b | 0x80]) if v else bytes([b])
        if not v:
            break
    sub += _TAG_FIELD2_FIXED32  + struct.pack('<f', l1_a)       # current_l1_a
    sub += _TAG_FIELD3_FIXED32  + struct.pack('<f', l2_a)       # current_l2_a
    sub += _TAG_FIELD4_FIXED32  + struct.pack('<f', l3_a)       # current_l3_a
    sub += _TAG_FIELD5_FIXED32  + struct.pack('<f', p_l1_imp)   # power_l1_import
    sub += _TAG_FIELD6_FIXED32  + struct.pack('<f', p_l1_exp)   # power_l1_export
    sub += _TAG_FIELD7_FIXED32  + struct.pack('<f', p_l2_imp)   # power_l2_import
    sub += _TAG_FIELD8_FIXED32  + struct.pack('<f', p_l2_exp)   # power_l2_export
    sub += _TAG_FIELD9_FIXED32  + struct.pack('<f', p_l3_imp)   # power_l3_import
    sub += _TAG_FIELD10_FIXED32 + struct.pack('<f', p_l3_exp)   # power_l3_export
    return _TAG_RECORD_LEN_DELIM + bytes([len(sub)]) + sub


def _make_hourly_energy_bytes(
    bucket_ts_s: int, win_start_ts_s: int, win_end_ts_s: int,
    sample_count: int, import_wh: float, export_wh: float,
) -> bytes:
    """Build a minimal _decode_hourly_energy_proto payload for one record."""
    def _varint(v: int) -> bytes:
        out = b''
        while True:
            b = v & 0x7F
            v >>= 7
            out += bytes([b | 0x80]) if v else bytes([b])
            if not v:
                break
        return out

    def _ts_submsg(ts_s: int) -> bytes:
        return _TAG_FIELD1_VARINT + _varint(ts_s)

    bucket_raw   = _ts_submsg(bucket_ts_s)
    win_start_raw = _ts_submsg(win_start_ts_s)
    win_end_raw  = _ts_submsg(win_end_ts_s)

    # Tags for the outer record fields (field_num << 3 | wire_type)
    _tag_f1_ld = b'\x0a'   # field 1, length-delimited (bucket ts submsg)
    _tag_f2_vi = b'\x10'   # field 2, varint (sample_count)
    _tag_f3_ld = b'\x1a'   # field 3, length-delimited (win_start submsg)
    _tag_f4_ld = b'\x22'   # field 4, length-delimited (win_end submsg)

    record = b''
    record += _tag_f1_ld + bytes([len(bucket_raw)])    + bucket_raw     # bucket ts
    record += _tag_f2_vi + _varint(sample_count)                        # sample count
    record += _tag_f3_ld + bytes([len(win_start_raw)]) + win_start_raw  # window start
    record += _tag_f4_ld + bytes([len(win_end_raw)])   + win_end_raw    # window end
    record += _TAG_FIELD7_FIXED32  + struct.pack('<f', import_wh)       # energy_import_wh
    record += _TAG_FIELD10_FIXED32 + struct.pack('<f', export_wh)       # energy_export_wh

    return _TAG_RECORD_LEN_DELIM + bytes([len(record)]) + record


class TestDecodeTelemProto:
    def test_single_record(self):
        raw = _make_telemetry_bytes(1000, import_kw=1.5, export_kw=0.5)
        results = _decode_telemetry_proto(raw)
        assert len(results) == 1
        r = results[0]
        assert r.timestamp.timestamp() == pytest.approx(1000)
        assert r.timestamp.tzinfo is not None
        assert r.power_import_kw == pytest.approx(1.5, abs=1e-4)
        assert r.power_export_kw == pytest.approx(0.5, abs=1e-4)

    def test_two_records(self):
        raw = (
            _make_telemetry_bytes(1000, 1.5, 0.5)
            + _make_telemetry_bytes(1060, 2.0, 0.0)
        )
        results = _decode_telemetry_proto(raw)
        assert len(results) == 2
        assert results[0].power_import_kw == pytest.approx(1.5, abs=1e-4)
        assert results[1].power_import_kw == pytest.approx(2.0, abs=1e-4)

    def test_empty_bytes_returns_empty_list(self):
        assert _decode_telemetry_proto(b'') == []

    def test_record_without_leading_tag(self):
        """Records without the leading 0x0a byte are also valid."""
        raw = _make_telemetry_bytes(1000, 1.5, 0.5)
        # strip the leading 0x0a byte
        raw_no_tag = raw[1:]
        results = _decode_telemetry_proto(raw_no_tag)
        assert len(results) == 1
        assert results[0].power_import_kw == pytest.approx(1.5, abs=1e-4)


class TestDecodePhaseTelemetryProto:
    def test_single_record_all_fields(self):
        raw = _make_phase_telemetry_bytes(
            ts_s=2000,
            l1_a=10.5, l2_a=11.0, l3_a=9.5,
            p_l1_imp=2.4, p_l1_exp=0.1,
            p_l2_imp=2.5, p_l2_exp=0.0,
            p_l3_imp=2.2, p_l3_exp=0.0,
        )
        results = _decode_phase_telemetry_proto(raw)
        assert len(results) == 1
        r = results[0]
        assert r.timestamp.timestamp() == pytest.approx(2000)
        assert r.current_l1_a == pytest.approx(10.5, abs=1e-3)
        assert r.current_l2_a == pytest.approx(11.0, abs=1e-3)
        assert r.current_l3_a == pytest.approx(9.5, abs=1e-3)
        assert r.power_l1_import_kw == pytest.approx(2.4, abs=1e-3)
        assert r.power_l1_export_kw == pytest.approx(0.1, abs=1e-3)
        assert r.power_l2_import_kw == pytest.approx(2.5, abs=1e-3)
        assert r.power_l2_export_kw == pytest.approx(0.0, abs=1e-3)
        assert r.power_l3_import_kw == pytest.approx(2.2, abs=1e-3)
        assert r.power_l3_export_kw == pytest.approx(0.0, abs=1e-3)

    def test_zero_current_values(self):
        """All-zero values decode without error."""
        raw = _make_phase_telemetry_bytes(1000, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        results = _decode_phase_telemetry_proto(raw)
        assert len(results) == 1
        r = results[0]
        assert r.current_l1_a == pytest.approx(0.0)
        assert r.power_l1_import_kw == pytest.approx(0.0)

    def test_empty_bytes_returns_empty_list(self):
        assert _decode_phase_telemetry_proto(b'') == []


class TestDecodeHourlyEnergyProto:
    def test_single_bucket(self):
        raw = _make_hourly_energy_bytes(
            bucket_ts_s=1000, win_start_ts_s=1000, win_end_ts_s=3600,
            sample_count=4, import_wh=500.0, export_wh=100.0,
        )
        results = _decode_hourly_energy_proto(raw)
        assert len(results) == 1
        r = results[0]
        assert r.bucket_start.timestamp() == pytest.approx(1000)
        assert r.window_start.timestamp() == pytest.approx(1000)
        assert r.window_end.timestamp() == pytest.approx(3600)
        assert r.sample_count == 4
        assert r.energy_import_wh == pytest.approx(500.0, abs=0.1)
        assert r.energy_export_wh == pytest.approx(100.0, abs=0.1)

    def test_two_buckets(self):
        raw = (
            _make_hourly_energy_bytes(1000, 1000, 3600, 4, 500.0, 0.0)
            + _make_hourly_energy_bytes(3600, 3600, 7200, 4, 480.0, 20.0)
        )
        results = _decode_hourly_energy_proto(raw)
        assert len(results) == 2
        assert results[0].energy_import_wh == pytest.approx(500.0, abs=0.1)
        assert results[1].energy_import_wh == pytest.approx(480.0, abs=0.1)

    def test_empty_bytes_returns_empty_list(self):
        assert _decode_hourly_energy_proto(b'') == []


class TestGetDevice:
    async def test_dict_response(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(
                    f"{POWER_BASE_URL}/devices/powerhub",
                    payload={
                        "deviceId": "dev-001",
                        "model": "PowerHub v1",
                        "facilityId": FACILITY_ID,
                        "macAddress": "AA:BB:CC:DD:EE:FF",
                    },
                )
                device = await client.get_device()
        assert isinstance(device, PowerHubDevice)
        assert device.device_id == "dev-001"
        assert device.facility_id == FACILITY_ID

    async def test_list_response(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(
                    f"{POWER_BASE_URL}/devices/powerhub",
                    payload=[{
                        "deviceId": "dev-002",
                        "model": "PowerHub v2",
                        "facilityId": FACILITY_ID,
                        "macAddress": "11:22:33:44:55:66",
                    }],
                )
                device = await client.get_device()
        assert device.device_id == "dev-002"

    async def test_empty_list_raises_value_error(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(f"{POWER_BASE_URL}/devices/powerhub", payload=[])
                with pytest.raises(ValueError, match="No PowerHub device"):
                    await client.get_device()

    async def test_raises_auth_error_on_401(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(f"{POWER_BASE_URL}/devices/powerhub", status=401)
                with pytest.raises(AuthError):
                    await client.get_device()


# Matches /telemetry/<uuid>?... (no trailing /aggregated/)
_TELEMETRY_URL_RE = re.compile(
    rf"{re.escape(POWER_BASE_URL)}/data-extraction/powerhub/telemetry/[^/?]+\?"
)
_AGGREGATED_ENERGY_URL_RE = re.compile(
    rf"{re.escape(POWER_BASE_URL)}/data-extraction/powerhub/telemetry/[^/]+/aggregated/energy\?"
)


class TestGetCurrentPower:
    async def test_returns_latest_sample(self):
        raw = (
            _make_telemetry_bytes(1000, 1.5, 0.0)
            + _make_telemetry_bytes(2000, 2.0, 0.0)  # latest
            + _make_telemetry_bytes(1500, 1.7, 0.0)
        )
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(_TELEMETRY_URL_RE, body=raw, content_type="application/octet-stream")
                sample = await client.get_current_power(FACILITY_ID)
        assert sample is not None
        assert isinstance(sample, PowerTelemetry)
        assert sample.timestamp.timestamp() == pytest.approx(2000)
        assert sample.power_import_kw == pytest.approx(2.0, abs=1e-3)

    async def test_returns_none_when_empty(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(_TELEMETRY_URL_RE, body=b"", content_type="application/octet-stream")
                sample = await client.get_current_power(FACILITY_ID)
        assert sample is None

    async def test_raises_auth_error_on_401(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(_TELEMETRY_URL_RE, status=401)
                with pytest.raises(AuthError):
                    await client.get_current_power(FACILITY_ID)


class TestGetCurrentPowerPhases:
    async def test_returns_latest_phase_sample(self):
        raw = (
            _make_phase_telemetry_bytes(1000, 5.0, 5.0, 5.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0)
            + _make_phase_telemetry_bytes(2000, 10.5, 11.0, 9.5, 2.4, 0.1, 2.5, 0.0, 2.2, 0.0)
        )
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(_TELEMETRY_URL_RE, body=raw, content_type="application/octet-stream")
                sample = await client.get_current_power_phases(FACILITY_ID)
        assert sample is not None
        assert isinstance(sample, PhaseTelemetry)
        assert sample.timestamp.timestamp() == pytest.approx(2000)
        assert sample.current_l1_a == pytest.approx(10.5, abs=1e-3)
        assert sample.power_l2_import_kw == pytest.approx(2.5, abs=1e-3)

    async def test_returns_none_when_empty(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(_TELEMETRY_URL_RE, body=b"", content_type="application/octet-stream")
                sample = await client.get_current_power_phases(FACILITY_ID)
        assert sample is None


class TestGetHourlyEnergy:
    async def test_parses_aggregated_response(self):
        raw = (
            _make_hourly_energy_bytes(1000, 1000, 3600, 4, 500.0, 0.0)
            + _make_hourly_energy_bytes(3600, 3600, 7200, 4, 480.0, 20.0)
        )
        start = datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 4, 18, 2, 0, tzinfo=timezone.utc)
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(_AGGREGATED_ENERGY_URL_RE, body=raw, content_type="application/octet-stream")
                result = await client.get_hourly_energy(FACILITY_ID, start, end)
        assert len(result) == 2
        assert result[0].energy_import_wh == pytest.approx(500.0, abs=0.1)
        assert result[1].energy_export_wh == pytest.approx(20.0, abs=0.1)


class TestGetDiagnostics:
    async def test_parses_fields(self):
        payload = {
            "uptimeS": 123456,
            "wifiRssiDbm": -62,
            "deviceInfoSwVersion": "1.2.3",
            "hanPortState": "ACTIVE",
        }
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(
                    f"{POWER_BASE_URL}/data-extraction/powerhub/diagnostics/{FACILITY_ID}",
                    payload=payload,
                )
                diag = await client.get_diagnostics(FACILITY_ID)
        assert isinstance(diag, PowerDiagnostics)
        assert diag.uptime_s == 123456
        assert diag.wifi_rssi_dbm == -62
        assert diag.sw_version == "1.2.3"
        assert diag.han_port_state == "ACTIVE"

    async def test_missing_sw_version_becomes_empty_string(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(
                    f"{POWER_BASE_URL}/data-extraction/powerhub/diagnostics/{FACILITY_ID}",
                    payload={"uptimeS": 0, "wifiRssiDbm": 0, "deviceInfoSwVersion": None, "hanPortState": ""},
                )
                diag = await client.get_diagnostics(FACILITY_ID)
        assert diag.sw_version == ""


class TestGetFacilityControl:
    async def test_parses_fields(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(
                    f"{POWER_BASE_URL}/activation/facilitycontrol/{FACILITY_ID}",
                    payload={
                        "fuseLimitA": 25.0,
                        "powerLimitKw": 11.0,
                        "actionOnFuseLimit": "NOTIFY",
                        "actionOnPowerLimit": "CUT",
                    },
                )
                ctrl = await client.get_facility_control(FACILITY_ID)
        assert isinstance(ctrl, FacilityControl)
        assert ctrl.fuse_limit_a == 25.0
        assert ctrl.power_limit_kw == 11.0
        assert ctrl.action_on_fuse_limit == "NOTIFY"
        assert ctrl.action_on_power_limit == "CUT"


class TestUpdateFacilityControl:
    async def test_posts_full_body(self):
        ctrl = FacilityControl(
            fuse_limit_a=16.0,
            power_limit_kw=10.0,
            action_on_fuse_limit="NOTIFY",
            action_on_power_limit="NOTIFY",
        )
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.post(
                    f"{POWER_BASE_URL}/activation/facilitycontrol",
                    status=200,
                    payload={},
                )
                await client.update_facility_control(FACILITY_ID, ctrl)

    async def test_raises_auth_error_on_401(self):
        ctrl = FacilityControl(16.0, 10.0, "NOTIFY", "NOTIFY")
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.post(f"{POWER_BASE_URL}/activation/facilitycontrol", status=401)
                with pytest.raises(AuthError):
                    await client.update_facility_control(FACILITY_ID, ctrl)


class TestGetFcrStatus:
    async def test_parses_enabled_true(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(
                    f"{POWER_BASE_URL}/activation/fcr/facility-enablements/{FACILITY_ID}",
                    payload={"fcrdDownEnabled": True},
                )
                status = await client.get_fcr_status(FACILITY_ID)
        assert isinstance(status, FcrStatus)
        assert status.fcrd_down_enabled is True

    async def test_parses_missing_field_as_false(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(
                    f"{POWER_BASE_URL}/activation/fcr/facility-enablements/{FACILITY_ID}",
                    payload={},
                )
                status = await client.get_fcr_status(FACILITY_ID)
        assert status.fcrd_down_enabled is False


_NOTIFY_PAYLOAD = {
    "notifyTotalPower": True,
    "notifyPhaseLoad": False,
    "notifyControlDisabledExceededPhase": True,
    "notifyControlDisabledExceededPower": False,
    "notifyControlEnabledExceededPhase": True,
    "notifyControlEnabledExceededPower": False,
}


class TestGetNotificationSettings:
    async def test_parses_all_flags(self):
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.get(
                    f"{POWER_BASE_URL}/customer/settings/{FACILITY_ID}/notifications",
                    payload=_NOTIFY_PAYLOAD,
                )
                settings = await client.get_notification_settings(FACILITY_ID)
        assert isinstance(settings, NotificationSettings)
        assert settings.notify_total_power is True
        assert settings.notify_phase_load is False
        assert settings.notify_control_disabled_exceeded_phase is True
        assert settings.notify_control_enabled_exceeded_power is False


class TestUpdateNotificationSettings:
    async def test_patches_and_returns_updated(self):
        new = NotificationSettings(
            notify_total_power=True,
            notify_phase_load=True,
            notify_control_disabled_exceeded_phase=True,
            notify_control_disabled_exceeded_power=True,
            notify_control_enabled_exceeded_phase=True,
            notify_control_enabled_exceeded_power=True,
        )
        echo = {**_NOTIFY_PAYLOAD, "notifyPhaseLoad": True, "notifyControlDisabledExceededPower": True, "notifyControlEnabledExceededPower": True}
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.patch(
                    f"{POWER_BASE_URL}/customer/settings/{FACILITY_ID}/notifications",
                    status=200,
                    payload=echo,
                )
                result = await client.update_notification_settings(FACILITY_ID, new)
        assert result.notify_phase_load is True
        assert result.notify_control_enabled_exceeded_power is True

    async def test_raises_auth_error_on_401(self):
        new = NotificationSettings(False, False, False, False, False, False)
        async with aiohttp.ClientSession() as session:
            client = PowerApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.patch(
                    f"{POWER_BASE_URL}/customer/settings/{FACILITY_ID}/notifications",
                    status=401,
                )
                with pytest.raises(AuthError):
                    await client.update_notification_settings(FACILITY_ID, new)


_DEFAULT_ATTRS_BODY = {
    "heatingType": "DISTRICT_HEATING",
    "fuseSize": "A25",
    "occupants": 2,
    "area": 80,
    "type": "APARTMENT",
    "evType": "NONE",
    "battery": False,
    "solar": False,
}


def _make_attrs() -> "FacilityAttributes":
    from custom_components.malarenergi_powerhub.api import FacilityAttributes
    return FacilityAttributes(
        heating_type="DISTRICT_HEATING",
        fuse_size=25,
        occupants=2,
        area=80,
        facility_type="APARTMENT",
        ev_type="NONE",
        has_battery=False,
        has_solar=False,
    )


class TestUpdateFacilityAttributes:
    """Covers the PowerHubApiClient._put helper via update_facility_attributes."""

    async def test_put_updates_and_parses_response(self):
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.put(
                    f"{BASE_URL}/facility/{FACILITY_ID}/attributes",
                    status=200,
                    payload=_DEFAULT_ATTRS_BODY,
                )
                result = await client.update_facility_attributes(FACILITY_ID, _make_attrs())
        assert result.fuse_size == 25
        assert result.occupants == 2
        assert result.facility_type == "APARTMENT"
        assert result.has_battery is False

    async def test_put_tolerates_invalid_fuse_size_in_response(self):
        """If the response's fuseSize can't be parsed, fall back to the input value."""
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.put(
                    f"{BASE_URL}/facility/{FACILITY_ID}/attributes",
                    status=200,
                    payload={**_DEFAULT_ATTRS_BODY, "fuseSize": "GARBAGE"},
                )
                result = await client.update_facility_attributes(FACILITY_ID, _make_attrs())
        assert result.fuse_size == 25

    async def test_put_raises_auth_error_on_401(self):
        async with aiohttp.ClientSession() as session:
            client = PowerHubApiClient(session, FAKE_TOKEN)
            with aioresponses() as m:
                m.put(
                    f"{BASE_URL}/facility/{FACILITY_ID}/attributes",
                    status=401,
                )
                with pytest.raises(AuthError):
                    await client.update_facility_attributes(FACILITY_ID, _make_attrs())

