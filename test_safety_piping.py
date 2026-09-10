"""Unit tests for safety piping (API 14E / API 520), noise attenuation, and material selection."""

from safety_piping import calc_wide_open_relief_capacity, check_erosional_velocity
from valve_noise import evaluate_noise_attenuation
from valve_selection import recommend_alloy_material, recommend_bonnet_type


def test_api14e_erosional_velocity_liquid():
    safe = check_erosional_velocity(actual_velocity_m_s=2.5, density_kg_m3=1000.0)
    assert safe.is_velocity_exceeded is False
    assert safe.erosional_limit_m_s > 3.8
    assert safe.velocity_ratio < 1.0

    exceeded = check_erosional_velocity(
        actual_velocity_m_s=6.0,
        density_kg_m3=1000.0,
        actual_flow_m3_s=0.03,
    )
    assert exceeded.is_velocity_exceeded is True
    assert exceeded.velocity_ratio > 1.0
    assert len(exceeded.warnings) > 0
    assert exceeded.min_recommended_pipe_dn_mm > 0


def test_api520_wide_open_relief_capacity_liquid():
    res = calc_wide_open_relief_capacity(
        service="liquid",
        rated_cv=50.0,
        inlet_pressure_bar_a=10.0,
        relief_pressure_bar_a=4.0,
        fluid_data={"specific_gravity": 1.0, "fl": 0.9, "vapor_pressure_bar_a": 0.023},
    )
    assert res.wide_open_flow_rate > 50.0
    assert res.flow_unit == "m\u00b3/h"
    assert len(res.safety_notes) > 0


def test_api520_wide_open_relief_capacity_gas():
    res = calc_wide_open_relief_capacity(
        service="gas",
        rated_cv=80.0,
        inlet_pressure_bar_a=20.0,
        relief_pressure_bar_a=5.0,
        fluid_data={"molecular_weight": 16.04, "temperature_c": 25.0, "xt": 0.70, "specific_heat_ratio": 1.31},
    )
    assert res.wide_open_flow_rate > 1000.0
    assert res.flow_unit == "Nm\u00b3/h"
    assert res.is_choked is True


def test_api520_wide_open_relief_capacity_steam():
    res = calc_wide_open_relief_capacity(
        service="steam",
        rated_cv=30.0,
        inlet_pressure_bar_a=12.0,
        relief_pressure_bar_a=6.0,
        fluid_data={"density_kg_m3": 6.0, "xt": 0.70},
    )
    assert res.wide_open_flow_rate > 500.0
    assert res.flow_unit == "kg/h"


def test_noise_attenuation_evaluation():
    low = evaluate_noise_attenuation(noise_dba=78.0)
    assert low.is_attenuation_required is False
    assert "Gerekmez" in low.recommended_treatment

    medium = evaluate_noise_attenuation(noise_dba=95.0, service="gas", delta_p_bar=10.0)
    assert medium.is_attenuation_required is True
    assert medium.whisper_trim_dba < 85.0
    assert "Whisper Trim" in medium.recommended_treatment

    critical = evaluate_noise_attenuation(noise_dba=116.0, service="gas", delta_p_bar=30.0)
    assert critical.is_attenuation_required is True
    assert "AIV" in critical.engineering_notes[0]
    assert "Labirent" in critical.recommended_treatment


def test_bonnet_recommendations():
    cryo = recommend_bonnet_type(-160.0, service="liquid", fluid_name="LNG")
    assert "Kriyojenik" in cryo

    finned = recommend_bonnet_type(280.0, service="steam", fluid_name="Steam")
    assert "Kanatl\u0131" in finned

    hi_temp = recommend_bonnet_type(500.0, service="gas", fluid_name="FlueGas")
    assert "Y\u00fcksek S\u0131cakl\u0131k" in hi_temp

    std = recommend_bonnet_type(40.0, service="liquid", fluid_name="Water")
    assert "Standart" in std


def test_alloy_material_recommendations():
    sour = recommend_alloy_material("gas", "NaturalGas", 50.0, is_sour=True)
    assert sour.nace_compliant is True
    assert "Inconel 718" in sour.stem_material

    h2_hot = recommend_alloy_material("gas", "Hydrogen", 350.0, is_h2=True)
    assert "WC6" in h2_hot.body_material
    assert "Nelson" in h2_hot.design_standard

    lng = recommend_alloy_material("liquid", "LNG", -162.0)
    assert "CF8M" in lng.body_material
    assert lng.temperature_limits_c[0] <= -196.0

    seawater = recommend_alloy_material("liquid", "Seawater", 25.0)
    assert "Duplex 2205" in seawater.body_material or "Monel" in seawater.body_material
