"""Separate coordinator for PowerHub push notifications (polls every 5 min)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from aiohttp import ClientResponseError

from .api import AuthError, PowerHubApiClient
from .const import CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

NOTIFICATIONS_SCAN_INTERVAL = 300  # 5 minutes


@dataclass
class NotificationData:
    """Most recent notification from the Mälarenergi backend."""
    title: str | None
    body: str | None
    notification_type: str | None   # e.g. "PRICE"
    created_ms: int | None
    all_notifications: list[dict]   # Full list for extra_state_attributes


class NotificationsCoordinator(DataUpdateCoordinator[NotificationData]):
    """Coordinator that polls /notifications every 5 minutes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._token = entry.data[CONF_TOKEN]
        self._entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_notifications",
            update_interval=timedelta(seconds=NOTIFICATIONS_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> NotificationData:
        session = async_get_clientsession(self.hass)
        client = PowerHubApiClient(session, self._token)
        try:
            notifications = await client.get_notifications()
        except AuthError:
            _LOGGER.warning("Token expired fetching notifications — triggering re-auth")
            self._entry.async_start_reauth(self.hass)
            raise UpdateFailed("Token expired, re-authentication required")
        except ClientResponseError as err:
            if err.status == 400:
                # API rejects placeholder firebase_token — return empty data silently
                _LOGGER.debug("Notifications API returned 400 (firebase_token not accepted): %s", err)
                return NotificationData(
                    title=None, body=None, notification_type=None,
                    created_ms=None, all_notifications=[],
                )
            raise UpdateFailed(f"Notifications API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Notifications API error: {err}") from err

        if not notifications:
            return NotificationData(
                title=None,
                body=None,
                notification_type=None,
                created_ms=None,
                all_notifications=[],
            )

        latest = notifications[0]
        return NotificationData(
            title=latest.get("title"),
            body=latest.get("body"),
            notification_type=latest.get("type"),
            created_ms=latest.get("created"),
            all_notifications=notifications,
        )
