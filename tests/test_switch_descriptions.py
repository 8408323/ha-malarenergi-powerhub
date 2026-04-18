"""Tests for pure value_fn lambdas in switch.py.

Full switch entity tests require the HA runtime (CoordinatorEntity); these tests
cover the description tables so any wiring mistake (wrong attribute name, typo)
fails in CI.
"""
from __future__ import annotations

from custom_components.malarenergi_powerhub.api import (
    FacilityAttributes,
    NotificationSettings,
)
from custom_components.malarenergi_powerhub.switch import (
    ATTRIBUTE_SWITCHES,
    NOTIFICATION_SWITCHES,
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
