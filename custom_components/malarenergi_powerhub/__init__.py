"""PowerHub integration for Home Assistant (Bitvis Power Flow energy companies)."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components.persistent_notification import async_create as pn_create
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PowerApiClient, PowerHubApiClient
from .const import CONF_FACILITY_ID, CONF_TOKEN, DOMAIN
from .coordinator import PowerHubCoordinator, device_info, provider_of
from .notifications_coordinator import NotificationsCoordinator
from .panel import async_remove_panel, async_setup_panel

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
]

SERVICE_CREATE_INVITATION = "create_invitation"
SERVICE_DELETE_INVITATION = "delete_invitation"

_CREATE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_FACILITY_ID): cv.string,
        vol.Optional("share_all_devices", default=True): cv.boolean,
    }
)

_DELETE_SCHEMA = vol.Schema(
    {
        vol.Required("invitation_id"): cv.string,
        vol.Optional(CONF_FACILITY_ID): cv.string,
    }
)


def _get_client(hass: HomeAssistant, facility_id: str | None) -> tuple[PowerHubApiClient, str]:
    """Return (client, facility_id) for the first matching config entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        fid = entry.data[CONF_FACILITY_ID]
        if facility_id is None or fid == facility_id:
            session = async_get_clientsession(hass)
            return PowerHubApiClient(session, entry.data[CONF_TOKEN], provider_of(entry)), fid
    raise ValueError(f"No config entry found for facility_id={facility_id!r}")


# Since HA 2026.8 every device belongs to one config entry and connections are
# per entry, so tagging our own device with the MAC can't collide with anyone's.
_DEVICE_PER_ENTRY = hasattr(dr.DeviceEntry, "config_entry_id")


def _refresh_invitations(hass: HomeAssistant) -> None:
    """Invitations are account-wide, so refresh every facility's coordinator (best-effort)."""
    for e in hass.config_entries.async_entries(DOMAIN):
        if coordinator := hass.data[DOMAIN].get(e.entry_id):
            hass.async_create_task(coordinator.async_request_refresh())


async def _async_link_hub(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Give our device the hub's MAC, which is how the core Bitvis Power Hub
    integration (local UDP) and router trackers identify the same hub.

    Runs before the platforms create our device, so on a first setup HA attaches
    our entities to an existing device with that MAC. Best-effort: the entities
    work without it.
    """
    client = PowerApiClient(async_get_clientsession(hass), entry.data[CONF_TOKEN])
    try:
        mac = (await client.get_device(entry.data[CONF_FACILITY_ID])).mac_address
    except Exception as err:  # noqa: BLE001 — any failure just skips the link
        _LOGGER.debug("PowerHub MAC lookup failed, not linking devices: %s", err)
        return
    if not mac:
        return
    connection = (dr.CONNECTION_NETWORK_MAC, dr.format_mac(mac))
    dev_reg = dr.async_get(hass)
    owner = dev_reg.async_get_device(connections={connection})
    if not _DEVICE_PER_ENTRY and owner and entry.entry_id not in owner.config_entries:
        # Older HA shares one device per MAC, and another integration (e.g. a
        # router's device tracker) already has it. get_or_create would allow the
        # collision and steal the MAC; leave both devices alone.
        _LOGGER.debug("PowerHub MAC %s already belongs to another device, not linking", mac)
        return
    dev_reg.async_get_or_create(config_entry_id=entry.entry_id, connections={connection}, **device_info(entry))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = PowerHubCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    await _async_link_hub(hass, entry)

    notifications_coordinator = NotificationsCoordinator(hass, entry)
    # Use async_refresh so a transient API error doesn't abort the whole entry setup.
    # The coordinator will retry on its normal schedule.
    await notifications_coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    hass.data[DOMAIN][f"{entry.entry_id}_notifications"] = notifications_coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_panel(hass)

    async def handle_create_invitation(call: ServiceCall) -> None:
        facility_id = call.data.get(CONF_FACILITY_ID)
        share_all_devices = call.data.get("share_all_devices", True)
        try:
            client, fid = _get_client(hass, facility_id)
        except ValueError as err:
            _LOGGER.error("create_invitation service failed: %s", err)
            return
        try:
            result = await client.create_invitation(fid, share_all_devices=share_all_devices)
        except Exception as err:
            _LOGGER.error("create_invitation API call failed: %s", err)
            raise HomeAssistantError(f"Failed to create invitation: {err}") from err
        _LOGGER.info(
            "Created invitation %s (code=%s, expires=%s)",
            result.invitation_id,
            result.code,
            result.expires,
        )
        # Show a persistent notification so the user can share the code
        pn_create(
            hass,
            message=(
                f"**Invitation code:** `{result.code}`\n\n"
                f"Invitation ID: `{result.invitation_id}`\n"
                f"Expires: {result.expires}\n\n"
                "Share this code with the person you want to invite. "
                "Use the `delete_invitation` service with the invitation ID to revoke access."
            ),
            title="PowerHub — Invitation Created",
            notification_id=f"powerhub_invitation_{result.invitation_id}",
        )
        _refresh_invitations(hass)

    async def handle_delete_invitation(call: ServiceCall) -> None:
        # Invitations are account-wide, but per energy company: with entries for
        # several companies, facility_id picks the one the invitation was made on.
        invitation_id = call.data["invitation_id"]
        try:
            client, _ = _get_client(hass, call.data.get(CONF_FACILITY_ID))
        except ValueError as err:
            _LOGGER.error("delete_invitation service failed: %s", err)
            return
        try:
            await client.delete_invitation(invitation_id)
        except Exception as err:
            _LOGGER.error("delete_invitation API call failed: %s", err)
            raise HomeAssistantError(f"Failed to delete invitation: {err}") from err
        _LOGGER.info("Deleted invitation %s", invitation_id)
        _refresh_invitations(hass)

    if not hass.services.has_service(DOMAIN, SERVICE_CREATE_INVITATION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CREATE_INVITATION,
            handle_create_invitation,
            schema=_CREATE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_INVITATION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_INVITATION,
            handle_delete_invitation,
            schema=_DELETE_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_notifications", None)
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_CREATE_INVITATION)
        hass.services.async_remove(DOMAIN, SERVICE_DELETE_INVITATION)
        async_remove_panel(hass)
    return unload_ok
