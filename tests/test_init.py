"""Tests for malarenergi_powerhub __init__.py.

Covers _get_client, async_setup_entry, async_unload_entry, and the
handle_create_invitation / handle_delete_invitation service handlers.
All HA runtime dependencies are replaced with lightweight mocks.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.malarenergi_powerhub import (
    SERVICE_CREATE_INVITATION,
    SERVICE_DELETE_INVITATION,
    _get_client,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.malarenergi_powerhub.const import (
    CONF_FACILITY_ID,
    CONF_TOKEN,
    DOMAIN,
)


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_entry(
    facility_id: str, token: str = "tok", entry_id: str = "eid-1"
) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {CONF_FACILITY_ID: facility_id, CONF_TOKEN: token}
    return entry


def _make_setup_hass() -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.services.has_service.return_value = False
    hass.services.async_register = MagicMock()
    hass.services.async_remove = MagicMock()
    hass.async_create_task = MagicMock()
    return hass


def _get_registered_handler(hass: MagicMock, service_name: str):
    """Extract the handler registered for *service_name*."""
    for c in hass.services.async_register.call_args_list:
        if c.args[1] == service_name:
            return c.args[2]
    raise AssertionError(f"Service {service_name!r} not registered")


async def _setup_and_get_handlers(
    hass: MagicMock,
    entry: MagicMock,
    coord: MagicMock,
    notif: MagicMock,
):
    with (
        patch(
            "custom_components.malarenergi_powerhub.PowerHubCoordinator",
            return_value=coord,
        ),
        patch(
            "custom_components.malarenergi_powerhub.NotificationsCoordinator",
            return_value=notif,
        ),
    ):
        await async_setup_entry(hass, entry)
    create_hdl = _get_registered_handler(hass, SERVICE_CREATE_INVITATION)
    delete_hdl = _get_registered_handler(hass, SERVICE_DELETE_INVITATION)
    return create_hdl, delete_hdl


def _make_coordinators() -> tuple[MagicMock, MagicMock]:
    coord = MagicMock()
    coord.async_config_entry_first_refresh = AsyncMock()
    coord.async_request_refresh = MagicMock(return_value=None)
    notif = MagicMock()
    notif.async_refresh = AsyncMock()
    return coord, notif


# ── _get_client ────────────────────────────────────────────────────────────────


def test_get_client_returns_client_for_matching_facility_id() -> None:
    entry = _make_entry("fac-1", "tok-1")
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    with patch(
        "custom_components.malarenergi_powerhub.async_get_clientsession",
        return_value=MagicMock(),
    ):
        _client, fid = _get_client(hass, "fac-1")
    assert fid == "fac-1"


def test_get_client_with_none_facility_id_returns_first_entry() -> None:
    e1 = _make_entry("fac-1", "tok-1")
    e2 = _make_entry("fac-2", "tok-2")
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [e1, e2]
    with patch(
        "custom_components.malarenergi_powerhub.async_get_clientsession",
        return_value=MagicMock(),
    ):
        _client, fid = _get_client(hass, None)
    assert fid == "fac-1"


def test_get_client_skips_non_matching_and_finds_second() -> None:
    e1 = _make_entry("fac-1", "tok-1")
    e2 = _make_entry("fac-2", "tok-2")
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [e1, e2]
    with patch(
        "custom_components.malarenergi_powerhub.async_get_clientsession",
        return_value=MagicMock(),
    ):
        _client, fid = _get_client(hass, "fac-2")
    assert fid == "fac-2"


def test_get_client_raises_when_no_entries_exist() -> None:
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = []
    with pytest.raises(ValueError, match="No config entry found"):
        _get_client(hass, "fac-missing")


def test_get_client_raises_when_facility_id_never_matches() -> None:
    entry = _make_entry("fac-1")
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    with pytest.raises(ValueError, match="No config entry found"):
        _get_client(hass, "fac-other")


# ── async_setup_entry ──────────────────────────────────────────────────────────


async def test_async_setup_entry_returns_true() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1")
    coord, notif = _make_coordinators()
    with (
        patch(
            "custom_components.malarenergi_powerhub.PowerHubCoordinator",
            return_value=coord,
        ),
        patch(
            "custom_components.malarenergi_powerhub.NotificationsCoordinator",
            return_value=notif,
        ),
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    coord.async_config_entry_first_refresh.assert_awaited_once()
    notif.async_refresh.assert_awaited_once()


async def test_async_setup_entry_stores_coordinators() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1", entry_id="eid-1")
    coord, notif = _make_coordinators()
    with (
        patch(
            "custom_components.malarenergi_powerhub.PowerHubCoordinator",
            return_value=coord,
        ),
        patch(
            "custom_components.malarenergi_powerhub.NotificationsCoordinator",
            return_value=notif,
        ),
    ):
        await async_setup_entry(hass, entry)

    assert hass.data[DOMAIN]["eid-1"] is coord
    assert hass.data[DOMAIN]["eid-1_notifications"] is notif


async def test_async_setup_entry_registers_both_services() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1")
    coord, notif = _make_coordinators()
    with (
        patch(
            "custom_components.malarenergi_powerhub.PowerHubCoordinator",
            return_value=coord,
        ),
        patch(
            "custom_components.malarenergi_powerhub.NotificationsCoordinator",
            return_value=notif,
        ),
    ):
        await async_setup_entry(hass, entry)

    registered = {c.args[1] for c in hass.services.async_register.call_args_list}
    assert SERVICE_CREATE_INVITATION in registered
    assert SERVICE_DELETE_INVITATION in registered


async def test_async_setup_entry_skips_register_when_services_exist() -> None:
    hass = _make_setup_hass()
    hass.services.has_service.return_value = True
    entry = _make_entry("fac-1")
    coord, notif = _make_coordinators()
    with (
        patch(
            "custom_components.malarenergi_powerhub.PowerHubCoordinator",
            return_value=coord,
        ),
        patch(
            "custom_components.malarenergi_powerhub.NotificationsCoordinator",
            return_value=notif,
        ),
    ):
        await async_setup_entry(hass, entry)

    hass.services.async_register.assert_not_called()


# ── async_unload_entry ─────────────────────────────────────────────────────────


async def test_async_unload_entry_pops_coordinators_on_success() -> None:
    hass = _make_setup_hass()
    hass.data = {
        DOMAIN: {"eid-1": "coord", "eid-1_notifications": "notif", "eid-2": "other"}
    }
    entry = _make_entry("fac-1", entry_id="eid-1")

    result = await async_unload_entry(hass, entry)

    assert result is True
    assert "eid-1" not in hass.data[DOMAIN]
    assert "eid-1_notifications" not in hass.data[DOMAIN]


async def test_async_unload_entry_does_not_pop_on_failure() -> None:
    hass = _make_setup_hass()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    hass.data = {DOMAIN: {"eid-1": "coord"}}
    entry = _make_entry("fac-1", entry_id="eid-1")

    result = await async_unload_entry(hass, entry)

    assert result is False
    assert "eid-1" in hass.data[DOMAIN]


async def test_async_unload_entry_removes_services_when_domain_empty() -> None:
    hass = _make_setup_hass()
    hass.data = {DOMAIN: {"eid-1": "coord"}}
    entry = _make_entry("fac-1", entry_id="eid-1")

    await async_unload_entry(hass, entry)

    assert hass.services.async_remove.call_count == 2
    removed = {c.args[1] for c in hass.services.async_remove.call_args_list}
    assert SERVICE_CREATE_INVITATION in removed
    assert SERVICE_DELETE_INVITATION in removed


async def test_async_unload_entry_keeps_services_when_entries_remain() -> None:
    hass = _make_setup_hass()
    hass.data = {DOMAIN: {"eid-1": "coord", "eid-2": "coord2"}}
    entry = _make_entry("fac-1", entry_id="eid-1")

    await async_unload_entry(hass, entry)

    hass.services.async_remove.assert_not_called()


# ── handle_create_invitation ───────────────────────────────────────────────────


async def test_handle_create_invitation_creates_persistent_notification() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1", entry_id="eid-1")
    coord, notif = _make_coordinators()

    create_hdl, _ = await _setup_and_get_handlers(hass, entry, coord, notif)

    inv_result = MagicMock()
    inv_result.invitation_id = "inv-abc"
    inv_result.code = "CODE123"
    inv_result.expires = "2026-12-31"
    mock_client = MagicMock()
    mock_client.create_invitation = AsyncMock(return_value=inv_result)

    service_call = MagicMock()
    service_call.data = {CONF_FACILITY_ID: "fac-1", "share_all_devices": True}

    with (
        patch(
            "custom_components.malarenergi_powerhub._get_client",
            return_value=(mock_client, "fac-1"),
        ),
        patch("custom_components.malarenergi_powerhub.pn_create") as mock_pn,
    ):
        await create_hdl(service_call)

    mock_pn.assert_called_once()
    # The notification message should contain the invitation code
    notification_msg = (
        mock_pn.call_args.kwargs.get("message") or mock_pn.call_args.args[1]
    )
    assert "CODE123" in notification_msg


async def test_handle_create_invitation_logs_error_on_missing_entry() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1", entry_id="eid-1")
    coord, notif = _make_coordinators()

    create_hdl, _ = await _setup_and_get_handlers(hass, entry, coord, notif)

    service_call = MagicMock()
    service_call.data = {}

    with patch(
        "custom_components.malarenergi_powerhub._get_client",
        side_effect=ValueError("no entry"),
    ):
        # Should not raise — logs error and returns None
        result = await create_hdl(service_call)

    assert result is None


async def test_handle_create_invitation_raises_ha_error_on_api_failure() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1", entry_id="eid-1")
    coord, notif = _make_coordinators()

    create_hdl, _ = await _setup_and_get_handlers(hass, entry, coord, notif)

    mock_client = MagicMock()
    mock_client.create_invitation = AsyncMock(side_effect=RuntimeError("api down"))

    service_call = MagicMock()
    service_call.data = {}

    with (
        patch(
            "custom_components.malarenergi_powerhub._get_client",
            return_value=(mock_client, "fac-1"),
        ),
        pytest.raises(HomeAssistantError, match="Failed to create invitation"),
    ):
        await create_hdl(service_call)


async def test_handle_create_invitation_schedules_coordinator_refresh() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1", entry_id="eid-1")
    coord, notif = _make_coordinators()

    create_hdl, _ = await _setup_and_get_handlers(hass, entry, coord, notif)

    inv_result = MagicMock()
    inv_result.invitation_id = "inv-1"
    inv_result.code = "CODE"
    inv_result.expires = "2027-01-01"
    mock_client = MagicMock()
    mock_client.create_invitation = AsyncMock(return_value=inv_result)

    service_call = MagicMock()
    service_call.data = {}

    with (
        patch(
            "custom_components.malarenergi_powerhub._get_client",
            return_value=(mock_client, "fac-1"),
        ),
        patch("custom_components.malarenergi_powerhub.pn_create"),
    ):
        await create_hdl(service_call)

    # async_create_task should have been called with the refresh coroutine
    hass.async_create_task.assert_called_once()


# ── handle_delete_invitation ───────────────────────────────────────────────────


async def test_handle_delete_invitation_calls_api() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1", entry_id="eid-1")
    coord, notif = _make_coordinators()

    _, delete_hdl = await _setup_and_get_handlers(hass, entry, coord, notif)

    mock_client = MagicMock()
    mock_client.delete_invitation = AsyncMock()

    service_call = MagicMock()
    service_call.data = {"invitation_id": "inv-abc"}

    with patch(
        "custom_components.malarenergi_powerhub._get_client",
        return_value=(mock_client, "fac-1"),
    ):
        await delete_hdl(service_call)

    mock_client.delete_invitation.assert_awaited_once_with("inv-abc")


async def test_handle_delete_invitation_logs_error_on_missing_entry() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1", entry_id="eid-1")
    coord, notif = _make_coordinators()

    _, delete_hdl = await _setup_and_get_handlers(hass, entry, coord, notif)

    service_call = MagicMock()
    service_call.data = {"invitation_id": "inv-abc"}

    with patch(
        "custom_components.malarenergi_powerhub._get_client",
        side_effect=ValueError("no entry"),
    ):
        result = await delete_hdl(service_call)

    assert result is None


async def test_handle_delete_invitation_raises_ha_error_on_api_failure() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1", entry_id="eid-1")
    coord, notif = _make_coordinators()

    _, delete_hdl = await _setup_and_get_handlers(hass, entry, coord, notif)

    mock_client = MagicMock()
    mock_client.delete_invitation = AsyncMock(side_effect=RuntimeError("network error"))

    service_call = MagicMock()
    service_call.data = {"invitation_id": "inv-abc"}

    with (
        patch(
            "custom_components.malarenergi_powerhub._get_client",
            return_value=(mock_client, "fac-1"),
        ),
        pytest.raises(HomeAssistantError, match="Failed to delete invitation"),
    ):
        await delete_hdl(service_call)


async def test_handle_delete_invitation_schedules_coordinator_refresh() -> None:
    hass = _make_setup_hass()
    entry = _make_entry("fac-1", entry_id="eid-1")
    coord, notif = _make_coordinators()

    _, delete_hdl = await _setup_and_get_handlers(hass, entry, coord, notif)

    mock_client = MagicMock()
    mock_client.delete_invitation = AsyncMock()

    service_call = MagicMock()
    service_call.data = {"invitation_id": "inv-abc"}

    with patch(
        "custom_components.malarenergi_powerhub._get_client",
        return_value=(mock_client, "fac-1"),
    ):
        await delete_hdl(service_call)

    hass.async_create_task.assert_called_once()
