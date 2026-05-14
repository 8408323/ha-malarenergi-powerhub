"""Tests for sensor.py — value_fn lambdas and entity class behaviour.

Full entity lifecycle (async_added_to_hass, HA platform setup) requires the HA
runtime; those paths are skipped here. These tests cover:
  - SENSORS description table integrity (unique keys, callable value_fn)
  - Every value_fn with a realistic PowerHubData fixture
  - PowerHubSensor.native_value and extra_state_attributes
  - NotificationSensor.native_value (body truncation) and extra_state_attributes
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from custom_components.malarenergi_powerhub.api import (
    AccountProfile,
    Agreement,
    FacilityAttributes,
    FacilityControl,
    FacilityInfo,
    FcrStatus,
    Invitation,
    Invitee,
    MonthlyInsights,
    PhaseTelemetry,
    PowerDiagnostics,
    PowerTelemetry,
)
from custom_components.malarenergi_powerhub.coordinator import PowerHubData
from custom_components.malarenergi_powerhub.notifications_coordinator import (
    NotificationData,
)
from custom_components.malarenergi_powerhub.sensor import (
    SENSORS,
    NotificationSensor,
    PowerHubSensor,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_TS = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_data(**overrides) -> PowerHubData:
    """Return a fully-populated PowerHubData for testing."""
    base = dict(
        consumption_today_kwh=10.5,
        production_today_kwh=3.2,
        spot_price_now=42.7,
        attributes=FacilityAttributes(
            heating_type="DISTRICT_HEATING",
            fuse_size=20,
            occupants=2,
            area=80,
            facility_type="APARTMENT",
            ev_type="NONE",
            has_battery=False,
            has_solar=True,
        ),
        invitations=[
            Invitation(
                invitation_id="inv-1",
                expires="2026-12-31",
                created="2026-01-01",
                claimed=False,
                code="ABC123",
            )
        ],
        invitees=[
            Invitee(
                invitee_id="inv-2",
                claimer_name="Alice",
                facility_id="f1",
                share_all_devices=True,
            )
        ],
        profile=AccountProfile(
            name="Erik Svensson",
            phone="0700000000",
            email="erik@example.com",
            customer_number="C123456",
        ),
        agreements=[
            Agreement(
                agreement_number="A001",
                supply_service_name="Spot",
                supply_start_date_ms=1700000000000,
                price_model="SPOT",
                utility="ELECTRICITY",
                facility_id="f1",
            )
        ],
        facility_info=FacilityInfo(
            facility_id="f1",
            meter_id="M001",
            street="Storgatan",
            house_number=1,
            city="Västerås",
            region="SE3",
            customer_id="C123456",
        ),
        notification_settings=None,
        monthly_insights=MonthlyInsights(
            facility_id="f1",
            month_timestamp_ms=1700000000000,
            your_average_price=38.5,
            monthly_average_price=40.0,
            price_trend="BELOW",
            current_year_value=1250.0,
            previous_year_value=1200.0,
            year_percentage_change=4.2,
            year_trend="UP",
            daily_peaks=[],
            baseload_kw=0.5,
            baseload_kwh=360.0,
            baseload_percentage=28.8,
            total_kwh=1250.0,
            off_peak_score=0.72,
            off_peak_rating="GOOD",
        ),
        production_ytd_kwh=850.0,
        current_power=PowerTelemetry(
            timestamp=_TS,
            power_import_kw=2.345,
            power_export_kw=0.5,
        ),
        current_power_phases=PhaseTelemetry(
            timestamp=_TS,
            current_l1_a=10.5,
            current_l2_a=0.25,
            current_l3_a=0.0,
        ),
        diagnostics=PowerDiagnostics(
            uptime_s=86400,
            wifi_rssi_dbm=-65,
            sw_version="1.2.3",
            han_port_state="ACTIVE",
        ),
        facility_control=FacilityControl(
            fuse_limit_a=25.0,
            power_limit_kw=11.0,
            action_on_fuse_limit="NOTIFY",
            action_on_power_limit="NOTIFY",
        ),
        fcr_status=FcrStatus(fcrd_down_enabled=True),
        hourly_energy_today=[],
    )
    base.update(overrides)
    return PowerHubData(**base)


def _make_coord(data: PowerHubData | None = None) -> MagicMock:
    coord = MagicMock()
    coord.data = data if data is not None else _make_data()
    coord.config_entry.entry_id = "test-entry-id"
    return coord


# ── SENSORS description table ─────────────────────────────────────────────────

def test_sensors_have_unique_keys() -> None:
    keys = [d.key for d in SENSORS]
    assert len(keys) == len(set(keys))


def test_all_sensors_have_callable_value_fn() -> None:
    for desc in SENSORS:
        assert callable(desc.value_fn), f"{desc.key}: value_fn not callable"


# ── value_fn with full data ───────────────────────────────────────────────────

def test_import_today_value_fn() -> None:
    d = _make_data(consumption_today_kwh=12.34)
    desc = next(s for s in SENSORS if s.key == "import_today")
    assert desc.value_fn(d) == 12.34


def test_export_today_value_fn() -> None:
    d = _make_data(production_today_kwh=5.67)
    desc = next(s for s in SENSORS if s.key == "export_today")
    assert desc.value_fn(d) == 5.67


def test_spot_price_value_fn() -> None:
    d = _make_data(spot_price_now=99.9)
    desc = next(s for s in SENSORS if s.key == "spot_price")
    assert desc.value_fn(d) == 99.9


def test_power_import_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "power_import")
    assert desc.value_fn(d) == round(2.345, 3)


def test_power_import_none_when_no_current_power() -> None:
    d = _make_data(current_power=None)
    desc = next(s for s in SENSORS if s.key == "power_import")
    assert desc.value_fn(d) is None


def test_power_export_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "power_export")
    assert desc.value_fn(d) == round(0.5, 3)


def test_current_l1_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "current_l1")
    assert desc.value_fn(d) == round(10.5, 2)


def test_current_l2_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "current_l2")
    assert desc.value_fn(d) == round(0.25, 2)


def test_current_l3_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "current_l3")
    assert desc.value_fn(d) == 0.0


def test_phase_sensors_none_when_no_phases() -> None:
    d = _make_data(current_power_phases=None)
    for key in ("current_l1", "current_l2", "current_l3"):
        desc = next(s for s in SENSORS if s.key == key)
        assert desc.value_fn(d) is None, f"{key} should be None when phases absent"


def test_wifi_rssi_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "wifi_rssi")
    assert desc.value_fn(d) == -65


def test_wifi_rssi_none_when_no_diagnostics() -> None:
    d = _make_data(diagnostics=None)
    desc = next(s for s in SENSORS if s.key == "wifi_rssi")
    assert desc.value_fn(d) is None


def test_sw_version_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "sw_version")
    assert desc.value_fn(d) == "1.2.3"


def test_han_port_state_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "han_port_state")
    assert desc.value_fn(d) == "ACTIVE"


def test_power_limit_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "power_limit")
    assert desc.value_fn(d) == 11.0


def test_power_limit_none_when_no_control() -> None:
    d = _make_data(facility_control=None)
    desc = next(s for s in SENSORS if s.key == "power_limit")
    assert desc.value_fn(d) is None


def test_fcr_enabled_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "fcr_enabled")
    assert desc.value_fn(d) is True


def test_account_name_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "account_name")
    assert desc.value_fn(d) == "Erik Svensson"


def test_account_name_none_when_no_profile() -> None:
    d = _make_data(profile=None)
    desc = next(s for s in SENSORS if s.key == "account_name")
    assert desc.value_fn(d) is None


def test_customer_number_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "customer_number")
    assert desc.value_fn(d) == "C123456"


def test_facility_address_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "facility_address")
    assert desc.value_fn(d) == "Storgatan 1"


def test_facility_address_none_when_no_info() -> None:
    d = _make_data(facility_info=None)
    desc = next(s for s in SENSORS if s.key == "facility_address")
    assert desc.value_fn(d) is None


def test_meter_id_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "meter_id")
    assert desc.value_fn(d) == "M001"


def test_price_zone_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "price_zone")
    assert desc.value_fn(d) == "SE3"


def test_agreement_number_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "agreement_number")
    assert desc.value_fn(d) == "A001"


def test_agreement_number_none_when_no_agreements() -> None:
    d = _make_data(agreements=[])
    desc = next(s for s in SENSORS if s.key == "agreement_number")
    assert desc.value_fn(d) is None


def test_price_model_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "price_model")
    assert desc.value_fn(d) == "SPOT"


def test_uptime_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "uptime")
    assert desc.value_fn(d) == 86400


def test_avg_price_this_month_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "avg_price_this_month")
    assert desc.value_fn(d) == round(38.5, 2)


def test_avg_price_this_month_none_when_no_insights() -> None:
    d = _make_data(monthly_insights=None)
    desc = next(s for s in SENSORS if s.key == "avg_price_this_month")
    assert desc.value_fn(d) is None


def test_market_avg_price_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "market_avg_price_this_month")
    assert desc.value_fn(d) == round(40.0, 2)


def test_consumption_ytd_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "consumption_ytd")
    assert desc.value_fn(d) == 1250.0


def test_production_ytd_value_fn() -> None:
    d = _make_data(production_ytd_kwh=999.0)
    desc = next(s for s in SENSORS if s.key == "production_ytd")
    assert desc.value_fn(d) == 999.0


def test_baseload_power_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "baseload_power")
    assert desc.value_fn(d) == 0.5


def test_active_invitations_value_fn() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "active_invitations")
    assert desc.value_fn(d) == 1


def test_active_invitations_zero_when_empty() -> None:
    d = _make_data(invitations=[])
    desc = next(s for s in SENSORS if s.key == "active_invitations")
    assert desc.value_fn(d) == 0


def test_invitees_value_fn_shows_name() -> None:
    d = _make_data()
    desc = next(s for s in SENSORS if s.key == "invitees")
    assert desc.value_fn(d) == "Alice"


def test_invitees_value_fn_shows_count_when_no_name() -> None:
    d = _make_data(
        invitees=[Invitee(invitee_id="x", claimer_name="", facility_id="f1", share_all_devices=False)]
    )
    desc = next(s for s in SENSORS if s.key == "invitees")
    # Empty claimer_name → falls through to count
    assert desc.value_fn(d) == "1"


def test_invitees_value_fn_empty() -> None:
    d = _make_data(invitees=[])
    desc = next(s for s in SENSORS if s.key == "invitees")
    assert desc.value_fn(d) == "0"


# ── PowerHubSensor entity ─────────────────────────────────────────────────────

def test_powerhub_sensor_native_value_returns_correct_value() -> None:
    desc = next(s for s in SENSORS if s.key == "import_today")
    coord = _make_coord(_make_data(consumption_today_kwh=7.77))
    sensor = PowerHubSensor(coord, desc)
    assert sensor.native_value == 7.77


def test_powerhub_sensor_native_value_none_when_no_data() -> None:
    desc = next(s for s in SENSORS if s.key == "import_today")
    coord = _make_coord(None)
    coord.data = None
    sensor = PowerHubSensor(coord, desc)
    assert sensor.native_value is None


def test_powerhub_sensor_unique_id_uses_entry_id_and_key() -> None:
    desc = next(s for s in SENSORS if s.key == "spot_price")
    coord = _make_coord()
    sensor = PowerHubSensor(coord, desc)
    assert sensor._attr_unique_id == "test-entry-id_spot_price"


def test_powerhub_sensor_device_info_set() -> None:
    desc = next(s for s in SENSORS if s.key == "spot_price")
    sensor = PowerHubSensor(_make_coord(), desc)
    assert sensor._attr_device_info is not None
    assert "PowerHub" in sensor._attr_device_info["name"]


def test_powerhub_sensor_extra_state_attributes_none_for_regular_sensor() -> None:
    desc = next(s for s in SENSORS if s.key == "spot_price")
    sensor = PowerHubSensor(_make_coord(), desc)
    assert sensor.extra_state_attributes is None


def test_powerhub_sensor_extra_state_attrs_none_when_no_data() -> None:
    desc = next(s for s in SENSORS if s.key == "active_invitations")
    coord = _make_coord()
    coord.data = None
    sensor = PowerHubSensor(coord, desc)
    assert sensor.extra_state_attributes is None


def test_powerhub_sensor_active_invitations_extra_attrs() -> None:
    desc = next(s for s in SENSORS if s.key == "active_invitations")
    sensor = PowerHubSensor(_make_coord(), desc)
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert "invitations" in attrs
    assert len(attrs["invitations"]) == 1
    inv = attrs["invitations"][0]
    assert inv["id"] == "inv-1"
    assert inv["code"] == "ABC123"
    assert inv["claimed"] is False


def test_powerhub_sensor_invitees_extra_attrs() -> None:
    desc = next(s for s in SENSORS if s.key == "invitees")
    sensor = PowerHubSensor(_make_coord(), desc)
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert attrs["count"] == 1
    assert attrs["invitees"][0]["name"] == "Alice"
    assert attrs["invitees"][0]["share_all_devices"] is True


# ── NotificationSensor entity ─────────────────────────────────────────────────

def _make_notif_coord(data: NotificationData | None = None) -> MagicMock:
    coord = MagicMock()
    coord.data = data
    return coord


def _make_notif_entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "notif-entry-id"
    entry.title = "My PowerHub"
    return entry


def test_notification_sensor_native_value_returns_body() -> None:
    data = NotificationData(
        title="Tariff change",
        body="Your tariff has changed.",
        notification_type="PRICE",
        created_ms=1700000000000,
        all_notifications=[],
    )
    sensor = NotificationSensor(_make_notif_coord(data), _make_notif_entry())
    assert sensor.native_value == "Your tariff has changed."


def test_notification_sensor_native_value_none_when_no_data() -> None:
    sensor = NotificationSensor(_make_notif_coord(None), _make_notif_entry())
    assert sensor.native_value is None


def test_notification_sensor_truncates_long_body() -> None:
    long_body = "x" * 300
    data = NotificationData(
        title="Test",
        body=long_body,
        notification_type="PRICE",
        created_ms=None,
        all_notifications=[],
    )
    sensor = NotificationSensor(_make_notif_coord(data), _make_notif_entry())
    value = sensor.native_value
    assert value is not None
    assert len(value) == 255
    assert value.endswith("...")


def test_notification_sensor_extra_attrs_basic() -> None:
    data = NotificationData(
        title="Alert",
        body="High power usage.",
        notification_type="POWER",
        created_ms=1700000000000,
        all_notifications=[
            {"title": "Alert", "body": "High power usage.", "type": "POWER", "created": 1700000000000}
        ],
    )
    sensor = NotificationSensor(_make_notif_coord(data), _make_notif_entry())
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert attrs["title"] == "Alert"
    assert attrs["type"] == "POWER"
    assert "created" in attrs
    assert len(attrs["all_notifications"]) == 1


def test_notification_sensor_extra_attrs_none_when_no_data() -> None:
    sensor = NotificationSensor(_make_notif_coord(None), _make_notif_entry())
    assert sensor.extra_state_attributes is None


def test_notification_sensor_extra_attrs_no_created_when_ms_none() -> None:
    data = NotificationData(
        title="Alert",
        body="msg",
        notification_type="PRICE",
        created_ms=None,
        all_notifications=[],
    )
    sensor = NotificationSensor(_make_notif_coord(data), _make_notif_entry())
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert "created" not in attrs


def test_notification_sensor_unique_id() -> None:
    sensor = NotificationSensor(_make_notif_coord(), _make_notif_entry())
    assert sensor._attr_unique_id == "notif-entry-id_latest_notification"
