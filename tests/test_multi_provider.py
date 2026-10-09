"""Tests for energy-company (provider) support and the link to the core Bitvis device."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses
from homeassistant import config_entries

from custom_components.malarenergi_powerhub import _async_link_hub
from custom_components.malarenergi_powerhub.api import (
    POWER_BASE_URL,
    PowerApiClient,
    PowerHubApiClient,
    bankid_poll,
    bankid_start,
    flow_url,
)
from custom_components.malarenergi_powerhub.config_flow import PowerHubConfigFlow
from custom_components.malarenergi_powerhub.const import CONF_FACILITY_ID, CONF_PROVIDER, CONF_TOKEN, DOMAIN
from custom_components.malarenergi_powerhub.coordinator import device_info, provider_of

FACILITY = "fac-1"
MAC = "94:54:C5:AA:BB:CC"


def _entry(**data) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "eid-1"
    entry.title = "Street 1"
    entry.data = {CONF_TOKEN: "tok", CONF_FACILITY_ID: FACILITY, **data}
    return entry


# ── api ───────────────────────────────────────────────────────────────────────


def test_flow_url_per_provider() -> None:
    assert flow_url("booenergi") == "https://booenergi.prod.flow.bitv.is/powerapi/v1"


async def test_client_uses_provider_backend() -> None:
    async with aiohttp.ClientSession() as session:
        client = PowerHubApiClient(session, "tok", "booenergi")
        with aioresponses() as m:
            m.get(f"{flow_url('booenergi')}/account/profile", payload={})
            await client._get("/account/profile")


async def test_bankid_uses_provider_backend() -> None:
    async with aiohttp.ClientSession() as session:
        with aioresponses() as m:
            m.get(f"{flow_url('norrtaljeenergi')}/bankid/auth", payload={"transactionId": "t", "autoStartToken": "a"})
            m.get(f"{flow_url('norrtaljeenergi')}/bankid/check/t", payload={"status": "complete", "token": "jwt"})
            assert await bankid_start(session, "norrtaljeenergi") == ("t", "a")
            assert [x async for x in bankid_poll(session, "t", "norrtaljeenergi")] == [("complete", None, "jwt")]


async def _device(payload, facility_id=FACILITY):
    async with aiohttp.ClientSession() as session:
        with aioresponses() as m:
            m.get(f"{POWER_BASE_URL}/devices/powerhub", payload=payload)
            return await PowerApiClient(session, "tok").get_device(facility_id)


async def test_get_device_picks_the_facilitys_hub() -> None:
    hubs = [{"facilityId": "other", "macAddress": "1"}, {"facilityId": FACILITY, "macAddress": "2"}]
    assert (await _device(hubs)).mac_address == "2"


async def test_get_device_rejects_a_hub_at_another_facility() -> None:
    for hubs in ({"facilityId": "other"}, [{"facilityId": "other"}], [{"facilityId": "a"}, {"facilityId": "b"}]):
        with pytest.raises(ValueError, match="No PowerHub device for facility"):
            await _device(hubs)


async def test_get_device_without_facility_takes_the_first() -> None:
    assert (await _device([{"facilityId": "a", "macAddress": "1"}], facility_id=None)).mac_address == "1"


# ── coordinator helpers ───────────────────────────────────────────────────────


def test_old_entries_are_malarenergi() -> None:
    assert provider_of(_entry()) == "malarenergi"
    assert device_info(_entry())["manufacturer"] == "Bitvis / Mälarenergi"


def test_device_info_names_the_provider() -> None:
    assert device_info(_entry(**{CONF_PROVIDER: "booenergi"}))["manufacturer"] == "Bitvis / Boo Energi"
    assert device_info(_entry(**{CONF_PROVIDER: "newco"}))["manufacturer"] == "Bitvis / newco"


# ── config flow ───────────────────────────────────────────────────────────────


def _flow() -> PowerHubConfigFlow:
    flow = PowerHubConfigFlow()
    flow.context = {"source": config_entries.SOURCE_USER}
    flow.hass = MagicMock()
    return flow


async def test_user_step_shows_provider_form() -> None:
    result = await _flow().async_step_user()
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_user_step_accepts_listed_and_typed_provider() -> None:
    for typed, slug in (("booenergi", "booenergi"), (" NewCo-2 ", "newco-2")):
        flow = _flow()
        flow.async_step_bankid = AsyncMock(return_value={"step_id": "bankid_qr"})
        await flow.async_step_user({CONF_PROVIDER: typed})
        assert flow._provider == slug
        flow.async_step_bankid.assert_awaited_once()


async def test_user_step_rejects_non_hostname_provider() -> None:
    flow = _flow()
    result = await flow.async_step_user({CONF_PROVIDER: "evil.com/x"})
    assert result["errors"] == {CONF_PROVIDER: "invalid_provider"}
    assert flow._provider == "malarenergi"


async def test_reauth_keeps_the_entrys_provider() -> None:
    flow = _flow()
    flow.async_step_bankid = AsyncMock()
    await flow.async_step_reauth({CONF_PROVIDER: "booenergi"})
    assert flow._provider == "booenergi"


async def test_created_entry_stores_provider() -> None:
    flow = _flow()
    flow._provider = "booenergi"
    flow.hass.config_entries.async_entries.return_value = []
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    facility = SimpleNamespace(facility_id=FACILITY, street="Street", house_number=1)
    client = MagicMock(get_facilities=AsyncMock(return_value=[facility]))
    with (
        patch("custom_components.malarenergi_powerhub.config_flow.async_get_clientsession"),
        patch("custom_components.malarenergi_powerhub.api.PowerHubApiClient", return_value=client) as cls,
    ):
        result = await flow._async_finish("jwt")
    assert cls.call_args.args[2] == "booenergi"
    assert result["data"][CONF_PROVIDER] == "booenergi"


async def test_import_defaults_provider() -> None:
    flow = _flow()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    data = {CONF_TOKEN: "t", CONF_FACILITY_ID: FACILITY, "street": "S", "house_number": 1}
    assert (await flow.async_step_import(data))["data"][CONF_PROVIDER] == "malarenergi"


# ── device link with the core bitvis integration ──────────────────────────────


async def _link(*, mac=MAC, error=None, owner=None):
    entry = _entry()
    dev_reg = MagicMock()
    dev_reg.async_get_device.return_value = owner
    get_device = AsyncMock(side_effect=error, return_value=SimpleNamespace(mac_address=mac))
    with (
        patch("custom_components.malarenergi_powerhub.async_get_clientsession"),
        patch("custom_components.malarenergi_powerhub.PowerApiClient", return_value=MagicMock(get_device=get_device)),
        patch("custom_components.malarenergi_powerhub.dr.async_get", return_value=dev_reg),
    ):
        await _async_link_hub(MagicMock(), entry)
    get_device.assert_awaited_once_with(FACILITY)
    return dev_reg


async def test_link_adds_mac_to_our_device() -> None:
    kwargs = (await _link()).async_get_or_create.call_args.kwargs
    assert kwargs["connections"] == {("mac", "94:54:c5:aa:bb:cc")}
    assert kwargs["identifiers"] == {(DOMAIN, "eid-1")}
    assert kwargs["config_entry_id"] == "eid-1"


async def test_link_leaves_a_device_owned_by_another_integration_alone() -> None:
    dev_reg = await _link(owner=SimpleNamespace(config_entries={"unifi-entry"}))
    dev_reg.async_get_or_create.assert_not_called()


async def test_link_is_idempotent_on_our_own_device() -> None:
    dev_reg = await _link(owner=SimpleNamespace(config_entries={"eid-1"}))
    dev_reg.async_get_or_create.assert_called_once()


async def test_link_skipped_without_mac_or_on_error() -> None:
    for kwargs in ({"mac": ""}, {"error": ValueError("down")}):
        (await _link(**kwargs)).async_get_or_create.assert_not_called()
