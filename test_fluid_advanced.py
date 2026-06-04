"""Tests for iapws and thermo integration in fluid_properties.py."""

from __future__ import annotations

from importlib.util import find_spec

from fluid_properties import get_steam_properties_iapws, get_thermo_fluid_state

HAS_IAPWS = find_spec("iapws") is not None
HAS_THERMO = find_spec("thermo") is not None


class TestSteamPropertiesIAPWS:
    def test_iapws_installed(self):
        assert HAS_IAPWS, "iapws library not installed"

    def test_steam_10bar_500k(self):
        props = get_steam_properties_iapws(10.0, 226.85)
        assert props is not None
        assert 4.0 < props["density_kg_m3"] < 5.0
        assert 1.5e-5 < props["viscosity_pa_s"] < 2.0e-5
        assert 1.3 < props["specific_heat_ratio"] < 1.4
        assert props["phase"] == "Vapour" or props["phase"] == "Gas"

    def test_water_10bar_27c(self):
        props = get_steam_properties_iapws(10.0, 27.0)
        assert props is not None
        assert 990.0 < props["density_kg_m3"] < 1000.0
        assert props["phase"] == "Liquid"

    def test_z_near_ideal(self):
        props = get_steam_properties_iapws(1.0, 200.0)
        assert props is not None
        assert 0.95 < props["z"] < 1.0

    def test_supercritical(self):
        props = get_steam_properties_iapws(250.0, 427.0)
        assert props is not None
        assert props["phase"] == "Supercritical fluid"

    def test_invalid_pressure(self):
        props = get_steam_properties_iapws(-1.0, 100.0)
        assert props is None

    def test_return_keys(self):
        props = get_steam_properties_iapws(5.0, 150.0)
        assert props is not None
        expected = {"density_kg_m3", "viscosity_pa_s", "cp_kj_kgk", "cv_kj_kgk",
                    "specific_heat_ratio", "z", "enthalpy_kj_kg", "entropy_kj_kgk",
                    "thermal_conductivity_w_mk", "phase"}
        assert expected.issubset(props.keys())


class TestThermoProperties:
    def test_thermo_installed(self):
        assert HAS_THERMO, "thermo library not installed"

    def test_methane_density(self):
        props = get_thermo_fluid_state("methane", 1.0, 25.0)
        assert props is not None
        assert 0.6 < props["density_kg_m3"] < 1.0

    def test_methane_mw(self):
        props = get_thermo_fluid_state("methane", 1.0, 25.0)
        assert props is not None
        assert 16.0 < props["molecular_weight"] < 16.1

    def test_water_thermo(self):
        props = get_thermo_fluid_state("water", 1.0, 20.0)
        assert props is not None
        assert props["density_kg_m3"] > 950.0

    def test_unknown_fluid(self):
        props = get_thermo_fluid_state("zz_not_a_fluid_xzy", 1.0, 25.0)
        assert props is None

    def test_return_keys(self):
        props = get_thermo_fluid_state("propane", 1.0, 25.0)
        assert props is not None
        for key in ["density_kg_m3", "viscosity_pa_s", "molecular_weight", "z"]:
            assert key in props, f"Missing key: {key}"

    def test_high_pressure(self):
        props = get_thermo_fluid_state("methane", 100.0, 25.0)
        assert props is not None
        assert props["density_kg_m3"] > 50.0
