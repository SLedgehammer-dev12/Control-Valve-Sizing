"""Tests for chemicals library integration in fluid_properties.py."""

from __future__ import annotations

from fluid_properties import (
    get_chemical_property,
    get_chemical_vapor_pressure_bar_a,
    list_chemical_fluids,
)


class TestChemicalsAvailable:
    def test_library_loaded(self):
        fluids = list_chemical_fluids()
        assert len(fluids) > 0

    def test_water_found(self):
        mw = get_chemical_property("water", "mw_g_mol")
        assert mw is not None
        assert 18.0 < mw < 18.1

    def test_methane_found(self):
        mw = get_chemical_property("methane", "mw_g_mol")
        assert mw is not None
        assert 16.0 < mw < 16.1

    def test_methane_critical_temp(self):
        tc = get_chemical_property("methane", "tc_k")
        assert tc is not None
        assert 180 < tc < 200

    def test_methane_critical_pressure(self):
        pc = get_chemical_property("methane", "pc_pa")
        assert pc is not None
        assert 4e6 < pc < 5e6

    def test_unknown_fluid(self):
        mw = get_chemical_property("zz_not_a_fluid_xzy", "mw_g_mol")
        assert mw is None

    def test_unknown_property(self):
        val = get_chemical_property("methane", "not_a_real_property")
        assert val is None


class TestChemicalVaporPressure:
    def test_methane_antoine(self):
        pv = get_chemical_vapor_pressure_bar_a("methane", -165)
        assert pv is not None
        assert 0.01 < pv < 1.0

    def test_water_antoine(self):
        pv = get_chemical_vapor_pressure_bar_a("water", 25)
        assert pv is not None
        assert 0.01 < pv < 0.1

    def test_water_boiling(self):
        pv = get_chemical_vapor_pressure_bar_a("water", 100)
        assert pv is not None
        assert 0.9 < pv < 1.2

    def test_ethanol_antoine(self):
        pv = get_chemical_vapor_pressure_bar_a("ethanol", 78)
        assert pv is not None
        assert 0.8 < pv < 1.2

    def test_out_of_range_temp(self):
        pv = get_chemical_vapor_pressure_bar_a("methane", 500)
        assert pv is None

    def test_unknown_fluid_antoine(self):
        pv = get_chemical_vapor_pressure_bar_a("zz_not_a_fluid", 25)
        assert pv is None


class TestChemicalPresets:
    def test_fluids_contain_common(self):
        fluids = list_chemical_fluids()
        for name in ["methane", "ethanol", "propane", "butane"]:
            assert name in fluids, f"Expected '{name}' in chemical fluids list"

    def test_fluids_are_sorted(self):
        fluids = list_chemical_fluids()
        assert fluids == sorted(fluids)

    def test_fluids_no_duplicates(self):
        fluids = list_chemical_fluids()
        assert len(fluids) == len(set(fluids))

    def test_fluids_is_cached(self):
        f1 = list_chemical_fluids()
        f2 = list_chemical_fluids()
        assert f1 is f2
