"""Tests for pure helper functions in coordinator.py.

The coordinator itself depends on HomeAssistant runtime (hass, ConfigEntry).
These tests cover only the module-level helpers that can run standalone.
"""
from __future__ import annotations

import zoneinfo
from datetime import datetime, timezone
from unittest.mock import patch

from custom_components.malarenergi_powerhub.coordinator import _day_start_ms, _now_ms


_STHLM = zoneinfo.ZoneInfo("Europe/Stockholm")


def test_day_start_ms_returns_midnight_stockholm_in_summer() -> None:
    """In summer, Stockholm is CEST (UTC+2). Midnight local is 22:00 UTC prior day."""
    # 2026-07-15 14:30 Stockholm (CEST, UTC+2)
    fake_now = datetime(2026, 7, 15, 14, 30, 0, tzinfo=_STHLM)
    with patch(
        "custom_components.malarenergi_powerhub.coordinator.datetime"
    ) as mock_dt:
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
    with patch(
        "custom_components.malarenergi_powerhub.coordinator.datetime"
    ) as mock_dt:
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
