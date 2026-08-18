"""Benchmark tests against published IEC 60534-2-1 / ISA-75.01.01 sizing examples.

Reference values are the worked examples documented by the fluids library
(which implements the IEC standard equations). These tests pin the project's
wrapper functions to the standard so that any regression in unit conversion,
candidate selection, or choked-flow handling is caught.
"""

from __future__ import annotations

from unittest import mock

from fluids.control_valve import size_control_valve_g, size_control_valve_l

from valve_sizing import (
    GasSizingInput,
    LiquidSizingInput,
    SteamSizingInput,
    ValveSize,
    size_gas_valve,
    size_liquid_valve,
    size_steam_valve,
)


def test_iec_liquid_globe_example_fluids():
    result = size_control_valve_l(
        rho=965.4, Psat=70.1e3, Pc=22120e3, mu=3.1472e-4,
        P1=680e3, P2=220e3, Q=0.1, D1=0.15, D2=0.15, d=0.15,
        FL=0.9, Fd=0.46,
    )
    assert result == 164.9954763704956


def test_iec_liquid_ball_example_fluids():
    result = size_control_valve_l(
        rho=965.4, Psat=70.1e3, Pc=22120e3, mu=3.1472e-4,
        P1=680e3, P2=220e3, Q=0.1, D1=0.1, D2=0.1, d=0.1,
        FL=0.6, Fd=0.98,
    )
    assert result == 238.05817216710483


def test_iec_gas_example_fluids():
    result = size_control_valve_g(
        T=433.0, MW=44.01, mu=1.4665e-4, gamma=1.30, Z=0.988,
        P1=680e3, P2=310e3, Q=38.0 / 36.0, D1=0.08, D2=0.1, d=0.05,
        FL=0.85, Fd=0.42, xT=0.60,
    )
    assert result == 72.5866454539105


def test_wrapper_liquid_globe_matches_iec():
    series = [ValveSize(150, '6"', 1e5)]
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=360.0,
            inlet_pressure_bar_a=6.8,
            outlet_pressure_bar_a=2.2,
            density_kg_m3=965.4,
            vapor_pressure_bar_a=0.701,
            critical_pressure_bar_a=221.2,
            viscosity_pa_s=3.1472e-4,
            fl=0.9,
            fd=0.46,
            pipe_inlet_diameter_mm=150.0,
            pipe_outlet_diameter_mm=150.0,
        ),
        valve_series=series,
    )
    assert abs(result["required_kv"] - 164.9955) / 164.9955 < 0.01


def test_wrapper_liquid_ball_matches_iec():
    series = [ValveSize(100, '4"', 1e5)]
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=360.0,
            inlet_pressure_bar_a=6.8,
            outlet_pressure_bar_a=2.2,
            density_kg_m3=965.4,
            vapor_pressure_bar_a=0.701,
            critical_pressure_bar_a=221.2,
            viscosity_pa_s=3.1472e-4,
            fl=0.6,
            fd=0.98,
            pipe_inlet_diameter_mm=100.0,
            pipe_outlet_diameter_mm=100.0,
        ),
        valve_series=series,
    )
    assert abs(result["required_kv"] - 238.058) / 238.058 < 0.01


def test_wrapper_gas_matches_iec():
    series = [ValveSize(50, '2"', 1e5)]
    q_actual_m3h = (38.0 / 36.0) * 3600.0
    flow_nm3h = q_actual_m3h / ((1.01325 / 6.8) * (433.15 / 273.15) * 0.988)
    result = size_gas_valve(
        GasSizingInput(
            flow_nm3h=flow_nm3h,
            inlet_pressure_bar_a=6.8,
            outlet_pressure_bar_a=3.1,
            temperature_c=159.85,
            molecular_weight=44.01,
            specific_heat_ratio=1.30,
            viscosity_pa_s=1.4665e-4,
            z=0.988,
            fl=0.85,
            fd=0.42,
            xt=0.60,
            pipe_inlet_diameter_mm=80.0,
            pipe_outlet_diameter_mm=100.0,
        ),
        valve_series=series,
    )
    assert abs(result["required_kv"] - 72.587) / 72.587 < 0.01


def test_steam_matches_ideal_gas_gas_path():
    gas_result = size_gas_valve(
        GasSizingInput(
            flow_nm3h=800.0,
            inlet_pressure_bar_a=12.0,
            outlet_pressure_bar_a=8.0,
            temperature_c=220.0,
            molecular_weight=18.015,
            specific_heat_ratio=1.30,
            viscosity_pa_s=1.5e-5,
            z=1.0,
            xt=0.72,
            fl=0.9,
            fd=1.0,
        ),
        valve_series=[ValveSize(50, '2"', 1e5)],
    )
    density_ideal = (12e5 * 18.015e-3) / (8.314 * 493.15)
    density_normal = (1.01325e5 * 18.015e-3) / (8.314 * 273.15)
    flow_kg_h = 800.0 * density_normal
    props = {
        "density_kg_m3": density_ideal,
        "viscosity_pa_s": 1.5e-5,
        "cp_kj_kgk": 2.1,
        "cv_kj_kgk": 1.615,
        "specific_heat_ratio": 1.30,
        "z": 1.0,
        "enthalpy_kj_kg": 2900.0,
        "entropy_kj_kgk": 6.5,
        "thermal_conductivity_w_mk": 0.04,
        "phase": "Vapour",
    }
    with mock.patch("fluid_properties.get_steam_properties_iapws", return_value=props):
        steam_result = size_steam_valve(
            SteamSizingInput(
                flow_kg_h=flow_kg_h,
                inlet_pressure_bar_a=12.0,
                outlet_pressure_bar_a=8.0,
                temperature_c=220.0,
                specific_heat_ratio=1.30,
                z=1.0,
                xt=0.72,
                fl=0.9,
                fd=1.0,
                pipe_inlet_diameter_mm=50.0,
                pipe_outlet_diameter_mm=50.0,
            ),
            valve_series=[ValveSize(50, '2"', 1e5)],
        )
    assert abs(steam_result["required_kv"] - gas_result["required_kv"]) / gas_result["required_kv"] < 0.02
