"""Binary sensor platform for Mälarenergi PowerHub facility attributes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PowerHubCoordinator, PowerHubData


@dataclass(frozen=True, kw_only=True)
class PowerHubBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[PowerHubData], bool | None]


BINARY_SENSORS: tuple[PowerHubBinarySensorDescription, ...] = (
    PowerHubBinarySensorDescription(
        key="has_solar",
        translation_key="has_solar",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.attributes.has_solar if d.attributes else None,
    ),
    PowerHubBinarySensorDescription(
        key="has_battery",
        translation_key="has_battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.attributes.has_battery if d.attributes else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PowerHubCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PowerHubBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class PowerHubBinarySensor(CoordinatorEntity[PowerHubCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    entity_description: PowerHubBinarySensorDescription

    def __init__(
        self,
        coordinator: PowerHubCoordinator,
        description: PowerHubBinarySensorDescription,
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
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
