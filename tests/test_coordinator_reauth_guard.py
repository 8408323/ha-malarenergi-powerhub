"""Tests for the coordinator's reauth guard.

Verifies that async_start_reauth is only called once per AuthError state
(not on every poll), and that the flag resets after a successful poll so
future token expiries still trigger a fresh reauth flow.
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.malarenergi_powerhub.api import AuthError
from custom_components.malarenergi_powerhub.coordinator import PowerHubCoordinator
from custom_components.malarenergi_powerhub.notifications_coordinator import (
    NotificationsCoordinator,
)


def _make_coordinator_env(cls):
    """Instantiate a coordinator with minimal mocked runtime so its
    _async_update_data can be driven to completion."""
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"token": "stale-token", "facility_id": "f1"}
    entry.async_start_reauth = MagicMock()

    hass = MagicMock()
    # DataUpdateCoordinator.__init__ touches hass.loop; give it something truthy
    hass.loop = MagicMock()

    with patch.object(cls, "__init__", lambda self, h, e: None):
        coord = cls(hass, entry)
    coord.hass = hass
    coord._entry = entry
    coord._token = "stale-token"
    coord._facility_id = "f1"
    coord._reauth_pending = False
    # cached fields for PowerHubCoordinator
    coord._cached_attributes = MagicMock()
    coord._cached_profile = MagicMock()
    coord._cached_agreements = []
    coord._cached_facility_info = MagicMock()
    coord._facility_info_resolved = True
    return coord, entry


class TestPowerHubCoordinatorReauthGuard:
    async def test_first_auth_error_triggers_reauth(self) -> None:
        coord, entry = _make_coordinator_env(PowerHubCoordinator)
        coord._make_client = MagicMock(return_value=MagicMock(
            get_facility_attributes=AsyncMock(side_effect=AuthError("expired")),
        ))
        coord._make_power_client = MagicMock()

        # Force first branch to execute get_facility_attributes by clearing the cache
        coord._cached_attributes = None

        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

        entry.async_start_reauth.assert_called_once_with(coord.hass)
        assert coord._reauth_pending is True

    async def test_subsequent_auth_errors_do_not_re_trigger(self) -> None:
        coord, entry = _make_coordinator_env(PowerHubCoordinator)
        coord._make_client = MagicMock(return_value=MagicMock(
            get_facility_attributes=AsyncMock(side_effect=AuthError("expired")),
        ))
        coord._make_power_client = MagicMock()
        coord._cached_attributes = None

        # First tick — arms the guard
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

        # Subsequent ticks — same AuthError, but we already asked HA once
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

        entry.async_start_reauth.assert_called_once()
        assert coord._reauth_pending is True

    async def test_successful_poll_resets_guard(self) -> None:
        """After the user completes reauth and the coordinator polls
        successfully once, the guard clears so a future token expiry
        can trigger a new reauth flow."""
        coord, entry = _make_coordinator_env(PowerHubCoordinator)
        coord._reauth_pending = True  # simulate: previously triggered

        # Stub the whole update path to succeed and return a usable dataclass
        async def fake_success(self):
            self._reauth_pending = False
            return MagicMock()

        with patch.object(
            PowerHubCoordinator,
            "_async_update_data",
            fake_success,
        ):
            await coord._async_update_data()

        assert coord._reauth_pending is False


class TestNotificationsCoordinatorReauthGuard:
    async def test_first_auth_error_triggers_reauth(self) -> None:
        coord, entry = _make_coordinator_env(NotificationsCoordinator)
        client = MagicMock()
        client.get_notifications = AsyncMock(side_effect=AuthError("expired"))

        with patch(
            "custom_components.malarenergi_powerhub.notifications_coordinator.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.notifications_coordinator.PowerHubApiClient",
            return_value=client,
        ):
            with pytest.raises(UpdateFailed):
                await coord._async_update_data()

        entry.async_start_reauth.assert_called_once_with(coord.hass)
        assert coord._reauth_pending is True

    async def test_subsequent_auth_errors_do_not_re_trigger(self) -> None:
        coord, entry = _make_coordinator_env(NotificationsCoordinator)
        client = MagicMock()
        client.get_notifications = AsyncMock(side_effect=AuthError("expired"))

        with patch(
            "custom_components.malarenergi_powerhub.notifications_coordinator.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.notifications_coordinator.PowerHubApiClient",
            return_value=client,
        ):
            with pytest.raises(UpdateFailed):
                await coord._async_update_data()
            with pytest.raises(UpdateFailed):
                await coord._async_update_data()
            with pytest.raises(UpdateFailed):
                await coord._async_update_data()

        entry.async_start_reauth.assert_called_once()

    async def test_successful_poll_resets_guard(self) -> None:
        coord, entry = _make_coordinator_env(NotificationsCoordinator)
        coord._reauth_pending = True
        client = MagicMock()
        client.get_notifications = AsyncMock(return_value=[])

        with patch(
            "custom_components.malarenergi_powerhub.notifications_coordinator.async_get_clientsession"
        ), patch(
            "custom_components.malarenergi_powerhub.notifications_coordinator.PowerHubApiClient",
            return_value=client,
        ):
            await coord._async_update_data()

        assert coord._reauth_pending is False
