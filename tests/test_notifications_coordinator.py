"""Tests for NotificationsCoordinator data paths.

The reauth-guard behavior is already covered in test_coordinator_reauth_guard.py.
These tests cover the data-shaping paths and the 400/generic error branches.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponseError

from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.malarenergi_powerhub.notifications_coordinator import (
    NotificationData,
    NotificationsCoordinator,
)


def _make_coord() -> NotificationsCoordinator:
    """Instantiate NotificationsCoordinator bypassing the HA runtime."""
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"token": "tok"}
    entry.async_start_reauth = MagicMock()

    hass = MagicMock()
    hass.loop = MagicMock()

    with patch.object(NotificationsCoordinator, "__init__", lambda self, h, e: None):
        coord = NotificationsCoordinator(hass, entry)

    coord.hass = hass
    coord._entry = entry
    coord._token = "tok"
    coord._reauth_pending = False
    return coord


def _make_client_response_error(status: int) -> ClientResponseError:
    """Build a minimal ClientResponseError for a given HTTP status."""
    request_info = MagicMock()
    request_info.url = "https://api.example.com"
    request_info.method = "GET"
    request_info.headers = {}
    return ClientResponseError(request_info, (), status=status)


class TestNotificationsCoordinatorDataPaths:
    async def test_non_empty_notifications_returns_latest(self) -> None:
        """When the API returns notifications, the coordinator returns
        a NotificationData populated from the first (latest) entry."""
        coord = _make_coord()
        notifications = [
            {
                "title": "Högt elpris",
                "body": "Priset är nu 1,50 kr/kWh",
                "type": "PRICE",
                "created": 1_700_000_000_000,
            },
            {
                "title": "Äldre notis",
                "body": "…",
                "type": "GENERAL",
                "created": 1_600_000_000_000,
            },
        ]
        client = MagicMock()
        client.get_notifications = AsyncMock(return_value=notifications)

        with (
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.async_get_clientsession"
            ),
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.PowerHubApiClient",
                return_value=client,
            ),
        ):
            result = await coord._async_update_data()

        assert isinstance(result, NotificationData)
        assert result.title == "Högt elpris"
        assert result.body == "Priset är nu 1,50 kr/kWh"
        assert result.notification_type == "PRICE"
        assert result.created_ms == 1_700_000_000_000
        assert len(result.all_notifications) == 2

    async def test_empty_notifications_returns_empty_data(self) -> None:
        """An empty list → NotificationData with all None fields."""
        coord = _make_coord()
        client = MagicMock()
        client.get_notifications = AsyncMock(return_value=[])

        with (
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.async_get_clientsession"
            ),
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.PowerHubApiClient",
                return_value=client,
            ),
        ):
            result = await coord._async_update_data()

        assert result.title is None
        assert result.body is None
        assert result.notification_type is None
        assert result.created_ms is None
        assert result.all_notifications == []

    async def test_status_400_returns_empty_data_silently(self) -> None:
        """A 400 ClientResponseError means the firebase_token hasn't been
        registered yet — return empty data instead of raising UpdateFailed."""
        coord = _make_coord()
        client = MagicMock()
        client.get_notifications = AsyncMock(
            side_effect=_make_client_response_error(400)
        )

        with (
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.async_get_clientsession"
            ),
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.PowerHubApiClient",
                return_value=client,
            ),
        ):
            result = await coord._async_update_data()

        assert isinstance(result, NotificationData)
        assert result.title is None
        assert result.all_notifications == []

    async def test_non_400_client_error_raises_update_failed(self) -> None:
        """A non-400 ClientResponseError (e.g. 503) is wrapped in UpdateFailed."""
        coord = _make_coord()
        client = MagicMock()
        client.get_notifications = AsyncMock(
            side_effect=_make_client_response_error(503)
        )

        with (
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.async_get_clientsession"
            ),
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.PowerHubApiClient",
                return_value=client,
            ),
        ):
            with pytest.raises(UpdateFailed, match="Notifications API error"):
                await coord._async_update_data()

    async def test_generic_exception_raises_update_failed(self) -> None:
        """Any unexpected exception is wrapped in UpdateFailed."""
        coord = _make_coord()
        client = MagicMock()
        client.get_notifications = AsyncMock(
            side_effect=RuntimeError("network timeout")
        )

        with (
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.async_get_clientsession"
            ),
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.PowerHubApiClient",
                return_value=client,
            ),
        ):
            with pytest.raises(UpdateFailed, match="Notifications API error"):
                await coord._async_update_data()

    async def test_successful_poll_clears_reauth_pending_flag(self) -> None:
        """After a successful poll, _reauth_pending must be cleared so a
        future token expiry can trigger a fresh reauth flow."""
        coord = _make_coord()
        coord._reauth_pending = True
        client = MagicMock()
        client.get_notifications = AsyncMock(return_value=[])

        with (
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.async_get_clientsession"
            ),
            patch(
                "custom_components.malarenergi_powerhub.notifications_coordinator.PowerHubApiClient",
                return_value=client,
            ),
        ):
            await coord._async_update_data()

        assert coord._reauth_pending is False
