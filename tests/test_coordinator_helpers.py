"""Tests for pure helper functions in coordinator.py.

The coordinator itself depends on HomeAssistant runtime (hass, ConfigEntry).
These tests cover only the module-level helpers that can run standalone.
"""

from __future__ import annotations

import zoneinfo
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import ClientResponseError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.malarenergi_powerhub.api import PowerApiClient, PowerHubApiClient
from custom_components.malarenergi_powerhub.const import CONF_FACILITY_ID, CONF_TOKEN
from custom_components.malarenergi_powerhub.coordinator import (
    PowerHubCoordinator,
    _day_start_ms,
    _now_ms,
    _optional,
)
from custom_components.malarenergi_powerhub.notifications_coordinator import (
    NotificationsCoordinator,
)

_STHLM = zoneinfo.ZoneInfo("Europe/Stockholm")


def test_day_start_ms_returns_midnight_stockholm_in_summer() -> None:
    """In summer, Stockholm is CEST (UTC+2). Midnight local is 22:00 UTC prior day."""
    # 2026-07-15 14:30 Stockholm (CEST, UTC+2)
    fake_now = datetime(2026, 7, 15, 14, 30, 0, tzinfo=_STHLM)
    with patch("custom_components.malarenergi_powerhub.coordinator.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result_ms = _day_start_ms()

    expected = datetime(2026, 7, 15, 0, 0, 0, tzinfo=_STHLM)
    assert result_ms == int(expected.timestamp() * 1000)
    # Sanity: the returned instant corresponds to 22:00 UTC the previous day
    assert datetime.fromtimestamp(result_ms / 1000, tz=timezone.utc) == datetime(
        2026, 7, 14, 22, 0, 0, tzinfo=timezone.utc
    )


def test_day_start_ms_returns_midnight_stockholm_in_winter() -> None:
    """In winter, Stockholm is CET (UTC+1). Midnight local is 23:00 UTC prior day."""
    fake_now = datetime(2026, 1, 15, 14, 30, 0, tzinfo=_STHLM)
    with patch("custom_components.malarenergi_powerhub.coordinator.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result_ms = _day_start_ms()

    expected = datetime(2026, 1, 15, 0, 0, 0, tzinfo=_STHLM)
    assert result_ms == int(expected.timestamp() * 1000)
    assert datetime.fromtimestamp(result_ms / 1000, tz=timezone.utc) == datetime(
        2026, 1, 14, 23, 0, 0, tzinfo=timezone.utc
    )


def test_day_start_ms_is_multiple_of_1000() -> None:
    """Midnight has no fractional seconds → ms value ends in 000."""
    assert _day_start_ms() % 1000 == 0


def test_now_ms_is_recent_utc_timestamp() -> None:
    """_now_ms returns milliseconds since epoch, close to actual now."""
    before = int(datetime.now(timezone.utc).timestamp() * 1000)
    value = _now_ms()
    after = int(datetime.now(timezone.utc).timestamp() * 1000)
    assert before <= value <= after


def test_now_ms_is_greater_than_day_start_ms_during_normal_day() -> None:
    """After midnight Stockholm, _now_ms should exceed _day_start_ms."""
    # This is only false in the first millisecond of the day; in practice safe.
    assert _now_ms() >= _day_start_ms()


# ── _optional ────────────────────────────────────────────────────────────────


async def test_optional_returns_value_on_success() -> None:
    async def _coro():
        return "ok"

    assert await _optional(_coro(), "ep") == "ok"


async def test_optional_404_returns_none() -> None:
    async def _coro():
        raise ClientResponseError(None, (), status=404)

    assert await _optional(_coro(), "ep") is None


async def test_optional_404_returns_custom_default() -> None:
    async def _coro():
        raise ClientResponseError(None, (), status=404)

    assert await _optional(_coro(), "ep", default=42) == 42


async def test_optional_non_404_reraises() -> None:
    async def _coro():
        raise ClientResponseError(None, (), status=500)

    with pytest.raises(ClientResponseError):
        await _optional(_coro(), "ep")


# ── PowerHubCoordinator.__init__ ──────────────────────────────────────────────


def test_power_hub_coordinator_init_sets_all_fields() -> None:
    entry = MagicMock()
    entry.data = {CONF_TOKEN: "my-token", CONF_FACILITY_ID: "facility-1"}

    with patch.object(DataUpdateCoordinator, "__init__", return_value=None):
        coord = PowerHubCoordinator(MagicMock(), entry)

    assert coord._token == "my-token"
    assert coord._facility_id == "facility-1"
    assert coord._entry is entry
    assert coord._cached_attributes is None
    assert coord._cached_profile is None
    assert coord._cached_agreements is None
    assert coord._cached_facility_info is None
    assert coord._facility_info_resolved is False
    assert coord._reauth_pending is False


# ── PowerHubCoordinator._make_client / _make_power_client ─────────────────────


def test_make_client_returns_powerhub_api_client() -> None:
    entry = MagicMock()
    entry.data = {CONF_TOKEN: "tok", CONF_FACILITY_ID: "fid"}

    with patch.object(DataUpdateCoordinator, "__init__", return_value=None):
        coord = PowerHubCoordinator(MagicMock(), entry)
    coord.hass = MagicMock()

    with patch(
        "custom_components.malarenergi_powerhub.coordinator.async_get_clientsession",
        return_value=MagicMock(),
    ):
        client = coord._make_client()

    assert isinstance(client, PowerHubApiClient)


def test_make_power_client_returns_power_api_client() -> None:
    entry = MagicMock()
    entry.data = {CONF_TOKEN: "tok", CONF_FACILITY_ID: "fid"}

    with patch.object(DataUpdateCoordinator, "__init__", return_value=None):
        coord = PowerHubCoordinator(MagicMock(), entry)
    coord.hass = MagicMock()

    with patch(
        "custom_components.malarenergi_powerhub.coordinator.async_get_clientsession",
        return_value=MagicMock(),
    ):
        client = coord._make_power_client()

    assert isinstance(client, PowerApiClient)


# ── NotificationsCoordinator.__init__ ─────────────────────────────────────────


def test_notifications_coordinator_init_sets_all_fields() -> None:
    entry = MagicMock()
    entry.data = {CONF_TOKEN: "notif-token"}

    with patch.object(DataUpdateCoordinator, "__init__", return_value=None):
        coord = NotificationsCoordinator(MagicMock(), entry)

    assert coord._token == "notif-token"
    assert coord._entry is entry
    assert coord._reauth_pending is False
