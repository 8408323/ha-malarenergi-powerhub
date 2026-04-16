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
from homeassistant.const import EntityCategory, UnitOfEnergy
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
        name="Import Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d: d.consumption_today_kwh,
    ),
    PowerHubSensorDescription(
        key="export_today",
        name="Export Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d: d.production_today_kwh,
    ),
    PowerHubSensorDescription(
        key="spot_price",
        name="Spot Price",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="öre/kWh",
        suggested_display_precision=2,
        value_fn=lambda d: d.spot_price_now,
    ),
    # ── Facility attributes (diagnostic) ─────────────────────────────────
    PowerHubSensorDescription(
        key="heating_type",
        name="Heating Type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.attributes.heating_type if d.attributes else None,
    ),
    PowerHubSensorDescription(
        key="fuse_size",
        name="Fuse Size",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="A",
        value_fn=lambda d: d.attributes.fuse_size if d.attributes else None,
    ),
    PowerHubSensorDescription(
        key="area",
        name="Area",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="m²",
        value_fn=lambda d: d.attributes.area if d.attributes else None,
    ),
    PowerHubSensorDescription(
        key="facility_type",
        name="Facility Type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.attributes.facility_type if d.attributes else None,
    ),
    # ── Sharing (diagnostic) ─────────────────────────────────────────────
    PowerHubSensorDescription(
        key="active_invitations",
        name="Active Invitations",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.invitations),
    ),
    PowerHubSensorDescription(
        key="invitees",
        name="Invitees",
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
    _attr_force_update = True
    entity_description: PowerHubSensorDescription

    def __init__(
        self,
        coordinator: PowerHubCoordinator,
        description: PowerHubSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
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
