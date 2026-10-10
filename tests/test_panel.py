"""Tests for the optional sidebar panel and its settings websocket commands."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.malarenergi_powerhub import panel
from custom_components.malarenergi_powerhub.const import DOMAIN

MOD = "custom_components.malarenergi_powerhub.panel"
_set = inspect.unwrap(panel.ws_settings_set)  # past require_admin + async_response


def _hass(entries=(), running=None):
    """Entries in *running* (default: all) have a coordinator, i.e. are loaded."""
    hass = MagicMock()
    hass.data = {DOMAIN: {e.entry_id: MagicMock() for e in (entries if running is None else running)}}
    hass.http.async_register_static_paths = AsyncMock()
    hass.config_entries.async_entries.return_value = list(entries)
    return hass


def _entry(options=None, entry_id="eid-1"):
    entry = MagicMock()
    entry.entry_id = entry_id
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


async def test_setup_without_loaded_entry_registers_no_panel(tmp_path) -> None:
    (tmp_path / "panel.js").write_text("x")
    hass = _hass()
    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock()) as reg,
        patch(f"{MOD}.websocket_api.async_register_command"),
    ):
        await panel.async_setup_panel(hass)
    reg.assert_not_awaited()
    assert panel.KEY_PANEL not in hass.data


async def test_last_entry_unloading_during_registration_leaves_no_panel(tmp_path) -> None:
    (tmp_path / "panel.js").write_text("x")
    hass = _hass([_entry()])

    async def unload_meanwhile(*args, **kwargs):
        hass.data[DOMAIN].clear()

    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock(side_effect=unload_meanwhile)),
        patch(f"{MOD}.websocket_api.async_register_command"),
        patch(f"{MOD}.frontend.async_remove_panel") as rm,
    ):
        await panel.async_setup_panel(hass)
    rm.assert_called_once()
    assert panel.KEY_PANEL not in hass.data


async def test_settings_set_rejects_a_stale_entry() -> None:
    entry = _entry()
    hass = _hass([entry])
    conn = MagicMock()
    await _set(hass, conn, {"id": 1, "options": {"show_panel": False}, "entry_id": "eid-other"})
    conn.send_error.assert_called_once()
    assert conn.send_error.call_args.args[1] == "stale_entry"
    hass.config_entries.async_update_entry.assert_not_called()


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
        hass.data[panel.KEY_PANEL] = True
        panel.async_remove_panel(hass)
        rm.assert_called_once()
    assert panel.KEY_PANEL not in hass.data


def test_settings_get_returns_defaults_merged() -> None:
    conn = MagicMock()
    panel.ws_settings_get(_hass([_entry({"sources": ["wind"], "junk": 1})]), conn, {"id": 1})
    opts = conn.send_result.call_args.args[1]["options"]
    assert opts["sources"] == ["wind"] and opts["show_panel"] is True and "junk" not in opts
    assert conn.send_result.call_args.args[1]["entry_id"] == "eid-1"
    panel.ws_settings_get(_hass(), conn, {"id": 2})
    assert conn.send_result.call_args.args[1] == {"options": panel.DEFAULT_OPTIONS, "entry_id": None}


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
    entry = _entry()
    hass = _hass([entry])
    hass.config_entries.async_update_entry.side_effect = lambda e, options: setattr(e, "options", options)
    hass.data.update({panel.KEY: True, panel.KEY_PANEL: ("eid-1", True)})  # registered, shown
    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.frontend.async_remove_panel") as rm,
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock()) as reg,
    ):
        await _set(hass, MagicMock(), {"id": 1, "options": {"show_panel": False}})
        await _set(hass, MagicMock(), {"id": 2, "options": {"language": "sv"}})  # unrelated: no re-register
    rm.assert_called_once()
    reg.assert_awaited_once()
    assert reg.await_args.kwargs["sidebar_title"] is None
    assert hass.data[panel.KEY_PANEL] == ("eid-1", False)
    assert reg.await_args.kwargs["config"] == {"entry_id": "eid-1"}


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


def test_language_validation() -> None:
    assert all(panel._valid("language", c) for c in ("auto", "en", "sv", "nb", "da", "fi", "is"))
    assert not panel._valid("language", "de")
    assert not panel._valid("language", None)


async def test_settings_set_rejects_unknown_language() -> None:
    entry = _entry({"language": "fi"})
    hass = _hass([entry])
    await _set(hass, MagicMock(), {"id": 1, "options": {"language": "xx"}})
    assert hass.config_entries.async_update_entry.call_args.kwargs["options"]["language"] == "fi"
    await _set(hass, MagicMock(), {"id": 2, "options": {"language": "nb"}})
    assert hass.config_entries.async_update_entry.call_args.kwargs["options"]["language"] == "nb"


async def test_unload_and_reload_registers_static_path_once(tmp_path) -> None:
    # the static route and ws commands live for the whole HA run; only the sidebar entry comes and goes
    (tmp_path / "panel.js").write_text("x")
    hass = _hass([_entry()])
    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock()) as reg,
        patch(f"{MOD}.websocket_api.async_register_command") as ws,
        patch(f"{MOD}.frontend.async_remove_panel") as rm,
    ):
        await panel.async_setup_panel(hass)
        panel.async_remove_panel(hass)
        await panel.async_setup_panel(hass)
    hass.http.async_register_static_paths.assert_awaited_once()
    assert ws.call_count == 2
    rm.assert_called_once()
    assert reg.await_count == 2 and hass.data[panel.KEY_PANEL]


def test_settings_entry_is_first_loaded_one() -> None:
    off, on = _entry({"language": "fi"}, "off"), _entry({"language": "sv"}, "on")
    assert panel._entry(_hass([off, on], running=[on])) is on
    assert panel._entry(_hass([off], running=[])) is None


async def test_failed_registration_is_retried_on_next_setup(tmp_path) -> None:
    (tmp_path / "panel.js").write_text("x")
    hass = _hass([_entry()])
    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock(side_effect=[RuntimeError, None])) as reg,
        patch(f"{MOD}.websocket_api.async_register_command"),
    ):
        try:
            await panel.async_setup_panel(hass)
        except RuntimeError:
            pass
        assert panel.KEY_PANEL not in hass.data
        await panel.async_setup_panel(hass)
    assert reg.await_count == 2 and hass.data[panel.KEY_PANEL]


async def test_reconcile_follows_the_active_entry(tmp_path) -> None:
    """Concurrent startup / unload: show_panel follows whichever entry's settings currently apply."""
    (tmp_path / "panel.js").write_text("x")
    first, second = _entry({"show_panel": True}), _entry({"show_panel": False}, "eid-2")
    hass = _hass([first, second], running=[second])  # the later entry finished setting up first
    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock()) as reg,
        patch(f"{MOD}.websocket_api.async_register_command"),
        patch(f"{MOD}.frontend.async_remove_panel") as rm,
    ):
        await panel.async_setup_panel(hass)
        assert reg.await_args.kwargs["sidebar_title"] is None
        hass.data[DOMAIN]["eid-1"] = MagicMock()  # the first entry is up: its settings apply now
        await panel.async_setup_panel(hass)
        assert reg.await_args.kwargs["sidebar_title"] == "PowerHub"
        await panel.async_setup_panel(hass)  # nothing changed: no-op
    assert reg.await_count == 2 and rm.call_count == 1


async def test_concurrent_setups_register_once(tmp_path) -> None:
    import asyncio

    (tmp_path / "panel.js").write_text("x")
    hass = _hass([_entry()])
    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock()) as reg,
        patch(f"{MOD}.websocket_api.async_register_command") as ws,
    ):
        await asyncio.gather(panel.async_setup_panel(hass), panel.async_setup_panel(hass))
    hass.http.async_register_static_paths.assert_awaited_once()
    assert ws.call_count == 2 and reg.await_count == 1


async def test_reconcile_when_active_entry_changes_with_same_visibility(tmp_path) -> None:
    """Same show_panel, different active entry: re-register so the open panel reloads that entry's settings."""
    (tmp_path / "panel.js").write_text("x")
    first, second = _entry(), _entry(entry_id="eid-2")
    hass = _hass([first, second])
    with (
        patch(f"{MOD}.WWW", tmp_path),
        patch(f"{MOD}.panel_custom.async_register_panel", new=AsyncMock()) as reg,
        patch(f"{MOD}.websocket_api.async_register_command"),
        patch(f"{MOD}.frontend.async_remove_panel"),
    ):
        await panel.async_setup_panel(hass)
        hass.data[DOMAIN].pop("eid-1")
        await panel.async_setup_panel(hass)
    assert [c.kwargs["config"] for c in reg.await_args_list] == [{"entry_id": "eid-1"}, {"entry_id": "eid-2"}]


def test_grid_feed_validation() -> None:
    assert panel._valid("grid_feed", "overhead") and panel._valid("grid_feed", "underground")
    assert not panel._valid("grid_feed", "satellite") and not panel._valid("grid_feed", None)
    assert panel.DEFAULT_OPTIONS["grid_feed"] == "overhead"
