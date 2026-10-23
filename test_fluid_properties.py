from __future__ import annotations

import pytest

from fluid_properties import (
    evaluate_liquid_preset,
    evaluate_steam_state,
    gas_component_options,
    get_pure_fluid_state,
    get_saturated_steam_pressure,
    get_saturated_steam_temperature,
    list_coolprop_fluids,
)


def test_pure_fluid_state_water():
    state = get_pure_fluid_state("Water", 10.0, 25.0)
    assert state["density_kg_m3"] > 990.0
    assert state["viscosity_pa_s"] > 0.0
    assert state["vapor_pressure_bar_a"] is not None
    assert 0.02 < state["vapor_pressure_bar_a"] < 0.05
    assert state["critical_pressure_bar_a"] > 200.0


def test_pure_fluid_state_supercritical_co2():
    state = get_pure_fluid_state("CarbonDioxide", 100.0, 50.0)
    assert state["density_kg_m3"] > 100.0
    assert state["molecular_weight"] == pytest.approx(44.01, rel=1e-2)
    assert state["critical_pressure_bar_a"] > 70.0


def test_evaluate_liquid_preset_water():
    res = evaluate_liquid_preset("Water", 5.0, 20.0)
    assert res["density_kg_m3"] == pytest.approx(998.2, rel=1e-2)
    assert res["temperature_corrected"] is True


def test_evaluate_liquid_preset_methanol():
    res = evaluate_liquid_preset("Methanol", 5.0, 20.0)
    assert res["density_kg_m3"] > 700.0
    assert res["temperature_corrected"] is True


def test_steam_saturation_helpers():
    t_sat_1bar = get_saturated_steam_temperature(1.01325)
    assert 99.0 <= t_sat_1bar <= 101.0
    p_sat_100c = get_saturated_steam_pressure(100.0)
    assert 0.98 <= p_sat_100c <= 1.05


def test_evaluate_steam_state_superheated():
    state = evaluate_steam_state(10.0, 250.0)
    assert state["phase"] == "superheated"
    assert state["delta_t_superheat"] > 50.0


def test_evaluate_steam_state_wet():
    t_sat = get_saturated_steam_temperature(10.0)
    state = evaluate_steam_state(10.0, t_sat - 10.0)
    assert state["phase"] == "wet_steam"
    assert len(state["warnings"]) > 0


def test_fluids_lists_populated():
    cp_fluids = list_coolprop_fluids()
    assert "Water" in cp_fluids
    assert "Methane" in cp_fluids
    gas_opts = gas_component_options()
    assert len(gas_opts) > 10
