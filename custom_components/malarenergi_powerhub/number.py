"""Number platform — editable numeric facility attributes and power limits."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfArea, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PowerHubCoordinator, PowerHubData
from .api import FacilityAttributes, FacilityControl


@dataclass(frozen=True, kw_only=True)
class PowerHubNumberDescription(NumberEntityDescription):
    value_fn: Callable[[FacilityAttributes], float | int | None]
    attr_field: str


@dataclass(frozen=True, kw_only=True)
class PowerControlNumberDescription(NumberEntityDescription):
    value_fn: Callable[[FacilityControl], float | None]
    control_field: str


ATTRIBUTE_NUMBERS: tuple[PowerHubNumberDescription, ...] = (
    PowerHubNumberDescription(
        key="area",
        translation_key="area",
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
        translation_key="occupants",
        entity_category=EntityCategory.CONFIG,
        native_min_value=1,
        native_max_value=20,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda a: a.occupants,
        attr_field="occupants",
    ),
)

CONTROL_NUMBERS: tuple[PowerControlNumberDescription, ...] = (
    PowerControlNumberDescription(
        key="fuse_limit_set",
        translation_key="fuse_limit_set",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement="A",
        native_min_value=1,
        native_max_value=63,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda c: c.fuse_limit_a,
        control_field="fuse_limit_a",
    ),
    PowerControlNumberDescription(
        key="power_limit_set",
        translation_key="power_limit_set",
        entity_category=EntityCategory.CONFIG,
        device_class=None,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        native_min_value=0.1,
        native_max_value=100.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        value_fn=lambda c: c.power_limit_kw,
        control_field="power_limit_kw",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PowerHubCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = [
        PowerHubNumber(coordinator, desc) for desc in ATTRIBUTE_NUMBERS
    ]
    entities += [PowerControlNumber(coordinator, desc) for desc in CONTROL_NUMBERS]
    async_add_entities(entities)


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
        assert coordinator.config_entry is not None
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


class PowerControlNumber(CoordinatorEntity[PowerHubCoordinator], NumberEntity):
    _attr_has_entity_name = True
    entity_description: PowerControlNumberDescription

    def __init__(
        self,
        coordinator: PowerHubCoordinator,
        description: PowerControlNumberDescription,
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
    def native_value(self) -> float | None:
        ctrl = self.coordinator.data and self.coordinator.data.facility_control
        if ctrl is None:
            return None
        return self.entity_description.value_fn(ctrl)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_facility_control(
            **{self.entity_description.control_field: value}
        )
