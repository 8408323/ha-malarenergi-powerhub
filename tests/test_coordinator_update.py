"""Tests for PowerHubCoordinator._async_update_data and update helpers.

These tests drive the coordinator without the HomeAssistant runtime by
mocking the HTTP clients returned by _make_client() and _make_power_client().
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientError, ClientResponseError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.malarenergi_powerhub.api import (
    AccountProfile,
    Agreement,
    AuthError,
    FacilityAttributes,
    FacilityControl,
    FacilityInfo,
    FcrStatus,
    HourlyEnergy,
    MeterData,
    MonthlyInsights,
    NotificationSettings,
    PhaseTelemetry,
    PowerDiagnostics,
    PowerTelemetry,
)
from custom_components.malarenergi_powerhub.coordinator import (
    PowerHubCoordinator,
    PowerHubData,
)

# ── Fixtures / builders ───────────────────────────────────────────────────────


def _make_facility_attributes(**kw) -> FacilityAttributes:
    defaults = dict(
        heating_type="DISTRICT_HEATING",
        fuse_size=20,
        occupants=2,
        area=80,
        facility_type="APARTMENT",
        ev_type="NONE",
        has_battery=False,
        has_solar=False,
    )
    defaults.update(kw)
    return FacilityAttributes(**defaults)


def _make_monthly_insights(**kw) -> MonthlyInsights:
    defaults = dict(
        facility_id="fac-1",
        month_timestamp_ms=0,
        your_average_price=85.0,
        monthly_average_price=90.0,
        price_trend="BELOW",
        current_year_value=1500.0,
        previous_year_value=1400.0,
        year_percentage_change=7.1,
        year_trend="ABOVE",
        daily_peaks=[],
        baseload_kw=0.5,
        baseload_kwh=360.0,
        baseload_percentage=24.0,
        total_kwh=1500.0,
        off_peak_score=0.7,
        off_peak_rating="GOOD",
    )
    defaults.update(kw)
    return MonthlyInsights(**defaults)


def _make_notification_settings(**kw) -> NotificationSettings:
    defaults = dict(
        notify_total_power=True,
        notify_phase_load=False,
        notify_control_disabled_exceeded_phase=False,
        notify_control_disabled_exceeded_power=False,
        notify_control_enabled_exceeded_phase=False,
        notify_control_enabled_exceeded_power=False,
    )
    defaults.update(kw)
    return NotificationSettings(**defaults)


def _make_facility_control(**kw) -> FacilityControl:
    defaults = dict(
        fuse_limit_a=25.0,
        power_limit_kw=10.0,
        action_on_fuse_limit="NOTIFY",
        action_on_power_limit="NOTIFY",
    )
    defaults.update(kw)
    return FacilityControl(**defaults)


def _make_api_client_mock(facility_attributes=None, **overrides) -> MagicMock:
    """A mock PowerHubApiClient with all methods returning sensible defaults."""
    client = MagicMock()
    attrs = facility_attributes or _make_facility_attributes()

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    consumption_data = [MeterData(timestamp_ms=now_ms - 60_000, value_wh=500.0)]
    production_data = [MeterData(timestamp_ms=now_ms - 60_000, value_wh=200.0)]
    spot_data = [{"timestamp": now_ms - 60_000, "value": 95.5}]

    client.get_facility_attributes = AsyncMock(return_value=attrs)
    client.get_profile = AsyncMock(
        return_value=AccountProfile(
            name="Test User",
            phone="070-000-0000",
            email="test@example.com",
            customer_number="C123",
        )
    )
    client.get_agreements = AsyncMock(
        return_value=[
            Agreement(
                agreement_number="AGR-1",
                supply_service_name="Electricity",
                supply_start_date_ms=0,
                price_model="SPOT",
                utility="ELECTRICITY",
                facility_id="fac-1",
            )
        ]
    )
    client.get_facilities = AsyncMock(
        return_value=[
            FacilityInfo(
                facility_id="fac-1",
                street="Test Street",
                house_number=1,
                city="Stockholm",
                meter_id="M001",
                region="SE3",
                customer_id="C123",
            )
        ]
    )
    client.get_monthly_insights = AsyncMock(return_value=_make_monthly_insights())
    client.get_today_consumption = AsyncMock(return_value=consumption_data)
    client.get_today_production = AsyncMock(return_value=production_data)
    client.get_spot_price_today = AsyncMock(return_value=spot_data)
    client.get_invitations = AsyncMock(return_value=[])
    client.get_invitees = AsyncMock(return_value=[])
    client.update_facility_attributes = AsyncMock(return_value=attrs)

    for attr, val in overrides.items():
        setattr(client, attr, val)

    return client


def _make_power_client_mock(**overrides) -> MagicMock:
    """A mock PowerApiClient with all methods returning sensible defaults."""
    client = MagicMock()
    now_ts = datetime.now(timezone.utc)
    client.get_notification_settings = AsyncMock(return_value=_make_notification_settings())
    client.get_current_power = AsyncMock(
        return_value=PowerTelemetry(timestamp=now_ts, power_import_kw=2.5, power_export_kw=0.0)
    )
    client.get_current_power_phases = AsyncMock(
        return_value=PhaseTelemetry(timestamp=now_ts, current_l1_a=5.0, current_l2_a=3.0, current_l3_a=4.0)
    )
    client.get_diagnostics = AsyncMock(
        return_value=PowerDiagnostics(
            uptime_s=3600,
            wifi_rssi_dbm=-55,
            sw_version="1.2.3",
            han_port_state="ACTIVE",
        )
    )
    client.get_facility_control = AsyncMock(return_value=_make_facility_control())
    client.get_fcr_status = AsyncMock(return_value=FcrStatus(fcrd_down_enabled=False))
    client.get_hourly_energy = AsyncMock(
        return_value=[
            HourlyEnergy(
                bucket_start=now_ts,
                window_start=now_ts,
                window_end=now_ts,
                sample_count=1,
                energy_import_wh=500.0,
                energy_export_wh=0.0,
            )
        ]
    )
    client.update_facility_control = AsyncMock(return_value=None)
    client.update_notification_settings = AsyncMock(return_value=None)

    for attr, val in overrides.items():
        setattr(client, attr, val)

    return client


def _make_coordinator(facility_id="fac-1") -> PowerHubCoordinator:
    """Instantiate a PowerHubCoordinator without the HA runtime."""
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"token": "tok", "facility_id": facility_id}
    entry.async_start_reauth = MagicMock()

    hass = MagicMock()
    hass.loop = MagicMock()

    with patch.object(PowerHubCoordinator, "__init__", lambda self, h, e: None):
        coord = PowerHubCoordinator(hass, entry)

    coord.hass = hass
    coord._entry = entry
    coord._token = "tok"
    coord._facility_id = facility_id
    coord._reauth_pending = False
    coord._cached_attributes = None
    coord._cached_profile = None
    coord._cached_agreements = None
    coord._cached_facility_info = None
    coord._facility_info_resolved = False
    coord._degraded_endpoints = set()
    coord.data = None
    coord.async_request_refresh = AsyncMock()
    return coord


# ── _async_update_data happy path ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_update_data_returns_powerhubdata() -> None:
    """A successful poll returns a PowerHubData with all fields set."""
    coord = _make_coordinator()
    api = _make_api_client_mock()
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    result = await coord._async_update_data()

    assert isinstance(result, PowerHubData)
    assert result.spot_price_now == 95.5
    assert result.current_power.power_import_kw == 2.5
    assert result.diagnostics.sw_version == "1.2.3"
    assert result.profile.name == "Test User"
    assert result.agreements[0].price_model == "SPOT"
    assert result.facility_info.region == "SE3"
    assert result.notification_settings.notify_total_power is True


@pytest.mark.asyncio
async def test_async_update_data_calculates_consumption_kwh() -> None:
    """Consumption is the sum of past MeterData points, converted Wh → kWh."""
    coord = _make_coordinator()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    # Two past buckets of 400 Wh each + one future bucket (should be excluded)
    data = [
        MeterData(timestamp_ms=now_ms - 120_000, value_wh=400.0),
        MeterData(timestamp_ms=now_ms - 60_000, value_wh=400.0),
        MeterData(timestamp_ms=now_ms + 3_600_000, value_wh=600.0),  # future
    ]
    api = _make_api_client_mock()
    api.get_today_consumption = AsyncMock(return_value=data)
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    result = await coord._async_update_data()

    assert result.consumption_today_kwh == round(800 / 1000, 3)  # 0.8 kWh


@pytest.mark.asyncio
async def test_async_update_data_consumption_none_when_no_past_points() -> None:
    """If no past points exist, consumption_today_kwh is None."""
    coord = _make_coordinator()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    future_only = [MeterData(timestamp_ms=now_ms + 3_600_000, value_wh=500.0)]
    api = _make_api_client_mock()
    api.get_today_consumption = AsyncMock(return_value=future_only)
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    result = await coord._async_update_data()

    assert result.consumption_today_kwh is None


@pytest.mark.asyncio
async def test_async_update_data_spot_price_picks_most_recent_past_bucket() -> None:
    """Spot price uses the latest bucket whose timestamp is <= now."""
    coord = _make_coordinator()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    spot_points = [
        {"timestamp": now_ms - 1_800_000, "value": 80.0},  # 30 min ago
        {"timestamp": now_ms - 900_000, "value": 90.0},  # 15 min ago (most recent)
        {"timestamp": now_ms + 900_000, "value": 100.0},  # future
    ]
    api = _make_api_client_mock()
    api.get_spot_price_today = AsyncMock(return_value=spot_points)
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    result = await coord._async_update_data()

    assert result.spot_price_now == 90.0


@pytest.mark.asyncio
async def test_async_update_data_spot_price_none_when_no_past_points() -> None:
    """If all spot buckets are in the future, spot_price_now is None."""
    coord = _make_coordinator()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    future_only = [{"timestamp": now_ms + 900_000, "value": 100.0}]
    api = _make_api_client_mock()
    api.get_spot_price_today = AsyncMock(return_value=future_only)
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    result = await coord._async_update_data()

    assert result.spot_price_now is None


# ── Caching behavior ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_static_data_fetched_only_on_first_poll() -> None:
    """get_facility_attributes, get_profile, get_agreements, get_facilities
    should each be called exactly once across two polls."""
    coord = _make_coordinator()
    api = _make_api_client_mock()
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    await coord._async_update_data()
    await coord._async_update_data()

    api.get_facility_attributes.assert_awaited_once()
    api.get_profile.assert_awaited_once()
    api.get_agreements.assert_awaited_once()
    api.get_facilities.assert_awaited_once()


@pytest.mark.asyncio
async def test_notification_settings_fetched_every_poll() -> None:
    """Notification settings are not cached — fetched on every tick."""
    coord = _make_coordinator()
    api = _make_api_client_mock()
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    await coord._async_update_data()
    await coord._async_update_data()

    assert power.get_notification_settings.await_count == 2


@pytest.mark.asyncio
async def test_facility_id_not_found_logs_warning_and_uses_none() -> None:
    """If facility_id doesn't match any entry in get_facilities(), facility_info is None."""
    coord = _make_coordinator(facility_id="MISSING-FAC")
    api = _make_api_client_mock()
    api.get_facilities = AsyncMock(
        return_value=[
            FacilityInfo(
                facility_id="OTHER-FAC",
                street="Other St",
                house_number=2,
                city="Västerås",
                meter_id="M999",
                region="SE3",
                customer_id="C000",
            )
        ]
    )
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    result = await coord._async_update_data()

    assert result.facility_info is None


# ── Error handling ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generic_error_wrapped_in_update_failed() -> None:
    """A non-AuthError exception is wrapped in UpdateFailed."""
    coord = _make_coordinator()
    api = _make_api_client_mock()
    api.get_notification_settings = AsyncMock(  # patched onto power client below
        side_effect=RuntimeError("network timeout")
    )
    power = _make_power_client_mock()
    power.get_notification_settings = AsyncMock(side_effect=RuntimeError("network timeout"))
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    with pytest.raises(UpdateFailed, match="API error"):
        await coord._async_update_data()


# ── Resilient account-metadata fetches (issue #52) ────────────────────────────


def _response_error(status: int) -> ClientResponseError:
    """Build an aiohttp ClientResponseError with the given HTTP status."""
    return ClientResponseError(MagicMock(), (), status=status, message="Request failed.")


@pytest.mark.asyncio
async def test_agreements_500_does_not_fail_tick() -> None:
    """A 500 on the non-critical agreements endpoint must not fail the tick.

    Regression test for issue #52: a server-side 500 on /account/agreement was
    taking every sensor — including live energy data — offline.
    """
    coord = _make_coordinator()
    api = _make_api_client_mock()
    api.get_agreements = AsyncMock(side_effect=_response_error(500))
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    result = await coord._async_update_data()

    # Tick succeeds; agreements come through empty, energy data is intact.
    assert result.agreements == []
    assert result.consumption_today_kwh is not None
    assert result.spot_price_now == 95.5


@pytest.mark.asyncio
async def test_agreements_failure_retried_next_tick() -> None:
    """After a failed agreements fetch, it is retried (not cached) next update."""
    coord = _make_coordinator()
    api = _make_api_client_mock()
    good = [
        Agreement(
            agreement_number="AGR-1",
            supply_service_name="Electricity",
            supply_start_date_ms=0,
            price_model="SPOT",
            utility="ELECTRICITY",
            facility_id="fac-1",
        )
    ]
    api.get_agreements = AsyncMock(side_effect=[_response_error(500), good])
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    first = await coord._async_update_data()
    second = await coord._async_update_data()

    assert first.agreements == []
    assert second.agreements[0].agreement_number == "AGR-1"
    assert api.get_agreements.await_count == 2


@pytest.mark.asyncio
async def test_repeated_failure_logs_warning_once_then_recovers(caplog) -> None:
    """A persistently-failing endpoint warns once, repeats at debug, then logs recovery.

    Guards against flooding the HA log every 60s while a backend endpoint is down.
    """
    import logging

    coord = _make_coordinator()
    api = _make_api_client_mock()
    good = [
        Agreement(
            agreement_number="AGR-1",
            supply_service_name="Electricity",
            supply_start_date_ms=0,
            price_model="SPOT",
            utility="ELECTRICITY",
            facility_id="fac-1",
        )
    ]
    # fail, fail, then succeed across three ticks
    api.get_agreements = AsyncMock(side_effect=[_response_error(500), _response_error(500), good])
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    caplog.set_level(logging.DEBUG, logger="custom_components.malarenergi_powerhub.coordinator")

    await coord._async_update_data()  # tick 1: WARNING
    await coord._async_update_data()  # tick 2: DEBUG (still failing)
    await coord._async_update_data()  # tick 3: success → INFO recovered

    agreement_warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "agreements" in r.getMessage()]
    agreement_debugs = [
        r for r in caplog.records if r.levelno == logging.DEBUG and "agreements still failing" in r.getMessage()
    ]
    recovery = [r for r in caplog.records if r.levelno == logging.INFO and "agreements recovered" in r.getMessage()]

    assert len(agreement_warnings) == 1  # warned exactly once, not per tick
    assert len(agreement_debugs) == 1  # second failure downgraded to debug
    assert len(recovery) == 1  # recovery logged once
    assert coord._degraded_endpoints == set()  # cleared after recovery


@pytest.mark.asyncio
async def test_static_fetch_auth_error_propagates_to_reauth() -> None:
    """AuthError from a static fetch still triggers the reauth guard."""
    coord = _make_coordinator()
    api = _make_api_client_mock()
    api.get_agreements = AsyncMock(side_effect=AuthError("token expired"))
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    coord._entry.async_start_reauth.assert_called_once()


@pytest.mark.asyncio
async def test_profile_client_error_tolerated() -> None:
    """A connection-level ClientError on profile is tolerated (profile None)."""
    coord = _make_coordinator()
    api = _make_api_client_mock()
    api.get_profile = AsyncMock(side_effect=ClientError("connection reset"))
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    result = await coord._async_update_data()

    assert result.profile is None


@pytest.mark.asyncio
async def test_attributes_timeout_tolerated() -> None:
    """A TimeoutError on attributes is tolerated (attributes None)."""
    coord = _make_coordinator()
    api = _make_api_client_mock()
    api.get_facility_attributes = AsyncMock(side_effect=TimeoutError())
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    result = await coord._async_update_data()

    assert result.attributes is None


@pytest.mark.asyncio
async def test_facilities_failure_tolerated_and_retried() -> None:
    """A 500 on the facilities list leaves facility_info None and retries next tick."""
    coord = _make_coordinator()
    api = _make_api_client_mock()
    good = [
        FacilityInfo(
            facility_id="fac-1",
            street="Test Street",
            house_number=1,
            city="Stockholm",
            meter_id="M001",
            region="SE3",
            customer_id="C123",
        )
    ]
    api.get_facilities = AsyncMock(side_effect=[_response_error(500), good])
    power = _make_power_client_mock()
    coord._make_client = MagicMock(return_value=api)
    coord._make_power_client = MagicMock(return_value=power)

    first = await coord._async_update_data()
    second = await coord._async_update_data()

    assert first.facility_info is None
    assert second.facility_info is not None
    assert second.facility_info.region == "SE3"
    assert api.get_facilities.await_count == 2


# ── async_update_attributes ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_update_attributes_calls_api_and_refreshes() -> None:
    """update_attributes writes the merged attributes and triggers a refresh."""
    coord = _make_coordinator()
    attrs = _make_facility_attributes(area=80)
    coord._cached_attributes = attrs

    updated_attrs = _make_facility_attributes(area=100)
    api = MagicMock()
    api.update_facility_attributes = AsyncMock(return_value=updated_attrs)
    coord._make_client = MagicMock(return_value=api)

    await coord.async_update_attributes(area=100)

    api.update_facility_attributes.assert_awaited_once()
    # The call should pass the facility_id and an attrs object with area=100
    call_args = api.update_facility_attributes.call_args
    assert call_args.args[0] == "fac-1"
    assert call_args.args[1].area == 100
    coord.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_update_attributes_raises_when_no_cache() -> None:
    """RuntimeError if attributes haven't been loaded yet."""
    coord = _make_coordinator()
    coord._cached_attributes = None

    with pytest.raises(RuntimeError):
        await coord.async_update_attributes(area=100)


@pytest.mark.asyncio
async def test_async_update_attributes_updates_local_cache() -> None:
    """After calling update_attributes, _cached_attributes reflects the API result."""
    coord = _make_coordinator()
    coord._cached_attributes = _make_facility_attributes(area=80)

    new_attrs = _make_facility_attributes(area=100)
    api = MagicMock()
    api.update_facility_attributes = AsyncMock(return_value=new_attrs)
    coord._make_client = MagicMock(return_value=api)

    await coord.async_update_attributes(area=100)

    assert coord._cached_attributes.area == 100


# ── async_update_facility_control ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_update_facility_control_calls_api_and_refreshes() -> None:
    """update_facility_control writes the merged control and triggers a refresh."""
    coord = _make_coordinator()
    control = _make_facility_control(power_limit_kw=10.0)
    coord.data = MagicMock()
    coord.data.facility_control = control

    power_client = MagicMock()
    power_client.update_facility_control = AsyncMock(return_value=None)
    coord._make_power_client = MagicMock(return_value=power_client)

    await coord.async_update_facility_control(power_limit_kw=15.0)

    power_client.update_facility_control.assert_awaited_once()
    call_args = power_client.update_facility_control.call_args
    assert call_args.args[0] == "fac-1"
    assert call_args.args[1].power_limit_kw == 15.0
    coord.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_update_facility_control_raises_when_no_data() -> None:
    coord = _make_coordinator()
    coord.data = None

    with pytest.raises(RuntimeError):
        await coord.async_update_facility_control(power_limit_kw=15.0)


@pytest.mark.asyncio
async def test_async_update_facility_control_raises_when_no_control() -> None:
    coord = _make_coordinator()
    coord.data = MagicMock()
    coord.data.facility_control = None

    with pytest.raises(RuntimeError):
        await coord.async_update_facility_control(power_limit_kw=15.0)


# ── async_update_notification_settings ────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_update_notification_settings_calls_api_and_refreshes() -> None:
    coord = _make_coordinator()
    settings = _make_notification_settings(notify_phase_load=False)
    coord.data = MagicMock()
    coord.data.notification_settings = settings

    power_client = MagicMock()
    power_client.update_notification_settings = AsyncMock(return_value=None)
    coord._make_power_client = MagicMock(return_value=power_client)

    await coord.async_update_notification_settings(notify_phase_load=True)

    power_client.update_notification_settings.assert_awaited_once()
    call_args = power_client.update_notification_settings.call_args
    assert call_args.args[0] == "fac-1"
    assert call_args.args[1].notify_phase_load is True
    coord.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_update_notification_settings_raises_when_no_data() -> None:
    coord = _make_coordinator()
    coord.data = None

    with pytest.raises(RuntimeError):
        await coord.async_update_notification_settings(notify_phase_load=True)


@pytest.mark.asyncio
async def test_async_update_notification_settings_raises_when_no_settings() -> None:
    coord = _make_coordinator()
    coord.data = MagicMock()
    coord.data.notification_settings = None

    with pytest.raises(RuntimeError):
        await coord.async_update_notification_settings(notify_phase_load=True)
