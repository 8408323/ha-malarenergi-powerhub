"""Select platform — editable enum facility attributes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PowerHubCoordinator
from .api import FacilityAttributes

# Known fuse sizes (Ampere)
FUSE_OPTIONS = ["A10", "A16", "A20", "A25", "A32", "A35", "A50", "A63"]

# Known heating types (from API observation)
HEATING_TYPE_OPTIONS = [
    "DISTRICT_HEATING",
    "ELECTRIC",
    "HEATING_PUMP",
    "GAS",
    "OIL",
    "WOOD",
    "NONE",
]

# Known facility types
FACILITY_TYPE_OPTIONS = [
    "VILLA",
    "APARTMENT",
    "TOWNHOUSE",
    "CABIN",
    "OTHER",
]

# Known EV charger types
EV_TYPE_OPTIONS = [
    "NONE",
    "ONE_PHASE",
    "THREE_PHASE",
]


@dataclass(frozen=True, kw_only=True)
class PowerHubSelectDescription(SelectEntityDescription):
    value_fn: Callable[[FacilityAttributes], str | None]
    attr_field: str
    # Converts the selected option string to the FacilityAttributes field value.
    # Default is identity (str→str); fuse_size overrides to parse "A20" → 20 (int).
    to_attr_value: Callable[[str], object] = lambda v: v


def _fuse_to_attr(v: str) -> int:
    try:
        return int(v.lstrip("Aa"))
    except ValueError:
        return 20


SELECTS: tuple[PowerHubSelectDescription, ...] = (
    PowerHubSelectDescription(
        key="fuse_size",
        translation_key="fuse_size",
        entity_category=EntityCategory.CONFIG,
        options=FUSE_OPTIONS,
        value_fn=lambda a: f"A{a.fuse_size}" if a.fuse_size else None,
        attr_field="fuse_size",
        to_attr_value=_fuse_to_attr,
    ),
    PowerHubSelectDescription(
        key="heating_type",
        translation_key="heating_type",
        entity_category=EntityCategory.CONFIG,
        options=HEATING_TYPE_OPTIONS,
        value_fn=lambda a: a.heating_type or None,
        attr_field="heating_type",
    ),
    PowerHubSelectDescription(
        key="facility_type",
        translation_key="facility_type",
        entity_category=EntityCategory.CONFIG,
        options=FACILITY_TYPE_OPTIONS,
        value_fn=lambda a: a.facility_type or None,
        attr_field="facility_type",
    ),
    PowerHubSelectDescription(
        key="ev_type",
        translation_key="ev_type",
        entity_category=EntityCategory.CONFIG,
        options=EV_TYPE_OPTIONS,
        value_fn=lambda a: a.ev_type or "NONE",
        attr_field="ev_type",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PowerHubCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PowerHubSelect(coordinator, desc) for desc in SELECTS
    )


class PowerHubSelect(CoordinatorEntity[PowerHubCoordinator], SelectEntity):
    _attr_has_entity_name = True
    entity_description: PowerHubSelectDescription

    def __init__(
        self,
        coordinator: PowerHubCoordinator,
        description: PowerHubSelectDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_options = list(description.options)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.config_entry.entry_id)},
            "name": "PowerHub",
            "manufacturer": "Bitvis / Mälarenergi",
            "model": "PowerHub (ESP32, Kaifa MA304)",
        }

    @property
    def current_option(self) -> str | None:
        attrs = self.coordinator.data and self.coordinator.data.attributes
        if attrs is None:
            return None
        val = self.entity_description.value_fn(attrs)
        # Return None (unavailable) if the value isn't in the options list
        if val not in self._attr_options:
            return None
        return val

    async def async_select_option(self, option: str) -> None:
        attr_value = self.entity_description.to_attr_value(option)
        await self.coordinator.async_update_attributes(
            **{self.entity_description.attr_field: attr_value}
        )
