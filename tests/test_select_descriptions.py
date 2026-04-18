"""Tests for pure value_fn / to_attr_value lambdas in select.py."""
from __future__ import annotations

from custom_components.malarenergi_powerhub.api import FacilityAttributes
from custom_components.malarenergi_powerhub.select import (
    EV_TYPE_OPTIONS,
    FACILITY_TYPE_OPTIONS,
    FUSE_OPTIONS,
    HEATING_TYPE_OPTIONS,
    SELECTS,
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


def test_select_options_cover_value_fn_output() -> None:
    """For each select, sample value_fn output is among the options (where applicable)."""
    fuse = next(d for d in SELECTS if d.key == "fuse_size")
    assert fuse.value_fn(_make_attrs(fuse_size=20)) in FUSE_OPTIONS

    heat = next(d for d in SELECTS if d.key == "heating_type")
    for opt in HEATING_TYPE_OPTIONS:
        assert heat.value_fn(_make_attrs(heating_type=opt)) == opt
