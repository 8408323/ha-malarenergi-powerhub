"""Sensor platform for Mälarenergi PowerHub."""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, kw_only=True)
class PowerHubSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PowerHubData], float | str | bool | None]


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
        state_class=SensorStateClass.MEASUREMENT,
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
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PowerHubCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PowerHubSensor(coordinator, description) for description in SENSORS
    )


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
    def native_value(self) -> float | str | bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
