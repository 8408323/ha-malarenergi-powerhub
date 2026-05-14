"""Tests for value_fn lambdas and entity classes in number.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.malarenergi_powerhub.api import (
    FacilityAttributes,
    FacilityControl,
)
from custom_components.malarenergi_powerhub.number import (
    ATTRIBUTE_NUMBERS,
    CONTROL_NUMBERS,
    PowerControlNumber,
    PowerHubNumber,
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


def _make_control(**overrides) -> FacilityControl:
    base = dict(
        fuse_limit_a=20.0,
        power_limit_kw=11.0,
        action_on_fuse_limit="NOTIFY",
        action_on_power_limit="NOTIFY",
    )
    base.update(overrides)
    return FacilityControl(**base)


def test_attribute_numbers_have_unique_keys() -> None:
    keys = [d.key for d in ATTRIBUTE_NUMBERS]
    assert len(keys) == len(set(keys))


def test_control_numbers_have_unique_keys() -> None:
    keys = [d.key for d in CONTROL_NUMBERS]
    assert len(keys) == len(set(keys))


def test_attribute_number_attr_field_matches_dataclass() -> None:
    valid = set(FacilityAttributes.__dataclass_fields__.keys())
    for desc in ATTRIBUTE_NUMBERS:
        assert desc.attr_field in valid


def test_control_number_control_field_matches_dataclass() -> None:
    valid = set(FacilityControl.__dataclass_fields__.keys())
    for desc in CONTROL_NUMBERS:
        assert desc.control_field in valid


def test_area_value_fn_reads_area() -> None:
    desc = next(d for d in ATTRIBUTE_NUMBERS if d.key == "area")
    assert desc.value_fn(_make_attrs(area=95)) == 95
    assert desc.value_fn(_make_attrs(area=1)) == 1


def test_occupants_value_fn_reads_occupants() -> None:
    desc = next(d for d in ATTRIBUTE_NUMBERS if d.key == "occupants")
    assert desc.value_fn(_make_attrs(occupants=4)) == 4


def test_fuse_limit_value_fn_reads_float_amps() -> None:
    desc = next(d for d in CONTROL_NUMBERS if d.key == "fuse_limit_set")
    assert desc.value_fn(_make_control(fuse_limit_a=16.0)) == 16.0


# ── PowerHubNumber entity ─────────────────────────────────────────────────────


def _make_number_coord(**attr_overrides) -> MagicMock:
    coord = MagicMock()
    coord.config_entry.entry_id = "entry-id"
    coord.config_entry.title = "Home"
    coord.data = MagicMock()
    coord.data.attributes = _make_attrs(**attr_overrides)
    coord.data.facility_control = _make_control()
    coord.async_update_attributes = AsyncMock()
    coord.async_update_facility_control = AsyncMock()
    return coord


def test_powerhub_number_native_value_reads_attribute() -> None:
    desc = next(d for d in ATTRIBUTE_NUMBERS if d.key == "area")
    coord = _make_number_coord(area=95)
    number = PowerHubNumber(coord, desc)
    assert number.native_value == 95


def test_powerhub_number_native_value_none_when_no_data() -> None:
    desc = next(d for d in ATTRIBUTE_NUMBERS if d.key == "area")
    coord = _make_number_coord()
    coord.data = None
    number = PowerHubNumber(coord, desc)
    assert number.native_value is None


def test_powerhub_number_native_value_none_when_no_attributes() -> None:
    desc = next(d for d in ATTRIBUTE_NUMBERS if d.key == "area")
    coord = _make_number_coord()
    coord.data.attributes = None
    number = PowerHubNumber(coord, desc)
    assert number.native_value is None


@pytest.mark.asyncio
async def test_powerhub_number_set_native_value_calls_coordinator() -> None:
    desc = next(d for d in ATTRIBUTE_NUMBERS if d.key == "area")
    coord = _make_number_coord()
    number = PowerHubNumber(coord, desc)
    await number.async_set_native_value(100.0)
    coord.async_update_attributes.assert_awaited_once_with(area=100)


def test_powerhub_number_unique_id() -> None:
    desc = next(d for d in ATTRIBUTE_NUMBERS if d.key == "area")
    coord = _make_number_coord()
    number = PowerHubNumber(coord, desc)
    assert number._attr_unique_id == "entry-id_area"


# ── PowerControlNumber entity ─────────────────────────────────────────────────


def test_power_control_number_native_value_reads_control() -> None:
    desc = next(d for d in CONTROL_NUMBERS if d.key == "power_limit_set")
    coord = _make_number_coord()
    coord.data.facility_control = _make_control(power_limit_kw=7.5)
    number = PowerControlNumber(coord, desc)
    assert number.native_value == 7.5


def test_power_control_number_native_value_none_when_no_data() -> None:
    desc = next(d for d in CONTROL_NUMBERS if d.key == "power_limit_set")
    coord = _make_number_coord()
    coord.data = None
    number = PowerControlNumber(coord, desc)
    assert number.native_value is None


def test_power_control_number_native_value_none_when_no_control() -> None:
    desc = next(d for d in CONTROL_NUMBERS if d.key == "power_limit_set")
    coord = _make_number_coord()
    coord.data.facility_control = None
    number = PowerControlNumber(coord, desc)
    assert number.native_value is None


@pytest.mark.asyncio
async def test_power_control_number_set_value_calls_coordinator() -> None:
    desc = next(d for d in CONTROL_NUMBERS if d.key == "power_limit_set")
    coord = _make_number_coord()
    number = PowerControlNumber(coord, desc)
    await number.async_set_native_value(8.0)
    coord.async_update_facility_control.assert_awaited_once_with(power_limit_kw=8.0)


def test_power_control_number_unique_id() -> None:
    desc = next(d for d in CONTROL_NUMBERS if d.key == "power_limit_set")
    coord = _make_number_coord()
    number = PowerControlNumber(coord, desc)
    assert number._attr_unique_id == "entry-id_power_limit_set"


def test_power_limit_value_fn_reads_kilowatts_end() -> None:
    desc = next(d for d in CONTROL_NUMBERS if d.key == "power_limit_set")
    assert desc.value_fn(_make_control(power_limit_kw=7.5)) == 7.5


def test_attribute_numbers_have_valid_bounds() -> None:
    """Min < max for every editable number, step > 0."""
    for desc in ATTRIBUTE_NUMBERS + CONTROL_NUMBERS:
        assert desc.native_min_value < desc.native_max_value
        assert desc.native_step > 0
