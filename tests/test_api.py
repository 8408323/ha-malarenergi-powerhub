"""Tests for api.py — uses aioresponses to mock HTTP, no real network calls."""
import pytest
import aiohttp
from aioresponses import aioresponses

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.malarenergi_powerhub.api import (
    BASE_URL,
    AuthError,
    InvitationCreated,
    MonthlyInsights,
    PowerHubApiClient,
    bankid_start,
    bankid_poll,
)

FAKE_TOKEN = "eyJhbGciOiJIUzI1NiJ9.fake.token"
FACILITY_ID = "102ee2c4-5c0a-4b92-b28f-8faa0c320def"


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
                        "street": "ÖSTER RÅBY",
                        "houseNumber": 11,
                        "entrance": None,
                        "city": "VÄSTERÅS",
                        "postcode": "00000",
                        "countrycode": "SE",
                        "latitude": 59.6099,
                        "longitude": 16.54481,
                        "annualPrediction": 0,
                        "fuseType": "",
                        "utilityid": "fb71138f",
                        "utilityName": "735999",
                        "metadata": {
                            "netId": "VLS",
                            "region": "SE3",
                            "meterId": "735999137910044285",
                        },
                        "facilityOwnerName": "Test User",
                        "facilityOwnerId": "65bfe7c9-ac53-4c16-8325-fb237d422501",
                        "attributes": {},
                    }],
                )
                facilities = await client.get_facilities()

        assert len(facilities) == 1
        f = facilities[0]
        assert f.facility_id == FACILITY_ID
        assert f.street == "ÖSTER RÅBY"
        assert f.house_number == 11
        assert f.region == "SE3"
        assert f.meter_id == "735999137910044285"

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
                        "transactionId": "52defb78-2abc-4c41-8b5b-d43d7b06f0b6",
                        "autoStartToken": "6d1579fa-00bd-440a-a27a-8674d685d047",
                    },
                )
                txid, token = await bankid_start(session)
        assert txid == "52defb78-2abc-4c41-8b5b-d43d7b06f0b6"
        assert token == "6d1579fa-00bd-440a-a27a-8674d685d047"


class TestBankIdPoll:
    async def test_yields_pending_then_complete(self):
        txid = "52defb78-2abc-4c41-8b5b-d43d7b06f0b6"
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

import struct

from custom_components.malarenergi_powerhub.api import (
    _decode_telemetry_proto,
    _decode_phase_telemetry_proto,
    _decode_hourly_energy_proto,
    PowerHubDevice,
    PowerApiClient,
    POWER_BASE_URL,
)

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

