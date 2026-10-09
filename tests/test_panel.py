"""Tests for the optional sidebar panel and its settings websocket commands."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.malarenergi_powerhub import panel

MOD = "custom_components.malarenergi_powerhub.panel"
_set = inspect.unwrap(panel.ws_settings_set)  # past require_admin + async_response


def _hass(entries=()):
    hass = MagicMock()
    hass.data = {}
    hass.http.async_register_static_paths = AsyncMock()
    hass.config_entries.async_entries.return_value = list(entries)
    return hass


def _entry(options=None):
    entry = MagicMock()
    entry.options = options or {}
    return entry


async def test_setup_registers_once_and_honours_show_panel(tmp_path) -> None:
    (tmp_path / "panel.js").write_text("x")
    hass = _hass([_entry({"show_panel": False})])
    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock()) as reg,
        patch(f"{MOD}.websocket_api.async_register_command") as ws,
    ):
        await panel.async_setup_panel(hass)
        await panel.async_setup_panel(hass)  # second config entry: no-op
    reg.assert_awaited_once()
    assert reg.await_args.kwargs["sidebar_title"] is None
    assert reg.await_args.kwargs["module_url"].startswith(f"{panel.URL}/panel.js?v=")
    assert ws.call_count == 2


async def test_setup_without_entry_shows_panel(tmp_path) -> None:
    (tmp_path / "panel.js").write_text("x")
    hass = _hass()
    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock()) as reg,
        patch(f"{MOD}.websocket_api.async_register_command"),
    ):
        await panel.async_setup_panel(hass)
    assert reg.await_args.kwargs["sidebar_title"] == "PowerHub"


async def test_setup_skips_when_not_built(tmp_path) -> None:
    hass = _hass()
    with patch(f"{MOD}.WWW", tmp_path):
        await panel.async_setup_panel(hass)
    assert panel.KEY not in hass.data


def test_remove_panel_only_when_registered() -> None:
    hass = _hass()
    with patch(f"{MOD}.frontend.async_remove_panel") as rm:
        panel.async_remove_panel(hass)
        rm.assert_not_called()
        hass.data[panel.KEY] = True
        panel.async_remove_panel(hass)
        rm.assert_called_once()
    assert panel.KEY not in hass.data


def test_settings_get_returns_defaults_merged() -> None:
    conn = MagicMock()
    panel.ws_settings_get(_hass([_entry({"sources": ["wind"], "junk": 1})]), conn, {"id": 1})
    opts = conn.send_result.call_args.args[1]["options"]
    assert opts["sources"] == ["wind"] and opts["show_panel"] is True and "junk" not in opts
    panel.ws_settings_get(_hass(), conn, {"id": 2})
    assert conn.send_result.call_args.args[1]["options"] == panel.DEFAULT_OPTIONS


async def test_settings_set_validates_and_saves() -> None:
    entry = _entry({"other": "kept"})
    hass = _hass([entry])
    conn = MagicMock()
    msg = {
        "id": 1,
        "options": {
            "sources": ["solar", "v2g"],
            "has_ev": None,
            "production_power": "sensor.pv",
            "ev_power": 5,
            "battery_invert": "no",
            "x": 1,
        },
    }
    await _set(hass, conn, msg)
    saved = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert (
        saved["other"] == "kept" and saved["sources"] == ["solar", "v2g"] and saved["production_power"] == "sensor.pv"
    )
    assert saved["ev_power"] == "" and saved["battery_invert"] is False and "x" not in saved
    conn.send_result.assert_called_once()


async def test_settings_set_toggles_sidebar(tmp_path) -> None:
    (tmp_path / "panel.js").write_text("x")
    hass = _hass([_entry()])
    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.frontend.async_remove_panel") as rm,
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock()) as reg,
    ):
        await _set(hass, MagicMock(), {"id": 1, "options": {"show_panel": False}})
    rm.assert_called_once()
    assert reg.await_args.kwargs["sidebar_title"] is None


async def test_settings_set_without_entry_errors() -> None:
    conn = MagicMock()
    await _set(_hass(), conn, {"id": 1, "options": {}})
    conn.send_error.assert_called_once()


def test_legacy_booleans_migrate_into_sources() -> None:
    assert panel._options(_entry({"has_solar": True, "has_battery": False}))["sources"] == ["solar"]
    assert panel._options(_entry({"has_solar": False}))["sources"] == []
    assert panel._options(_entry())["sources"] is None  # never answered: panel follows the hub
    # an explicit list wins over the old booleans
    assert panel._options(_entry({"has_solar": True, "sources": ["wind"]}))["sources"] == ["wind"]


def test_sources_validation() -> None:
    assert panel._valid("sources", None)
    assert panel._valid("sources", ["solar", "battery", "wind", "generator", "v2g", "other"])
    assert not panel._valid("sources", ["nuclear"])
    assert not panel._valid("sources", "solar")


async def test_settings_set_drops_legacy_keys_after_migrating() -> None:
    entry = _entry({"has_solar": True, "has_battery": True, "keep": 1})
    hass = _hass([entry])
    await _set(hass, MagicMock(), {"id": 1, "options": {"show_panel": True}})
    saved = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert saved["sources"] == ["solar", "battery"] and saved["keep"] == 1
    assert "has_solar" not in saved and "has_battery" not in saved
