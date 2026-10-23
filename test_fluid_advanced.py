"""Tests for iapws and thermo integration in fluid_properties.py."""

from __future__ import annotations

from importlib.util import find_spec

import pytest

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


class TestSteamSaturation:
    """Test suite for saturated and superheated steam property helpers."""

    def test_saturated_steam_temperature_lookup(self):
        from fluid_properties import get_saturated_steam_temperature

        t_1bar = get_saturated_steam_temperature(1.01325)
        assert t_1bar == pytest.approx(100.0, abs=0.5)

        t_10bar = get_saturated_steam_temperature(10.0)
        assert t_10bar == pytest.approx(179.9, abs=0.5)

        t_50bar = get_saturated_steam_temperature(50.0)
        assert t_50bar == pytest.approx(263.9, abs=0.5)

    def test_saturated_steam_pressure_lookup(self):
        from fluid_properties import get_saturated_steam_pressure

        p_100c = get_saturated_steam_pressure(100.0)
        assert p_100c == pytest.approx(1.013, abs=0.05)

        p_180c = get_saturated_steam_pressure(180.0)
        assert p_180c == pytest.approx(10.0, abs=0.5)

    def test_evaluate_steam_state_superheated(self):
        from fluid_properties import evaluate_steam_state

        res = evaluate_steam_state(10.0, 250.0)
        assert res["phase"] == "superheated"
        assert res["is_superheated"] is True
        assert res["delta_t_superheat"] > 60.0

    def test_evaluate_steam_state_wet(self):
        from fluid_properties import evaluate_steam_state

        res = evaluate_steam_state(10.0, 150.0)
        assert res["phase"] == "wet_steam"
        assert res["is_wet"] is True
        assert any("erozyon" in w.lower() for w in res["warnings"])

    def test_evaluate_steam_state_saturated(self):
        from fluid_properties import evaluate_steam_state

        res = evaluate_steam_state(10.0, 180.0)
        assert res["phase"] == "saturated"
        assert any("Stellite" in w for w in res["warnings"])

    def test_saturated_steam_supercritical_and_fallback(self, monkeypatch):
        from fluid_properties import (
            CP,
            get_saturated_steam_pressure,
            get_saturated_steam_temperature,
        )

        assert get_saturated_steam_temperature(250.0) == 373.95
        assert get_saturated_steam_pressure(400.0) == 220.64

        def _fail(*_a, **_k):
            raise RuntimeError("coolprop down")

        monkeypatch.setattr(CP, "PropsSI", _fail)
        t_fallback = get_saturated_steam_temperature(10.0)
        assert t_fallback > 0.0
        p_fallback = get_saturated_steam_pressure(100.0)
        assert p_fallback > 0.0

    def test_evaluate_steam_state_high_temperature(self):
        from fluid_properties import evaluate_steam_state

        res = evaluate_steam_state(10.0, 450.0)
        assert any("WC6/WC9" in w for w in res["warnings"])


class TestFluidPropertiesFallbacks:
    def test_molecular_weight_fallbacks(self, monkeypatch):
        import fluid_properties
        from fluid_properties import get_molecular_weight

        assert get_molecular_weight("nonexistent_molecule_xyz_123") == 28.96

        monkeypatch.setattr(fluid_properties, "_get_mw_coolprop", lambda _f: None)
        assert get_molecular_weight("benzene") == pytest.approx(78.11, abs=0.5)

    def test_liquid_preset_invalid(self):
        from fluid_properties import get_liquid_preset

        with pytest.raises(ValueError, match="Bilinmeyen sivi preset"):
            get_liquid_preset("invalid_liquid")

    def test_evaluate_chemicals_state_path(self, monkeypatch):
        import fluid_properties

        fluid_properties.get_pure_fluid_state.cache_clear()

        def _fail(*_a, **_k):
            raise RuntimeError("coolprop down")

        monkeypatch.setattr(fluid_properties.CP, "PropsSI", _fail)
        monkeypatch.setattr(fluid_properties, "get_thermo_fluid_state", lambda *_a, **_k: None)

        state = fluid_properties.get_pure_fluid_state("Methane", 5.0, 25.0)
        assert state["density_kg_m3"] > 0
        assert state["z"] > 0

    def test_chemical_vapor_pressure_bounds_and_errors(self):
        from fluid_properties import get_chemical_vapor_pressure_bar_a

        assert get_chemical_vapor_pressure_bar_a("water", -100.0) is None
        assert get_chemical_vapor_pressure_bar_a("water", 1000.0) is None
        assert get_chemical_vapor_pressure_bar_a("unknown_molecule_xyz", 25.0) is None




def test_gas_presets_are_complete_and_evaluable():
    from config import GAS_PRESETS
    from fluid_properties import evaluate_gas_mixture

    for name, preset in GAS_PRESETS.items():
        rows = preset["components"]
        assert rows, name
        assert sum(float(row["fraction_pct"]) for row in rows) == pytest.approx(100.0), name
        summary = evaluate_gas_mixture(rows, "molar", 8.0, 20.0)
        assert summary.average_molecular_weight > 0.0, name
        assert summary.density_kg_m3 > 0.0, name
        assert summary.z and summary.z > 0.0, name
        assert summary.specific_heat_ratio and summary.specific_heat_ratio > 0.0, name


def test_hydrogen_blends_get_lighter_and_stiffer():
    from config import GAS_PRESETS
    from fluid_properties import evaluate_gas_mixture

    names = ["H2-NG %5 (blend)", "H2-NG %10 (blend)", "H2-NG %20 (blend)", "H2-NG %50 (blend)"]
    summaries = [evaluate_gas_mixture(GAS_PRESETS[name]["components"], "molar", 8.0, 20.0) for name in names]
    mws = [summary.average_molecular_weight for summary in summaries]
    densities = [summary.density_kg_m3 for summary in summaries]
    ks = [summary.specific_heat_ratio or 0.0 for summary in summaries]
    assert all(later < earlier for earlier, later in zip(mws, mws[1:], strict=False))
    assert all(later < earlier for earlier, later in zip(densities, densities[1:], strict=False))
    assert all(later > earlier for earlier, later in zip(ks, ks[1:], strict=False))


def test_molar_and_mass_basis_are_equivalent():
    from config import GAS_PRESETS
    from fluid_properties import evaluate_gas_mixture, get_molecular_weight

    rows = GAS_PRESETS["Doğal Gaz"]["components"]
    molar = evaluate_gas_mixture(rows, "molar", 8.0, 20.0)
    weighted = [(row["component"], float(row["fraction_pct"]) * get_molecular_weight(str(row["component"]))) for row in rows]
    total = sum(weight for _, weight in weighted)
    mass_rows = [{"component": component, "fraction_pct": weight / total * 100.0} for component, weight in weighted]
    mass = evaluate_gas_mixture(mass_rows, "mass", 8.0, 20.0)
    assert mass.average_molecular_weight == pytest.approx(molar.average_molecular_weight, rel=1e-6)
    assert mass.density_kg_m3 == pytest.approx(molar.density_kg_m3, rel=1e-6)
    assert mass.z == pytest.approx(molar.z, rel=1e-6)
    assert mass.specific_heat_ratio == pytest.approx(molar.specific_heat_ratio, rel=1e-6)



def test_gas_fallback_flag_is_exposed(monkeypatch):
    import fluid_properties
    from config import GAS_PRESETS
    from fluid_properties import evaluate_gas_mixture

    monkeypatch.setattr(fluid_properties, "_evaluate_mixture_state_heos", lambda *_args, **_kwargs: None)
    summary = evaluate_gas_mixture(GAS_PRESETS["Doğal Gaz"]["components"], "molar", 8.0, 20.0)
    assert summary.fallback_used is True


def test_gas_normal_path_is_not_marked_fallback():
    from config import GAS_PRESETS
    from fluid_properties import evaluate_gas_mixture

    summary = evaluate_gas_mixture(GAS_PRESETS["Doğal Gaz"]["components"], "molar", 8.0, 20.0)
    assert summary.fallback_used is False



def test_gas_model_real_vs_ideal():
    from config import GAS_PRESETS
    from fluid_properties import evaluate_gas_mixture

    real = evaluate_gas_mixture(GAS_PRESETS["Doğal Gaz"]["components"], "molar", 8.0, 20.0, "real")
    ideal = evaluate_gas_mixture(GAS_PRESETS["Doğal Gaz"]["components"], "molar", 8.0, 20.0, "ideal")
    assert real.model_used == "heos"
    assert real.fallback_used is False
    assert real.z != pytest.approx(1.0)
    assert ideal.model_used == "ideal"
    assert ideal.fallback_used is True
    assert ideal.z == pytest.approx(1.0)
    with pytest.raises(ValueError, match="Gercek gaz"):
        evaluate_gas_mixture([{"component": "Chlorine", "fraction_pct": 100.0}], "molar", 8.0, 20.0, "real")
