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


class TestEnergyGasPresets:
    def test_h2_ng_blends_normalize_and_evaluate(self):
        from config import GAS_PRESETS
        from fluid_properties import evaluate_gas_mixture

        for name in ["H2-NG %5 (blend)", "H2-NG %10 (blend)", "H2-NG %20 (blend)", "H2-NG %50 (blend)"]:
            summary = evaluate_gas_mixture(GAS_PRESETS[name]["components"], "molar", 8.0, 20.0)
            assert abs(summary.total_percent - 100.0) < 1e-6, name
            assert summary.average_molecular_weight > 0.0
            assert summary.z is not None

    def test_syngas_preset_present(self):
        from config import GAS_PRESETS
        from fluid_properties import evaluate_gas_mixture

        summary = evaluate_gas_mixture(GAS_PRESETS["Sentez Gazi (Syngas)"]["components"], "molar", 8.0, 20.0)
        assert abs(summary.total_percent - 100.0) < 1e-6
        assert "CarbonMonoxide" in summary.mole_fractions

    def test_energy_presets_registered(self):
        from config import GAS_PRESET_NAMES

        assert any("H2-NG" in name for name in GAS_PRESET_NAMES)
        assert "Sentez Gazi (Syngas)" in GAS_PRESET_NAMES


class TestPureFluidStateFallbackCascade:
    def test_ideal_gas_fallback_returns_valid_state(self):
        from fluid_properties import _ideal_gas_fallback

        state = _ideal_gas_fallback("Methane", 1.0, 25.0)
        for key in ["density_kg_m3", "molecular_weight", "specific_heat_ratio", "z"]:
            assert state[key] > 0.0, key
        assert state["density_kg_m3"] < 1.0

    def test_chemicals_state_unknown_fluid_returns_none(self):
        from fluid_properties import _evaluate_chemicals_state

        assert _evaluate_chemicals_state("zz_not_a_fluid_xzy", 1.0, 25.0) is None

    def test_coolprop_failure_falls_to_thermo(self, monkeypatch):
        import fluid_properties

        class _FailCP:
            @staticmethod
            def PropsSI(*_a, **_k):  # noqa: N802 - CoolProp API mirror
                raise ValueError("boom")

        fluid_properties.get_pure_fluid_state.cache_clear()
        monkeypatch.setattr(fluid_properties, "CP", _FailCP)
        state = fluid_properties.get_pure_fluid_state("Methane", 1.0, 25.0)
        assert state["molecular_weight"] > 15.0
        assert state["specific_heat_ratio"] > 1.0

    def test_full_fallback_to_ideal_gas(self, monkeypatch):
        import fluid_properties

        class _FailCP:
            @staticmethod
            def PropsSI(*_a, **_k):  # noqa: N802 - CoolProp API mirror
                raise ValueError("boom")

        fluid_properties.get_pure_fluid_state.cache_clear()
        monkeypatch.setattr(fluid_properties, "CP", _FailCP)
        monkeypatch.setattr(fluid_properties, "get_thermo_fluid_state", lambda *_a, **_k: None)
        monkeypatch.setattr(fluid_properties, "_evaluate_chemicals_state", lambda *_a, **_k: None)
        state = fluid_properties.get_pure_fluid_state("Methane", 1.0, 25.0)
        assert state["z"] == 1.0
        assert state["density_kg_m3"] > 0.0
