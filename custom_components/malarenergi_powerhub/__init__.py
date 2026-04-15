"""Mälarenergi PowerHub integration for Home Assistant."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PowerHubApiClient
from .const import CONF_FACILITY_ID, CONF_TOKEN, DOMAIN, STATIC_URL
from .coordinator import PowerHubCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_CREATE_INVITATION = "create_invitation"
SERVICE_DELETE_INVITATION = "delete_invitation"

_CREATE_SCHEMA = vol.Schema({
    vol.Optional(CONF_FACILITY_ID): cv.string,
    vol.Optional("share_all_devices", default=True): cv.boolean,
})

_DELETE_SCHEMA = vol.Schema({
    vol.Required("invitation_id"): cv.string,
})


def _get_client(hass: HomeAssistant, facility_id: str | None) -> tuple[PowerHubApiClient, str]:
    """Return (client, facility_id) for the first matching config entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        fid = entry.data[CONF_FACILITY_ID]
        if facility_id is None or fid == facility_id:
            session = async_get_clientsession(hass)
            return PowerHubApiClient(session, entry.data[CONF_TOKEN]), fid
    raise ValueError(f"No config entry found for facility_id={facility_id!r}")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register static path for QR images served during config flow."""
    import os
    qr_dir = hass.config.path("custom_components", DOMAIN, "www")
    os.makedirs(qr_dir, exist_ok=True)
    try:
        hass.http.register_static_path(STATIC_URL, qr_dir, cache_headers=False)
    except RuntimeError:
        _LOGGER.debug("Static path %s already registered", STATIC_URL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = PowerHubCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_create_invitation(call: ServiceCall) -> None:
        facility_id = call.data.get(CONF_FACILITY_ID)
        share_all_devices = call.data.get("share_all_devices", True)
        try:
            client, fid = _get_client(hass, facility_id)
        except ValueError as err:
            _LOGGER.error("create_invitation service failed: %s", err)
            return
        result = await client.create_invitation(fid, share_all_devices=share_all_devices)
        _LOGGER.info(
            "Created invitation %s (code=%s, expires=%s)",
            result.invitation_id,
            result.code,
            result.expires,
        )

    async def handle_delete_invitation(call: ServiceCall) -> None:
        # Invitations are account-wide; any config entry's token is valid.
        invitation_id = call.data["invitation_id"]
        try:
            client, _ = _get_client(hass, None)
        except ValueError as err:
            _LOGGER.error("delete_invitation service failed: %s", err)
            return
        await client.delete_invitation(invitation_id)
        _LOGGER.info("Deleted invitation %s", invitation_id)

    if not hass.services.has_service(DOMAIN, SERVICE_CREATE_INVITATION):
        hass.services.async_register(
            DOMAIN, SERVICE_CREATE_INVITATION, handle_create_invitation,
            schema=_CREATE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_INVITATION):
        hass.services.async_register(
            DOMAIN, SERVICE_DELETE_INVITATION, handle_delete_invitation,
            schema=_DELETE_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_CREATE_INVITATION)
        hass.services.async_remove(DOMAIN, SERVICE_DELETE_INVITATION)
    return unload_ok
