"""Switch platform — toggleable boolean facility attributes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PowerHubCoordinator
from .api import FacilityAttributes


@dataclass(frozen=True, kw_only=True)
class PowerHubSwitchDescription(SwitchEntityDescription):
    value_fn: Callable[[FacilityAttributes], bool | None]
    attr_field: str


SWITCHES: tuple[PowerHubSwitchDescription, ...] = (
    PowerHubSwitchDescription(
        key="has_solar",
        translation_key="has_solar",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda a: a.has_solar,
        attr_field="has_solar",
    ),
    PowerHubSwitchDescription(
        key="has_battery",
        translation_key="has_battery",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda a: a.has_battery,
        attr_field="has_battery",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PowerHubCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PowerHubSwitch(coordinator, desc) for desc in SWITCHES
    )


class PowerHubSwitch(CoordinatorEntity[PowerHubCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    entity_description: PowerHubSwitchDescription

    def __init__(
        self,
        coordinator: PowerHubCoordinator,
        description: PowerHubSwitchDescription,
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
        attrs = self.coordinator.data and self.coordinator.data.attributes
        if attrs is None:
            return None
        return self.entity_description.value_fn(attrs)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_update_attributes(
            **{self.entity_description.attr_field: True}
        )

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_update_attributes(
            **{self.entity_description.attr_field: False}
        )
