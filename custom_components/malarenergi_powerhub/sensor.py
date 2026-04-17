"""Sensor platform for Mälarenergi PowerHub."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PowerHubCoordinator, PowerHubData
from .notifications_coordinator import NotificationData, NotificationsCoordinator


@dataclass(frozen=True, kw_only=True)
class PowerHubSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PowerHubData], float | str | int | bool | None]


SENSORS: tuple[PowerHubSensorDescription, ...] = (
    # ── Energy metering ──────────────────────────────────────────────────
    PowerHubSensorDescription(
        key="import_today",
        translation_key="import_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d: d.consumption_today_kwh,
    ),
    PowerHubSensorDescription(
        key="export_today",
        translation_key="export_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d: d.production_today_kwh,
    ),
    PowerHubSensorDescription(
        key="spot_price",
        translation_key="spot_price",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="öre/kWh",
        suggested_display_precision=2,
        value_fn=lambda d: d.spot_price_now,
    ),
    # ── Real-time power (1-min resolution) ──────────────────────────────
    PowerHubSensorDescription(
        key="power_import",
        translation_key="power_import",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=3,
        value_fn=lambda d: round(d.current_power.power_import_kw, 3) if d.current_power else None,
    ),
    PowerHubSensorDescription(
        key="power_export",
        translation_key="power_export",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=3,
        value_fn=lambda d: round(d.current_power.power_export_kw, 3) if d.current_power else None,
    ),
    # ── Per-phase power and current ──────────────────────────────────────
    PowerHubSensorDescription(
        key="power_l1_import",
        translation_key="power_l1_import",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=3,
        value_fn=lambda d: round(d.current_power_phases.power_l1_import_kw, 3) if d.current_power_phases else None,
    ),
    PowerHubSensorDescription(
        key="power_l2_import",
        translation_key="power_l2_import",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=3,
        value_fn=lambda d: round(d.current_power_phases.power_l2_import_kw, 3) if d.current_power_phases else None,
    ),
    PowerHubSensorDescription(
        key="power_l3_import",
        translation_key="power_l3_import",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=3,
        value_fn=lambda d: round(d.current_power_phases.power_l3_import_kw, 3) if d.current_power_phases else None,
    ),
    PowerHubSensorDescription(
        key="power_l1_export",
        translation_key="power_l1_export",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=3,
        value_fn=lambda d: round(d.current_power_phases.power_l1_export_kw, 3) if d.current_power_phases else None,
    ),
    PowerHubSensorDescription(
        key="power_l2_export",
        translation_key="power_l2_export",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=3,
        value_fn=lambda d: round(d.current_power_phases.power_l2_export_kw, 3) if d.current_power_phases else None,
    ),
    PowerHubSensorDescription(
        key="power_l3_export",
        translation_key="power_l3_export",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=3,
        value_fn=lambda d: round(d.current_power_phases.power_l3_export_kw, 3) if d.current_power_phases else None,
    ),
    PowerHubSensorDescription(
        key="current_l1",
        translation_key="current_l1",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=lambda d: round(d.current_power_phases.current_l1_a, 2) if d.current_power_phases else None,
    ),
    PowerHubSensorDescription(
        key="current_l2",
        translation_key="current_l2",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=lambda d: round(d.current_power_phases.current_l2_a, 2) if d.current_power_phases else None,
    ),
    PowerHubSensorDescription(
        key="current_l3",
        translation_key="current_l3",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=lambda d: round(d.current_power_phases.current_l3_a, 2) if d.current_power_phases else None,
    ),
    # ── Device diagnostics ───────────────────────────────────────────────
    PowerHubSensorDescription(
        key="wifi_rssi",
        translation_key="wifi_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.diagnostics.wifi_rssi_dbm if d.diagnostics else None,
    ),
    PowerHubSensorDescription(
        key="sw_version",
        translation_key="sw_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.diagnostics.sw_version if d.diagnostics else None,
    ),
    PowerHubSensorDescription(
        key="han_port_state",
        translation_key="han_port_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.diagnostics.han_port_state if d.diagnostics else None,
    ),
    PowerHubSensorDescription(
        key="fuse_limit",
        translation_key="fuse_limit",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="A",
        value_fn=lambda d: d.facility_control.fuse_limit_a if d.facility_control else None,
    ),
    PowerHubSensorDescription(
        key="power_limit",
        translation_key="power_limit",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda d: d.facility_control.power_limit_kw if d.facility_control else None,
    ),
    PowerHubSensorDescription(
        key="fcr_enabled",
        translation_key="fcr_enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.fcr_status.fcrd_down_enabled if d.fcr_status else None,
    ),
    # ── Account / facility info (diagnostic) ────────────────────────────
    PowerHubSensorDescription(
        key="account_name",
        translation_key="account_name",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.profile.name if d.profile else None,
    ),
    PowerHubSensorDescription(
        key="customer_number",
        translation_key="customer_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.profile.customer_number if d.profile else None,
    ),
    PowerHubSensorDescription(
        key="facility_address",
        translation_key="facility_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            f"{d.facility_info.street} {d.facility_info.house_number}"
            if d.facility_info else None
        ),
    ),
    PowerHubSensorDescription(
        key="meter_id",
        translation_key="meter_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.facility_info.meter_id if d.facility_info else None,
    ),
    PowerHubSensorDescription(
        key="price_zone",
        translation_key="price_zone",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.facility_info.region if d.facility_info else None,
    ),
    PowerHubSensorDescription(
        key="agreement_number",
        translation_key="agreement_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.agreements[0].agreement_number if d.agreements else None,
    ),
    PowerHubSensorDescription(
        key="price_model",
        translation_key="price_model",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.agreements[0].price_model if d.agreements else None,
    ),
    PowerHubSensorDescription(
        key="uptime",
        translation_key="uptime",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="s",
        value_fn=lambda d: d.diagnostics.uptime_s if d.diagnostics else None,
    ),
    # ── Monthly insights ─────────────────────────────────────────────────
    PowerHubSensorDescription(
        key="avg_price_this_month",
        translation_key="avg_price_this_month",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="öre/kWh",
        suggested_display_precision=2,
        value_fn=lambda d: round(d.monthly_insights.your_average_price, 2)
            if d.monthly_insights and d.monthly_insights.your_average_price is not None else None,
    ),
    PowerHubSensorDescription(
        key="market_avg_price_this_month",
        translation_key="market_avg_price_this_month",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="öre/kWh",
        suggested_display_precision=2,
        value_fn=lambda d: round(d.monthly_insights.monthly_average_price, 2)
            if d.monthly_insights and d.monthly_insights.monthly_average_price is not None else None,
    ),
    PowerHubSensorDescription(
        key="consumption_ytd",
        translation_key="consumption_ytd",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda d: d.monthly_insights.current_year_value
            if d.monthly_insights else None,
    ),
    PowerHubSensorDescription(
        key="baseload_power",
        translation_key="baseload_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=3,
        value_fn=lambda d: d.monthly_insights.baseload_kw
            if d.monthly_insights else None,
    ),
    # ── Sharing (diagnostic) ─────────────────────────────────────────────
    PowerHubSensorDescription(
        key="active_invitations",
        translation_key="active_invitations",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.invitations),
    ),
    PowerHubSensorDescription(
        key="invitees",
        translation_key="invitees",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: ", ".join(
            inv.claimer_name for inv in d.invitees if inv.claimer_name
        ) or str(len(d.invitees)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PowerHubCoordinator = hass.data[DOMAIN][entry.entry_id]
    notifications_coordinator: NotificationsCoordinator = hass.data[DOMAIN][
        f"{entry.entry_id}_notifications"
    ]
    entities: list[SensorEntity] = [
        PowerHubSensor(coordinator, description) for description in SENSORS
    ]
    entities.append(NotificationSensor(notifications_coordinator, entry))
    async_add_entities(entities)


class PowerHubSensor(CoordinatorEntity[PowerHubCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: PowerHubSensorDescription

    def __init__(
        self,
        coordinator: PowerHubCoordinator,
        description: PowerHubSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        assert coordinator.config_entry is not None
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.config_entry.entry_id)},
            "name": "PowerHub",
            "manufacturer": "Bitvis / Mälarenergi",
            "model": "PowerHub (ESP32, Kaifa MA304)",
        }

    @property
    def native_value(self) -> float | str | int | bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.coordinator.data is None:
            return None
        key = self.entity_description.key

        if key == "active_invitations":
            return {
                "invitations": [
                    {
                        "id": inv.invitation_id,
                        "claimed": inv.claimed,
                        "expires": datetime.fromtimestamp(
                            inv.expires / 1000, tz=timezone.utc
                        ).isoformat() if inv.expires else None,
                        "created": datetime.fromtimestamp(
                            inv.created / 1000, tz=timezone.utc
                        ).isoformat() if inv.created else None,
                    }
                    for inv in self.coordinator.data.invitations
                ]
            }

        if key == "invitees":
            return {
                "count": len(self.coordinator.data.invitees),
                "invitees": [
                    {
                        "id": inv.invitee_id,
                        "name": inv.claimer_name,
                        "share_all_devices": inv.share_all_devices,
                    }
                    for inv in self.coordinator.data.invitees
                ],
            }

        return None


class NotificationSensor(CoordinatorEntity[NotificationsCoordinator], SensorEntity):
    """Sensor showing the most recent Mälarenergi push notification."""

    _attr_has_entity_name = True
    _attr_name = "Latest Notification"

    def __init__(
        self,
        coordinator: NotificationsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_latest_notification"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "PowerHub",
            "manufacturer": "Bitvis / Mälarenergi",
            "model": "PowerHub (ESP32, Kaifa MA304)",
        }

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        body = self.coordinator.data.body
        # HA state is limited to 255 characters
        if body and len(body) > 255:
            return body[:252] + "..."
        return body

    @property
    def extra_state_attributes(self) -> dict | None:
        data: NotificationData | None = self.coordinator.data
        if data is None:
            return None
        attrs: dict = {
            "title": data.title,
            "type": data.notification_type,
        }
        if data.created_ms:
            attrs["created"] = datetime.fromtimestamp(
                data.created_ms / 1000, tz=timezone.utc
            ).isoformat()
        attrs["all_notifications"] = [
            {
                "title": n.get("title"),
                "body": n.get("body"),
                "type": n.get("type"),
                "created": datetime.fromtimestamp(
                    n["created"] / 1000, tz=timezone.utc
                ).isoformat() if n.get("created") else None,
            }
            for n in data.all_notifications
        ]
        return attrs
