"""Unit tests for the 10 iterative continuous improvement cycles."""

import math

import pytest


def test_thermal_expansion_cryogenic_contraction():
    from thermal_expansion import expansion_loop_length, pipe_linear_expansion, pipe_thermal_stress

    # Cryogenic service: -160 C delta T
    delta_l = pipe_linear_expansion(50.0, -160.0, "stainless_304")
    assert delta_l < 0
    # Loop calculation must handle contraction without complex number error
    loop_m = expansion_loop_length(50.0, -160.0, "stainless_304", 150.0)
    assert loop_m > 0
    assert math.isfinite(loop_m)

    stress = pipe_thermal_stress(-160.0, "stainless_304")
    assert stress < 0  # tensile contraction stress


def test_units_delta_pressure_conversions():
    from units import delta_pressure_from_bar, delta_pressure_to_bar

    # 1 bar delta P in psi
    psi_dp = delta_pressure_from_bar(1.0, "psi_g")
    assert psi_dp == pytest.approx(14.50377, rel=1e-3)

    # 14.50377 psi delta P back to bar (no atmospheric addition)
    bar_dp = delta_pressure_to_bar(psi_dp, "psi_a")
    assert bar_dp == pytest.approx(1.0, rel=1e-3)

    # kPa and MPa
    assert delta_pressure_to_bar(100.0, "kPa_a") == pytest.approx(1.0)
    assert delta_pressure_to_bar(0.1, "MPa_g") == pytest.approx(1.0)


def test_multicase_cv_turndown():
    from multi_case import OperatingCase, size_multicase

    # Cases where Delta P varies widely between min and max
    cases = [
        OperatingCase("Min", flow=10.0, p1_bar_a=15.0, p2_bar_a=5.0, temperature_c=25.0),
        OperatingCase("Normal", flow=50.0, p1_bar_a=12.0, p2_bar_a=8.0, temperature_c=25.0),
        OperatingCase("Max", flow=120.0, p1_bar_a=10.0, p2_bar_a=9.0, temperature_c=25.0),
    ]
    fluid_data = {"density_kg_m3": 1000.0, "viscosity_pa_s": 0.001, "vapor_pressure_bar_a": 0.023, "critical_pressure_bar_a": 220.64}
    analysis = size_multicase("liquid", cases, fluid_data)
    assert analysis.turndown_ratio == pytest.approx(12.0)  # 120 / 10
    assert analysis.cv_turndown_ratio > analysis.turndown_ratio  # Cv turndown is larger due to delta P


def test_split_range_design_and_reporting():
    from multi_case import OperatingCase, size_multicase
    from reporting import build_multicase_report

    # Extreme turndown: 2 m3/h at deltaP=8 bar to 200 m3/h at deltaP=2 bar (Turndown > 100:1)
    cases = [
        OperatingCase("Min", flow=2.0, p1_bar_a=10.0, p2_bar_a=2.0, temperature_c=25.0),
        OperatingCase("Normal", flow=40.0, p1_bar_a=8.0, p2_bar_a=4.0, temperature_c=25.0),
        OperatingCase("Max", flow=200.0, p1_bar_a=6.0, p2_bar_a=4.0, temperature_c=25.0),
    ]
    fluid_data = {
        "density_kg_m3": 1000.0,
        "viscosity_pa_s": 0.001,
        "vapor_pressure_bar_a": 0.023,
        "critical_pressure_bar_a": 220.64,
    }
    analysis = size_multicase("liquid", cases, fluid_data)
    assert analysis.split_range is not None
    assert analysis.split_range.small_valve.dn_mm < analysis.split_range.large_valve.dn_mm
    assert analysis.split_range.combined_rangeability > 50.0

    report = build_multicase_report(analysis)
    assert "Paralel Split-Range Vana" in report
    assert "Vana A (Küçük Debi)" in report



def test_packing_emissions_temperature_advisories():
    from packing_emissions import recommend_packing_system

    # Cryogenic
    cryo = recommend_packing_system("liquid", "Methane", -160.0, 10.0)
    assert any("Kriyojenik" in r for r in cryo.recommendations)

    # Extreme high temp
    hot = recommend_packing_system("steam", "Steam", 500.0, 40.0)
    assert any("Grafit" in r or "radyasyon" in r.lower() for r in hot.recommendations)


def test_safety_piping_pc_usage_in_relief():
    from safety_piping import calc_wide_open_relief_capacity

    fluid_with_pc = {
        "specific_gravity": 1.0,
        "vapor_pressure_bar_a": 1.0,
        "critical_pressure_bar_a": 220.64,
        "fl": 0.90,
    }
    res = calc_wide_open_relief_capacity("liquid", 50.0, 10.0, 2.0, fluid_with_pc)
    assert res.wide_open_flow_rate > 0
    assert res.is_choked is True


def test_datasheet_isa20_contains_vendor_matches():
    from datasheet_isa20 import build_isa20_datasheet
    from valve_sizing import LiquidSizingInput, size_liquid_valve

    inp = LiquidSizingInput(
        flow_m3h=45.0,
        inlet_pressure_bar_a=8.0,
        outlet_pressure_bar_a=5.0,
        density_kg_m3=998.0,
        vapor_pressure_bar_a=0.023,
        critical_pressure_bar_a=220.64,
        viscosity_pa_s=0.001,
        fl=0.90,
    )
    result = size_liquid_valve(inp)
    ds = build_isa20_datasheet(
        tag_number="CV-001",
        service_description="Feed water",
        line_number="10-CW-101",
        pid_number="PID-101",
        service_type="liquid",
        fluid_name="Water",
        sizing_result=result,
    )
    assert any("Uyumlu Global Modeller" in n for n in ds.engineering_notes)
