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
