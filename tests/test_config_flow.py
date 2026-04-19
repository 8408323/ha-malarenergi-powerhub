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
        existing_entry.unique_id = FACILITY.facility_id
        existing_entry.data = {
            CONF_TOKEN: "old-token",
            CONF_FACILITY_ID: FACILITY.facility_id,
        }
        flow.hass.config_entries.async_get_entry.return_value = existing_entry

        # BankID returns two facilities in a different order than on first setup
        other_facility = FacilityInfo(
            facility_id="other-uuid-999",
            street="Lillgatan",
            house_number=5,
            city="Västerås",
            meter_id="meter-2",
            region="SE3",
            customer_id="cust-1",
        )
        fake_client = MagicMock()
        fake_client.get_facilities = AsyncMock(return_value=[other_facility, FACILITY])

        with patch(
            "custom_components.malarenergi_powerhub.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.api.PowerHubApiClient",
            return_value=fake_client,
        ):
            result = await flow._async_finish(NEW_TOKEN)

        # Token was written back; facility_id preserved (NOT overwritten with
        # facilities[0] which would have retargeted the entry to other_facility)
        flow.hass.config_entries.async_update_entry.assert_called_once()
        _, kwargs = flow.hass.config_entries.async_update_entry.call_args
        assert kwargs["data"][CONF_TOKEN] == NEW_TOKEN
        assert kwargs["data"][CONF_FACILITY_ID] == FACILITY.facility_id

        flow.hass.config_entries.async_reload.assert_awaited_once_with(OLD_ENTRY_ID)
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"

    async def test_reauth_without_entry_id_locates_by_unique_id(self) -> None:
        """HA sometimes omits entry_id from the reauth context. Fall back to
        matching an existing entry by unique_id against the returned facilities."""
        flow = _make_flow(config_entries.SOURCE_REAUTH, entry_id=None)

        existing_entry = MagicMock()
        existing_entry.entry_id = OLD_ENTRY_ID
        existing_entry.unique_id = FACILITY.facility_id
        existing_entry.data = {
            CONF_TOKEN: "old-token",
            CONF_FACILITY_ID: FACILITY.facility_id,
        }
        flow.hass.config_entries.async_get_entry.return_value = None
        flow.hass.config_entries.async_entries = MagicMock(return_value=[existing_entry])

        fake_client = MagicMock()
        fake_client.get_facilities = AsyncMock(return_value=[FACILITY])

        with patch(
            "custom_components.malarenergi_powerhub.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.api.PowerHubApiClient",
            return_value=fake_client,
        ):
            result = await flow._async_finish(NEW_TOKEN)

        flow.hass.config_entries.async_update_entry.assert_called_once()
        flow.hass.config_entries.async_reload.assert_awaited_once_with(OLD_ENTRY_ID)
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"

    async def test_reauth_with_no_identifiable_entry_aborts_as_unresolved(
        self,
    ) -> None:
        """If entry_id is missing and no existing entry's unique_id matches
        any returned facility, we must abort — not fall through to create."""
        flow = _make_flow(config_entries.SOURCE_REAUTH, entry_id=None)
        flow.hass.config_entries.async_get_entry.return_value = None
        flow.hass.config_entries.async_entries = MagicMock(return_value=[])

        fake_client = MagicMock()
        fake_client.get_facilities = AsyncMock(return_value=[FACILITY])

        with patch(
            "custom_components.malarenergi_powerhub.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.api.PowerHubApiClient",
            return_value=fake_client,
        ):
            result = await flow._async_finish(NEW_TOKEN)

        flow.hass.config_entries.async_update_entry.assert_not_called()
        flow.hass.config_entries.async_reload.assert_not_awaited()
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_unresolved"

    async def test_reauth_with_ambiguous_unique_id_match_aborts(self) -> None:
        """If the unique_id fallback finds more than one candidate entry
        (future multi-facility case), we must abort rather than silently
        pick the first one and update the wrong entry."""
        flow = _make_flow(config_entries.SOURCE_REAUTH, entry_id=None)
        flow.hass.config_entries.async_get_entry.return_value = None

        entry_a = MagicMock()
        entry_a.entry_id = "entry-a"
        entry_a.unique_id = FACILITY.facility_id
        entry_a.data = {CONF_FACILITY_ID: FACILITY.facility_id}
        entry_b = MagicMock()
        entry_b.entry_id = "entry-b"
        entry_b.unique_id = "other-uuid-999"
        entry_b.data = {CONF_FACILITY_ID: "other-uuid-999"}
        flow.hass.config_entries.async_entries = MagicMock(
            return_value=[entry_a, entry_b]
        )

        other_facility = FacilityInfo(
            facility_id="other-uuid-999",
            street="Lillgatan",
            house_number=5,
            city="Västerås",
            meter_id="meter-2",
            region="SE3",
            customer_id="cust-1",
        )
        fake_client = MagicMock()
        fake_client.get_facilities = AsyncMock(return_value=[FACILITY, other_facility])

        with patch(
            "custom_components.malarenergi_powerhub.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.api.PowerHubApiClient",
            return_value=fake_client,
        ):
            result = await flow._async_finish(NEW_TOKEN)

        flow.hass.config_entries.async_update_entry.assert_not_called()
        flow.hass.config_entries.async_reload.assert_not_awaited()
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_ambiguous"

    async def test_reauth_with_different_bankid_account_aborts_with_wrong_account(
        self,
    ) -> None:
        """If the user signs in with BankID for a different account, the
        returned facilities will not include the entry's facility_id — we must
        abort instead of silently retargeting the entry."""
        flow = _make_flow(config_entries.SOURCE_REAUTH, entry_id=OLD_ENTRY_ID)

        existing_entry = MagicMock()
        existing_entry.entry_id = OLD_ENTRY_ID
        existing_entry.unique_id = FACILITY.facility_id
        existing_entry.data = {
            CONF_TOKEN: "old-token",
            CONF_FACILITY_ID: FACILITY.facility_id,
        }
        flow.hass.config_entries.async_get_entry.return_value = existing_entry

        stranger_facility = FacilityInfo(
            facility_id="stranger-uuid-888",
            street="Annangatan",
            house_number=2,
            city="Eskilstuna",
            meter_id="meter-x",
            region="SE3",
            customer_id="cust-2",
        )
        fake_client = MagicMock()
        fake_client.get_facilities = AsyncMock(return_value=[stranger_facility])

        with patch(
            "custom_components.malarenergi_powerhub.config_flow.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.api.PowerHubApiClient",
            return_value=fake_client,
        ):
            result = await flow._async_finish(NEW_TOKEN)

        flow.hass.config_entries.async_update_entry.assert_not_called()
        flow.hass.config_entries.async_reload.assert_not_awaited()
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_wrong_account"


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
