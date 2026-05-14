"""Tests for value_fn lambdas and entity classes in switch.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.malarenergi_powerhub.api import (
    FacilityAttributes,
    NotificationSettings,
)
from custom_components.malarenergi_powerhub.switch import (
    ATTRIBUTE_SWITCHES,
    NOTIFICATION_SWITCHES,
    NotificationSwitch,
    PowerHubSwitch,
)


def _make_attrs(**overrides) -> FacilityAttributes:
    base = dict(
        heating_type="DISTRICT_HEATING",
        fuse_size=20,
        occupants=2,
        area=80,
        facility_type="APARTMENT",
        ev_type="NONE",
        has_battery=False,
        has_solar=False,
    )
    base.update(overrides)
    return FacilityAttributes(**base)


def _make_notif(**overrides) -> NotificationSettings:
    base = dict(
        notify_total_power=False,
        notify_phase_load=False,
        notify_control_disabled_exceeded_phase=False,
        notify_control_disabled_exceeded_power=False,
        notify_control_enabled_exceeded_phase=False,
        notify_control_enabled_exceeded_power=False,
    )
    base.update(overrides)
    return NotificationSettings(**base)


def test_attribute_switches_have_unique_keys() -> None:
    keys = [d.key for d in ATTRIBUTE_SWITCHES]
    assert len(keys) == len(set(keys))


def test_notification_switches_have_unique_keys() -> None:
    keys = [d.key for d in NOTIFICATION_SWITCHES]
    assert len(keys) == len(set(keys))


def test_attribute_switch_attr_field_matches_dataclass() -> None:
    """Every attr_field must be a real FacilityAttributes field so turn_on works."""
    valid = set(FacilityAttributes.__dataclass_fields__.keys())
    for desc in ATTRIBUTE_SWITCHES:
        assert desc.attr_field in valid, f"{desc.key} points at non-existent field"


def test_notification_switch_notif_field_matches_dataclass() -> None:
    valid = set(NotificationSettings.__dataclass_fields__.keys())
    for desc in NOTIFICATION_SWITCHES:
        assert desc.notif_field in valid, f"{desc.key} points at non-existent field"


def test_has_solar_value_fn_reflects_attribute() -> None:
    desc = next(d for d in ATTRIBUTE_SWITCHES if d.key == "has_solar")
    assert desc.value_fn(_make_attrs(has_solar=True)) is True
    assert desc.value_fn(_make_attrs(has_solar=False)) is False


def test_has_battery_value_fn_reflects_attribute() -> None:
    desc = next(d for d in ATTRIBUTE_SWITCHES if d.key == "has_battery")
    assert desc.value_fn(_make_attrs(has_battery=True)) is True
    assert desc.value_fn(_make_attrs(has_battery=False)) is False


def test_every_notification_switch_reads_its_named_field() -> None:
    """Flip each field individually; ensure the matching value_fn — and only
    that one — returns True. Guards against copy-paste errors in the lambdas."""
    for target in NOTIFICATION_SWITCHES:
        notif = _make_notif(**{target.notif_field: True})
        for desc in NOTIFICATION_SWITCHES:
            expected = desc.notif_field == target.notif_field
            assert desc.value_fn(notif) is expected, (
                f"{desc.key} read wrong field when {target.notif_field} was set"
            )


# ── PowerHubSwitch entity ─────────────────────────────────────────────────────

def _make_coord_with_attrs(**attr_overrides) -> MagicMock:
    coord = MagicMock()
    coord.config_entry.entry_id = "entry-id"
    coord.config_entry.title = "Home"
    coord.data = MagicMock()
    coord.data.attributes = _make_attrs(**attr_overrides)
    coord.data.notification_settings = _make_notif()
    coord.async_update_attributes = AsyncMock()
    coord.async_update_notification_settings = AsyncMock()
    return coord


def test_powerhub_switch_is_on_reflects_attribute() -> None:
    desc = next(d for d in ATTRIBUTE_SWITCHES if d.key == "has_solar")
    coord = _make_coord_with_attrs(has_solar=True)
    switch = PowerHubSwitch(coord, desc)
    assert switch.is_on is True


def test_powerhub_switch_is_on_none_when_no_data() -> None:
    desc = next(d for d in ATTRIBUTE_SWITCHES if d.key == "has_solar")
    coord = _make_coord_with_attrs()
    coord.data = None
    switch = PowerHubSwitch(coord, desc)
    assert switch.is_on is None


def test_powerhub_switch_is_on_none_when_no_attributes() -> None:
    desc = next(d for d in ATTRIBUTE_SWITCHES if d.key == "has_solar")
    coord = _make_coord_with_attrs()
    coord.data.attributes = None
    switch = PowerHubSwitch(coord, desc)
    assert switch.is_on is None


@pytest.mark.asyncio
async def test_powerhub_switch_turn_on_calls_coordinator() -> None:
    desc = next(d for d in ATTRIBUTE_SWITCHES if d.key == "has_solar")
    coord = _make_coord_with_attrs(has_solar=False)
    switch = PowerHubSwitch(coord, desc)
    await switch.async_turn_on()
    coord.async_update_attributes.assert_awaited_once_with(has_solar=True)


@pytest.mark.asyncio
async def test_powerhub_switch_turn_off_calls_coordinator() -> None:
    desc = next(d for d in ATTRIBUTE_SWITCHES if d.key == "has_solar")
    coord = _make_coord_with_attrs(has_solar=True)
    switch = PowerHubSwitch(coord, desc)
    await switch.async_turn_off()
    coord.async_update_attributes.assert_awaited_once_with(has_solar=False)


def test_powerhub_switch_unique_id() -> None:
    desc = next(d for d in ATTRIBUTE_SWITCHES if d.key == "has_solar")
    coord = _make_coord_with_attrs()
    switch = PowerHubSwitch(coord, desc)
    assert switch._attr_unique_id == "entry-id_has_solar"


# ── NotificationSwitch entity ─────────────────────────────────────────────────

def test_notification_switch_is_on_reflects_setting() -> None:
    desc = next(d for d in NOTIFICATION_SWITCHES if d.key == "notify_total_power")
    coord = _make_coord_with_attrs()
    coord.data.notification_settings = _make_notif(notify_total_power=True)
    switch = NotificationSwitch(coord, desc)
    assert switch.is_on is True


def test_notification_switch_is_on_none_when_no_data() -> None:
    desc = next(d for d in NOTIFICATION_SWITCHES if d.key == "notify_total_power")
    coord = _make_coord_with_attrs()
    coord.data = None
    switch = NotificationSwitch(coord, desc)
    assert switch.is_on is None


def test_notification_switch_is_on_none_when_no_notif_settings() -> None:
    desc = next(d for d in NOTIFICATION_SWITCHES if d.key == "notify_total_power")
    coord = _make_coord_with_attrs()
    coord.data.notification_settings = None
    switch = NotificationSwitch(coord, desc)
    assert switch.is_on is None


@pytest.mark.asyncio
async def test_notification_switch_turn_on_calls_coordinator() -> None:
    desc = next(d for d in NOTIFICATION_SWITCHES if d.key == "notify_total_power")
    coord = _make_coord_with_attrs()
    switch = NotificationSwitch(coord, desc)
    await switch.async_turn_on()
    coord.async_update_notification_settings.assert_awaited_once_with(
        notify_total_power=True
    )


@pytest.mark.asyncio
async def test_notification_switch_turn_off_calls_coordinator() -> None:
    desc = next(d for d in NOTIFICATION_SWITCHES if d.key == "notify_total_power")
    coord = _make_coord_with_attrs()
    switch = NotificationSwitch(coord, desc)
    await switch.async_turn_off()
    coord.async_update_notification_settings.assert_awaited_once_with(
        notify_total_power=False
    )


def test_notification_switch_unique_id() -> None:
    desc = next(d for d in NOTIFICATION_SWITCHES if d.key == "notify_total_power")
    coord = _make_coord_with_attrs()
    switch = NotificationSwitch(coord, desc)
    assert switch._attr_unique_id == "entry-id_notify_total_power"
