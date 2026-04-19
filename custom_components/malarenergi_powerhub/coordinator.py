"""DataUpdateCoordinator for Mälarenergi PowerHub."""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace as dataclass_replace
from datetime import datetime, timedelta, timezone

from aiohttp import ClientResponseError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AccountProfile,
    Agreement,
    AuthError,
    FacilityAttributes,
    FacilityControl,
    FacilityInfo,
    FcrStatus,
    HourlyEnergy,
    Invitation,
    Invitee,
    MonthlyInsights,
    NotificationSettings,
    PhaseTelemetry,
    PowerApiClient,
    PowerDiagnostics,
    PowerHubApiClient,
    PowerTelemetry,
)
from .const import CONF_FACILITY_ID, CONF_TOKEN, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class PowerHubData:
    """Snapshot of data from the PowerHub API."""
    consumption_today_kwh: float | None    # kWh imported from grid today so far
    production_today_kwh: float | None     # kWh exported to grid today so far
    spot_price_now: float | None           # Current Nordpool spot price (öre/kWh)
    attributes: FacilityAttributes | None  # Static facility attributes (solar, battery, etc.)
    invitations: list[Invitation]          # Active sharing invitations
    invitees: list[Invitee]               # People with access to the facility
    # Account / facility metadata
    profile: AccountProfile | None         # Account holder name, email, phone
    agreements: list[Agreement]            # Supply agreements
    facility_info: FacilityInfo | None     # Address, meter ID, region
    notification_settings: NotificationSettings | None  # Push notification prefs
    monthly_insights: MonthlyInsights | None            # Current-month price/usage stats
    production_ytd_kwh: float | None                    # kWh exported to grid this year
    # Power backend (real-time)
    current_power: PowerTelemetry | None      # Most recent 1-min total power sample
    current_power_phases: PhaseTelemetry | None  # Most recent per-phase sample
    diagnostics: PowerDiagnostics | None      # Device status
    facility_control: FacilityControl | None  # Fuse/power limits
    fcr_status: FcrStatus | None              # FCR enablement
    hourly_energy_today: list[HourlyEnergy]   # Hourly energy buckets (today)


def _day_start_ms() -> int:
    """Unix timestamp in ms for start of today in Europe/Stockholm."""
    import zoneinfo
    tz = zoneinfo.ZoneInfo("Europe/Stockholm")
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


async def _optional(coro, name: str, default=None):
    """Await an optional endpoint; map 404 to `default`, re-raise everything else.

    404 is the expected response for accounts whose PowerHub device isn't
    fully provisioned. Other errors (5xx, timeouts, protocol) should still
    fail the coordinator tick so the user sees the problem instead of
    getting silently stale/missing data. AuthError propagates so the
    reauth guard runs.
    """
    try:
        return await coro
    except ClientResponseError as err:
        if err.status == 404:
            _LOGGER.debug("Optional endpoint %s returned 404", name)
            return default
        raise


class PowerHubCoordinator(DataUpdateCoordinator[PowerHubData]):
    """Coordinator that polls the Bitvis Flow API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._token = entry.data[CONF_TOKEN]
        self._facility_id = entry.data[CONF_FACILITY_ID]
        self._entry = entry
        self._cached_attributes: FacilityAttributes | None = None
        self._cached_profile: AccountProfile | None = None
        self._cached_agreements: list[Agreement] | None = None
        self._cached_facility_info: FacilityInfo | None = None
        self._facility_info_resolved = False
        # True once we've asked HA to start a reauth flow; reset after a
        # successful poll. Prevents spamming async_start_reauth (and its
        # log line) on every 60-second tick while the user is scanning the
        # BankID QR code.
        self._reauth_pending = False
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    def _make_client(self) -> PowerHubApiClient:
        session = async_get_clientsession(self.hass)
        return PowerHubApiClient(session, self._token)

    def _make_power_client(self) -> PowerApiClient:
        session = async_get_clientsession(self.hass)
        return PowerApiClient(session, self._token)

    async def _async_update_data(self) -> PowerHubData:
        client = self._make_client()
        power_client = self._make_power_client()
        day_ms = _day_start_ms()
        now_ms = _now_ms()

        try:
            # Static data — cache after first successful fetch
            if self._cached_attributes is None:
                self._cached_attributes = await client.get_facility_attributes(
                    self._facility_id
                )
            if self._cached_profile is None:
                self._cached_profile = await client.get_profile()
            if self._cached_agreements is None:
                self._cached_agreements = await client.get_agreements()
            if not self._facility_info_resolved:
                facilities = await client.get_facilities()
                self._cached_facility_info = next(
                    (f for f in facilities if f.facility_id == self._facility_id),
                    None,
                )
                self._facility_info_resolved = True
                if self._cached_facility_info is None and facilities:
                    _LOGGER.warning(
                        "Configured facility_id %s was not found in the returned facilities. "
                        "Facility metadata (address, meter ID) will be unavailable. "
                        "Please verify the facility_id in your configuration or reconfigure the integration.",
                        self._facility_id,
                    )

            # Notification settings (fetched each poll — user may change in app)
            notification_settings = await power_client.get_notification_settings(
                self._facility_id
            )

            # Monthly insights for the current month
            import zoneinfo as _zi
            _tz = _zi.ZoneInfo("Europe/Stockholm")
            _now_local = datetime.now(_tz)
            _month_start = _now_local.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            _month_start_ms = int(_month_start.timestamp() * 1000)
            monthly_insights = await client.get_monthly_insights(
                self._facility_id, _month_start_ms
            )
            production_insights = await client.get_monthly_insights(
                self._facility_id, _month_start_ms, meter_type="production"
            )
            production_ytd_kwh = production_insights.current_year_value

            # Consumption today — API returns Wh per bucket; convert to kWh
            consumption_points = await client.get_today_consumption(
                self._facility_id, day_ms
            )
            past_consumption = [p for p in consumption_points if p.timestamp_ms <= now_ms]
            consumption_kwh = (
                round(sum(p.value_wh for p in past_consumption) / 1000, 3)
                if past_consumption else None
            )

            # Production (export) today — API returns Wh per bucket; convert to kWh
            production_points = await client.get_today_production(
                self._facility_id, day_ms
            )
            past_production = [p for p in production_points if p.timestamp_ms <= now_ms]
            production_kwh = (
                round(sum(p.value_wh for p in past_production) / 1000, 3)
                if past_production else None
            )

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

            # Invitations and invitees (account-level, fetched each poll)
            invitations = await client.get_invitations()
            invitees = await client.get_invitees(self._facility_id)

            # Power backend: real-time power, diagnostics, facility control.
            # These endpoints can 404 for accounts whose PowerHub device isn't
            # fully provisioned — treat as "no data" instead of failing the tick.
            current_power = await _optional(
                power_client.get_current_power(self._facility_id), "current_power"
            )
            current_power_phases = await _optional(
                power_client.get_current_power_phases(self._facility_id),
                "current_power_phases",
            )
            diagnostics = await _optional(
                power_client.get_diagnostics(self._facility_id), "diagnostics"
            )
            facility_control = await _optional(
                power_client.get_facility_control(self._facility_id), "facility_control"
            )
            fcr_status = await _optional(
                power_client.get_fcr_status(self._facility_id), "fcr_status"
            )

            # Hourly energy for today (from midnight Stockholm time until now)
            import zoneinfo
            tz = zoneinfo.ZoneInfo("Europe/Stockholm")
            from datetime import datetime as _dt
            now_local = _dt.now(tz)
            day_start_utc = now_local.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).astimezone(timezone.utc)
            hourly_energy_today = await _optional(
                power_client.get_hourly_energy(
                    self._facility_id,
                    start=day_start_utc,
                    end=datetime.now(tz=timezone.utc),
                ),
                "hourly_energy_today",
                default=[],
            )

        except AuthError:
            if not self._reauth_pending:
                _LOGGER.warning("Token expired — triggering re-auth")
                self._entry.async_start_reauth(self.hass)
                self._reauth_pending = True
            raise UpdateFailed("Token expired, re-authentication required")
        except Exception as err:
            raise UpdateFailed(f"API error: {err}") from err

        # Poll succeeded — if the user just completed re-auth, clear the flag
        # so a future token expiry triggers a fresh reauth flow.
        self._reauth_pending = False

        return PowerHubData(
            consumption_today_kwh=consumption_kwh,
            production_today_kwh=production_kwh,
            spot_price_now=spot_now,
            attributes=self._cached_attributes,
            invitations=invitations,
            invitees=invitees,
            profile=self._cached_profile,
            agreements=self._cached_agreements or [],
            facility_info=self._cached_facility_info,
            notification_settings=notification_settings,
            current_power=current_power,
            current_power_phases=current_power_phases,
            diagnostics=diagnostics,
            facility_control=facility_control,
            fcr_status=fcr_status,
            hourly_energy_today=hourly_energy_today,
            monthly_insights=monthly_insights,
            production_ytd_kwh=production_ytd_kwh,
        )

    async def async_update_facility_control(self, **kwargs) -> None:
        """Update one or more FacilityControl fields, then refresh."""
        if self.data is None or self.data.facility_control is None:
            raise RuntimeError("Facility control not yet loaded")
        updated = dataclass_replace(self.data.facility_control, **kwargs)
        power_client = self._make_power_client()
        await power_client.update_facility_control(self._facility_id, updated)
        await self.async_request_refresh()

    async def async_update_notification_settings(self, **kwargs) -> None:
        """Update one or more NotificationSettings fields, then refresh."""
        if self.data is None or self.data.notification_settings is None:
            raise RuntimeError("Notification settings not yet loaded")
        updated = dataclass_replace(self.data.notification_settings, **kwargs)
        power_client = self._make_power_client()
        await power_client.update_notification_settings(self._facility_id, updated)
        await self.async_request_refresh()

    async def async_update_attributes(self, **kwargs) -> None:
        """Write one or more attribute fields via PUT, then refresh sensors.

        Keyword arguments must match FacilityAttributes field names, e.g.:
            await coordinator.async_update_attributes(fuse_size=20)
        """
        if self._cached_attributes is None:
            raise RuntimeError("Facility attributes not yet loaded")
        updated = dataclass_replace(self._cached_attributes, **kwargs)
        client = self._make_client()
        self._cached_attributes = await client.update_facility_attributes(
            self._facility_id, updated
        )
        await self.async_request_refresh()
