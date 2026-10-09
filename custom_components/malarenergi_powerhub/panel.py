"""Optional sidebar dashboard (frontend/ built to www/panel.js) and its settings websocket commands."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

WWW = Path(__file__).parent / "www"
URL = f"/{DOMAIN}_static"
PANEL = "powerhub"
KEY = f"{DOMAIN}_panel"  # static path + websocket commands registered (once per HA run)

# Panel settings live in the (first) config entry's options so they follow the user across devices.
# sources / has_ev: None = not answered yet, the panel then follows the integration's has_solar/has_battery/ev_type.
# Entity fields are optional extras the PowerHub can't measure itself; "" means not configured.
SOURCES = ("solar", "battery", "wind", "generator", "v2g", "other")  # local sources export can come from
LEGACY = ("has_solar", "has_battery")  # pre-"sources" booleans, migrated on read
LANGS = ("auto", "en", "sv", "nb", "da", "fi", "is")  # auto = follow the Home Assistant user's language
DEFAULT_OPTIONS: dict = {
    "show_panel": True,
    "language": "auto",
    "sources": None,
    "has_ev": None,  # plain EV charger (consumption only); bidirectional is the "v2g" source
    "production_power": "",
    "battery_power": "",
    "battery_soc": "",
    "battery_invert": False,  # some inverters report + as charging; the panel expects + = discharging
    "ev_power": "",
}


def _entry(hass: HomeAssistant):
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def _options(entry) -> dict:
    stored = entry.options or {}
    opts = {**DEFAULT_OPTIONS, **{k: v for k, v in stored.items() if k in DEFAULT_OPTIONS}}
    if opts["sources"] is None and any(stored.get(k) is not None for k in LEGACY):
        opts["sources"] = [k[4:] for k in LEGACY if stored.get(k)]
    return opts


def _valid(key: str, value) -> bool:
    default = DEFAULT_OPTIONS[key]
    if key == "language":
        return value in LANGS
    if key == "sources":
        return value is None or (isinstance(value, list) and all(v in SOURCES for v in value))
    if isinstance(default, str):
        return isinstance(value, str)
    return isinstance(value, bool) or (default is None and value is None)


async def _register(hass: HomeAssistant, show: bool) -> None:
    v = int((WWW / "panel.js").stat().st_mtime)
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="malarenergi-powerhub-panel",
        frontend_url_path=PANEL,
        module_url=f"{URL}/panel.js?v={v}",
        # hidden = no sidebar entry, but /powerhub still opens it (so it can be switched back on)
        sidebar_title="PowerHub" if show else None,
        sidebar_icon="mdi:home-lightning-bolt-outline",
        require_admin=False,
        config={},
    )


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Register the panel once; later config entries reuse it."""
    if hass.data.get(KEY) or not (WWW / "panel.js").exists():
        return
    hass.data[KEY] = True
    await hass.http.async_register_static_paths([StaticPathConfig(URL, str(WWW), cache_headers=False)])
    websocket_api.async_register_command(hass, ws_settings_get)
    websocket_api.async_register_command(hass, ws_settings_set)
    entry = _entry(hass)
    await _register(hass, _options(entry)["show_panel"] if entry else True)


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    """Drop the sidebar entry once the last config entry is gone (commands stay registered, harmlessly)."""
    if hass.data.pop(KEY, None):
        frontend.async_remove_panel(hass, PANEL, warn_if_unknown=False)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/get"})
@callback
def ws_settings_get(hass, connection, msg):
    entry = _entry(hass)
    connection.send_result(msg["id"], {"options": _options(entry) if entry else DEFAULT_OPTIONS})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/set", vol.Required("options"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_settings_set(hass, connection, msg):
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "PowerHub is not set up")
        return
    old = _options(entry)
    clean = {k: v for k, v in msg["options"].items() if k in DEFAULT_OPTIONS and _valid(k, v)}
    new = {**old, **clean}
    kept = {k: v for k, v in entry.options.items() if k not in LEGACY}  # migrated into sources
    hass.config_entries.async_update_entry(entry, options={**kept, **new})
    if new["show_panel"] != old["show_panel"]:
        frontend.async_remove_panel(hass, PANEL, warn_if_unknown=False)
        await _register(hass, new["show_panel"])
    connection.send_result(msg["id"], {"options": new})
