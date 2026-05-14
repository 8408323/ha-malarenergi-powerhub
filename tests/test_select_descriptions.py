"""Tests for value_fn / to_attr_value lambdas and entity class in select.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.malarenergi_powerhub.api import FacilityAttributes
from custom_components.malarenergi_powerhub.select import (
    EV_TYPE_OPTIONS,
    FACILITY_TYPE_OPTIONS,
    FUSE_OPTIONS,
    HEATING_TYPE_OPTIONS,
    SELECTS,
    PowerHubSelect,
    _fuse_to_attr,
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


def test_selects_have_unique_keys() -> None:
    keys = [d.key for d in SELECTS]
    assert len(keys) == len(set(keys))


def test_select_attr_field_matches_dataclass() -> None:
    valid = set(FacilityAttributes.__dataclass_fields__.keys())
    for desc in SELECTS:
        assert desc.attr_field in valid


def test_fuse_size_value_fn_formats_as_axx() -> None:
    desc = next(d for d in SELECTS if d.key == "fuse_size")
    assert desc.value_fn(_make_attrs(fuse_size=20)) == "A20"
    assert desc.value_fn(_make_attrs(fuse_size=63)) == "A63"


def test_fuse_size_value_fn_returns_none_when_zero() -> None:
    desc = next(d for d in SELECTS if d.key == "fuse_size")
    assert desc.value_fn(_make_attrs(fuse_size=0)) is None


def test_fuse_to_attr_parses_axx_to_int() -> None:
    assert _fuse_to_attr("A20") == 20
    assert _fuse_to_attr("A63") == 63
    assert _fuse_to_attr("a16") == 16


def test_fuse_to_attr_falls_back_to_default_on_bad_input() -> None:
    assert _fuse_to_attr("bogus") == 20


def test_heating_type_value_fn_passes_through() -> None:
    desc = next(d for d in SELECTS if d.key == "heating_type")
    assert desc.value_fn(_make_attrs(heating_type="ELECTRIC")) == "ELECTRIC"


def test_heating_type_value_fn_returns_none_when_empty() -> None:
    desc = next(d for d in SELECTS if d.key == "heating_type")
    assert desc.value_fn(_make_attrs(heating_type="")) is None


def test_facility_type_value_fn_passes_through() -> None:
    desc = next(d for d in SELECTS if d.key == "facility_type")
    assert desc.value_fn(_make_attrs(facility_type="VILLA")) == "VILLA"


def test_ev_type_value_fn_defaults_to_none_string_when_missing() -> None:
    """ev_type=None falls back to the literal option "NONE" (not Python None)."""
    desc = next(d for d in SELECTS if d.key == "ev_type")
    assert desc.value_fn(_make_attrs(ev_type=None)) == "NONE"
    assert desc.value_fn(_make_attrs(ev_type="THREE_PHASE")) == "THREE_PHASE"


def test_all_option_lists_are_non_empty() -> None:
    assert FUSE_OPTIONS
    assert HEATING_TYPE_OPTIONS
    assert FACILITY_TYPE_OPTIONS
    assert EV_TYPE_OPTIONS


# ── PowerHubSelect entity ─────────────────────────────────────────────────────


def _make_select_coord(**attr_overrides) -> MagicMock:
    coord = MagicMock()
    coord.config_entry.entry_id = "entry-id"
    coord.config_entry.title = "Home"
    coord.data = MagicMock()
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
    base.update(attr_overrides)
    coord.data.attributes = FacilityAttributes(**base)
    coord.async_update_attributes = AsyncMock()
    return coord


def test_powerhub_select_current_option_returns_valid_option() -> None:
    desc = next(d for d in SELECTS if d.key == "heating_type")
    select = PowerHubSelect(_make_select_coord(heating_type="ELECTRIC"), desc)
    assert select.current_option == "ELECTRIC"


def test_powerhub_select_current_option_none_when_no_data() -> None:
    desc = next(d for d in SELECTS if d.key == "heating_type")
    coord = _make_select_coord()
    coord.data = None
    select = PowerHubSelect(coord, desc)
    assert select.current_option is None


def test_powerhub_select_current_option_none_when_no_attributes() -> None:
    desc = next(d for d in SELECTS if d.key == "heating_type")
    coord = _make_select_coord()
    coord.data.attributes = None
    select = PowerHubSelect(coord, desc)
    assert select.current_option is None


def test_powerhub_select_current_option_none_when_value_not_in_options() -> None:
    """An unknown value from the API renders the entity unavailable (None)."""
    desc = next(d for d in SELECTS if d.key == "heating_type")
    select = PowerHubSelect(_make_select_coord(heating_type="UNKNOWN_FUTURE"), desc)
    assert select.current_option is None


def test_powerhub_select_fuse_size_current_option() -> None:
    desc = next(d for d in SELECTS if d.key == "fuse_size")
    select = PowerHubSelect(_make_select_coord(fuse_size=25), desc)
    assert select.current_option == "A25"


@pytest.mark.asyncio
async def test_powerhub_select_async_select_option_calls_coordinator() -> None:
    desc = next(d for d in SELECTS if d.key == "heating_type")
    coord = _make_select_coord()
    select = PowerHubSelect(coord, desc)
    await select.async_select_option("ELECTRIC")
    coord.async_update_attributes.assert_awaited_once_with(heating_type="ELECTRIC")


@pytest.mark.asyncio
async def test_powerhub_select_fuse_size_converts_option_to_int() -> None:
    """fuse_size uses to_attr_value to parse "A20" → 20 before the API call."""
    desc = next(d for d in SELECTS if d.key == "fuse_size")
    coord = _make_select_coord()
    select = PowerHubSelect(coord, desc)
    await select.async_select_option("A20")
    coord.async_update_attributes.assert_awaited_once_with(fuse_size=20)


def test_powerhub_select_unique_id() -> None:
    desc = next(d for d in SELECTS if d.key == "heating_type")
    select = PowerHubSelect(_make_select_coord(), desc)
    assert select._attr_unique_id == "entry-id_heating_type"


def test_powerhub_select_options_populated_from_description() -> None:
    desc = next(d for d in SELECTS if d.key == "fuse_size")
    select = PowerHubSelect(_make_select_coord(), desc)
    assert select._attr_options == list(FUSE_OPTIONS)


def test_select_options_cover_value_fn_output() -> None:
    """For each select, sample value_fn output is among the options (where applicable)."""
    fuse = next(d for d in SELECTS if d.key == "fuse_size")
    assert fuse.value_fn(_make_attrs(fuse_size=20)) in FUSE_OPTIONS

    heat = next(d for d in SELECTS if d.key == "heating_type")
    for opt in HEATING_TYPE_OPTIONS:
        assert heat.value_fn(_make_attrs(heating_type=opt)) == opt
