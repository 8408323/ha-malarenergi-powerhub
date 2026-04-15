"""DataUpdateCoordinator for Mälarenergi PowerHub."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthError, FacilityAttributes, PowerHubApiClient
from .const import CONF_FACILITY_ID, CONF_TOKEN, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class PowerHubData:
    """Snapshot of data from the PowerHub API."""
    consumption_today_kwh: float | None    # kWh imported from grid today so far
    production_today_kwh: float | None     # kWh exported to grid today so far
    spot_price_now: float | None           # Current Nordpool spot price (öre/kWh)
    attributes: FacilityAttributes | None  # Static facility attributes (solar, battery, etc.)


def _day_start_ms() -> int:
    """Unix timestamp in ms for start of today in Europe/Stockholm."""
    import zoneinfo
    tz = zoneinfo.ZoneInfo("Europe/Stockholm")
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


class PowerHubCoordinator(DataUpdateCoordinator[PowerHubData]):
    """Coordinator that polls the Bitvis Flow API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._token = entry.data[CONF_TOKEN]
        self._facility_id = entry.data[CONF_FACILITY_ID]
        self._entry = entry
        self._cached_attributes: FacilityAttributes | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    def _make_client(self) -> PowerHubApiClient:
        session = async_get_clientsession(self.hass)
        return PowerHubApiClient(session, self._token)

    async def _async_update_data(self) -> PowerHubData:
        client = self._make_client()
        day_ms = _day_start_ms()
        now_ms = _now_ms()

        try:
            # Fetch facility attributes once (static data — cache after first successful fetch)
            if self._cached_attributes is None:
                self._cached_attributes = await client.get_facility_attributes(
                    self._facility_id
                )

            # Consumption today — API returns kWh per 15-min bucket
            consumption_points = await client.get_today_consumption(
                self._facility_id, day_ms
            )
            consumption_kwh = sum(
                p.value_wh for p in consumption_points
                if p.timestamp_ms <= now_ms
            ) or None

            # Production (export) today — API returns kWh per 15-min bucket
            production_points = await client.get_today_production(
                self._facility_id, day_ms
            )
            production_kwh = sum(
                p.value_wh for p in production_points
                if p.timestamp_ms <= now_ms
            ) or None

            # Current spot price — find the 15-min bucket containing now
            spot_points = await client.get_spot_price_today(
                self._facility_id, day_ms
            )
            spot_now: float | None = None
            if spot_points:
                # Find the most recent bucket before now
                past = [p for p in spot_points if p["timestamp"] <= now_ms]
                if past:
                    spot_now = max(past, key=lambda p: p["timestamp"])["value"]

        except AuthError:
            _LOGGER.warning("Token expired — triggering re-auth")
            self._entry.async_start_reauth(self.hass)
            raise UpdateFailed("Token expired, re-authentication required")
        except Exception as err:
            raise UpdateFailed(f"API error: {err}") from err

        return PowerHubData(
            consumption_today_kwh=consumption_kwh,
            production_today_kwh=production_kwh,
            spot_price_now=spot_now,
            attributes=self._cached_attributes,
        )
