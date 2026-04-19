"""Tests for the config flow's reauth completion path.

The full HA config-flow harness would require pytest-homeassistant-custom-component;
these tests instead target the branching logic inside _async_finish directly by
mocking the surrounding HA runtime. We cover the behaviour that matters for users:
on successful BankID reauth, the existing entry's token is updated, the entry is
reloaded, and the flow aborts with reason="reauth_successful".
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries

from custom_components.malarenergi_powerhub.api import FacilityInfo
from custom_components.malarenergi_powerhub.config_flow import PowerHubConfigFlow
from custom_components.malarenergi_powerhub.const import CONF_FACILITY_ID, CONF_TOKEN

FACILITY = FacilityInfo(
    facility_id="facility-uuid-123",
    street="Storgatan",
    house_number=1,
    city="Västerås",
    meter_id="meter-1",
    region="SE3",
    customer_id="cust-1",
)
NEW_TOKEN = "eyJnew.token.value"
OLD_ENTRY_ID = "existing-entry-id"


def _make_flow(source: str, entry_id: str | None = None) -> PowerHubConfigFlow:
    """Build a PowerHubConfigFlow with enough runtime scaffolding to exercise
    _async_finish without HA's real flow manager."""
    flow = PowerHubConfigFlow()
    # ConfigFlow.source is read from self.context["source"]
    flow.context = {"source": source}
    if entry_id is not None:
        flow.context["entry_id"] = entry_id
    flow.hass = MagicMock()
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()
    return flow


class TestAsyncFinishReauth:
    async def test_reauth_updates_existing_entry_and_aborts_successfully(self) -> None:
        flow = _make_flow(config_entries.SOURCE_REAUTH, entry_id=OLD_ENTRY_ID)

        existing_entry = MagicMock()
        existing_entry.entry_id = OLD_ENTRY_ID
        existing_entry.data = {
            CONF_TOKEN: "old-token",
            CONF_FACILITY_ID: FACILITY.facility_id,
        }
        flow.hass.config_entries.async_get_entry.return_value = existing_entry

        fake_client = MagicMock()
        fake_client.get_facilities = AsyncMock(return_value=[FACILITY])

        with patch(
            "custom_components.malarenergi_powerhub.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.api.PowerHubApiClient",
            return_value=fake_client,
        ):
            result = await flow._async_finish(NEW_TOKEN)

        # Token was written back onto the existing entry, preserving other data keys
        flow.hass.config_entries.async_update_entry.assert_called_once()
        _, kwargs = flow.hass.config_entries.async_update_entry.call_args
        assert kwargs["data"][CONF_TOKEN] == NEW_TOKEN
        assert kwargs["data"][CONF_FACILITY_ID] == FACILITY.facility_id

        # Entry was reloaded so the coordinator picks up the new token
        flow.hass.config_entries.async_reload.assert_awaited_once_with(OLD_ENTRY_ID)

        # Flow aborts with the reason HA uses to dismiss the re-auth notification
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"

    async def test_reauth_without_entry_id_falls_through_to_create(self) -> None:
        """If HA didn't stash entry_id in context, we shouldn't silently no-op —
        fall through to the create-entry path so the user still gets an entry."""
        flow = _make_flow(config_entries.SOURCE_REAUTH, entry_id=None)
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()

        fake_client = MagicMock()
        fake_client.get_facilities = AsyncMock(return_value=[FACILITY])

        with patch(
            "custom_components.malarenergi_powerhub.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.api.PowerHubApiClient",
            return_value=fake_client,
        ):
            result = await flow._async_finish(NEW_TOKEN)

        # Did not touch the existing-entry helpers
        flow.hass.config_entries.async_update_entry.assert_not_called()
        flow.hass.config_entries.async_reload.assert_not_awaited()

        # Went down the create-entry path instead
        assert result["type"] == "create_entry"
        assert result["data"][CONF_TOKEN] == NEW_TOKEN


class TestAsyncFinishUserFlow:
    async def test_user_flow_creates_new_entry_with_token(self) -> None:
        flow = _make_flow(config_entries.SOURCE_USER)
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()

        fake_client = MagicMock()
        fake_client.get_facilities = AsyncMock(return_value=[FACILITY])

        with patch(
            "custom_components.malarenergi_powerhub.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.api.PowerHubApiClient",
            return_value=fake_client,
        ):
            result = await flow._async_finish(NEW_TOKEN)

        flow.async_set_unique_id.assert_awaited_once_with(FACILITY.facility_id)
        flow._abort_if_unique_id_configured.assert_called_once_with(
            updates={CONF_TOKEN: NEW_TOKEN}
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "Storgatan 1"
        assert result["data"][CONF_TOKEN] == NEW_TOKEN
        assert result["data"][CONF_FACILITY_ID] == FACILITY.facility_id
