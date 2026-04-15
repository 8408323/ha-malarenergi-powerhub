"""Mälarenergi PowerHub integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import PowerHubCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]
_RESOURCE_URL = "/local/malarenergi_powerhub/malarenergi-qr.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the QR web component as a frontend resource."""
    hass.http.register_static_path(
        "/local/malarenergi_powerhub",
        hass.config.path("custom_components/malarenergi_powerhub/www"),
        cache_headers=False,
    )
    add_extra_js_url(hass, _RESOURCE_URL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = PowerHubCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
