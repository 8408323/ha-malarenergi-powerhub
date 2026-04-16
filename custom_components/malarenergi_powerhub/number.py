"""Number platform — editable numeric facility attributes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfArea
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PowerHubCoordinator
from .api import FacilityAttributes


@dataclass(frozen=True, kw_only=True)
class PowerHubNumberDescription(NumberEntityDescription):
    value_fn: Callable[[FacilityAttributes], float | int | None]
    attr_field: str           # FacilityAttributes field name for writing


NUMBERS: tuple[PowerHubNumberDescription, ...] = (
    PowerHubNumberDescription(
        key="area",
        name="Area",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        native_min_value=1,
        native_max_value=2000,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda a: a.area,
        attr_field="area",
    ),
    PowerHubNumberDescription(
        key="occupants",
        name="Occupants",
        entity_category=EntityCategory.CONFIG,
        native_min_value=1,
        native_max_value=20,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda a: a.occupants,
        attr_field="occupants",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PowerHubCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PowerHubNumber(coordinator, desc) for desc in NUMBERS
    )


class PowerHubNumber(CoordinatorEntity[PowerHubCoordinator], NumberEntity):
    _attr_has_entity_name = True
    entity_description: PowerHubNumberDescription

    def __init__(
        self,
        coordinator: PowerHubCoordinator,
        description: PowerHubNumberDescription,
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
    def native_value(self) -> float | None:
        attrs = self.coordinator.data and self.coordinator.data.attributes
        if attrs is None:
            return None
        return self.entity_description.value_fn(attrs)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_attributes(
            **{self.entity_description.attr_field: int(value)}
        )
