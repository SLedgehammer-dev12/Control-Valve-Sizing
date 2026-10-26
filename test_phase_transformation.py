"""Tests for phase transformation and transition diagnostics (gas condensation / liquid boiling)."""

import pytest
from fastapi.testclient import TestClient

from api import app
from fluid_properties import (
    evaluate_gas_phase_state,
    evaluate_liquid_phase_state,
    evaluate_liquid_preset,
    evaluate_steam_state,
)

client = TestClient(app)


def test_natural_gas_lng_condensation_detection() -> None:
    diag = evaluate_gas_phase_state(
        "Doğal Gaz",
        pressure_bar_a=6.0,
        temperature_c=-150.0,
    )
    assert diag["is_condensed"] is True
    assert diag["is_phase_mismatch"] is True
    assert diag["is_two_phase"] is False
    assert "LNG" in diag["phase_label_tr"]
    assert diag["density_kg_m3"] is not None and diag["density_kg_m3"] > 400.0
    assert diag["t_bubble_c"] is not None and diag["t_bubble_c"] > -145.0
    assert "LNG" in diag["warning_tr"]
    assert diag["suggested_action"] is not None
    assert diag["suggested_action"]["target_service"] == "liquid"
    assert diag["suggested_action"]["preset"] == "LNG"


def test_methane_lng_condensation() -> None:
    diag = evaluate_gas_phase_state(
        "Metan",
        pressure_bar_a=6.0,
        temperature_c=-150.0,
    )
    assert diag["is_condensed"] is True
    assert diag["t_sat_c"] is not None
    assert pytest.approx(diag["t_sat_c"], abs=1.0) == -134.4
    assert diag["density_kg_m3"] is not None and diag["density_kg_m3"] > 390.0


def test_propane_lpg_condensation_detection() -> None:
    diag = evaluate_gas_phase_state(
        "Propan",
        pressure_bar_a=6.0,
        temperature_c=0.0,
    )
    assert diag["is_condensed"] is True
    assert "LPG" in diag["phase_label_tr"] or "Sıvı" in diag["phase_label_tr"]
    assert diag["suggested_action"] is not None
    assert diag["suggested_action"]["preset"] == "Propane"


def test_natural_gas_two_phase_band() -> None:
    diag = evaluate_gas_phase_state(
        "Doğal Gaz",
        pressure_bar_a=6.0,
        temperature_c=-120.0,
    )
    assert diag["is_two_phase"] is True
    assert diag["is_phase_mismatch"] is True
    assert "İki Fazlı" in diag["phase_label_tr"]
    assert "erozyon" in diag["warning_tr"].lower()


def test_gas_normal_single_phase() -> None:
    diag = evaluate_gas_phase_state(
        "Doğal Gaz",
        pressure_bar_a=6.0,
        temperature_c=25.0,
    )
    assert diag["is_condensed"] is False
    assert diag["is_two_phase"] is False
    assert diag["is_phase_mismatch"] is False
    assert diag["warning_tr"] is None
    assert diag["suggested_action"] is None


def test_liquid_inlet_boiling_diagnostic() -> None:
    # Vapor pressure = 4.76 bar >= P1 = 1.0 bar
    diag = evaluate_liquid_phase_state(
        p1_bar_a=1.0,
        vapor_pressure_bar_a=4.76,
        temperature_c=150.0,
    )
    assert diag["is_boiled_at_inlet"] is True
    assert diag["is_phase_mismatch"] is True
    assert "kaynamıştır" in diag["warning_tr"]
    assert diag["suggested_action"]["target_service"] == "steam"

    # Normal liquid
    diag_ok = evaluate_liquid_phase_state(
        p1_bar_a=8.0,
        vapor_pressure_bar_a=0.023,
        temperature_c=25.0,
    )
    assert diag_ok["is_boiled_at_inlet"] is False
    assert diag_ok["is_phase_mismatch"] is False
    assert diag_ok["warning_tr"] is None


def test_steam_subcooled_liquid_detection() -> None:
    # 12 bar(a) saturation temp is ~188 C. At 120 C, water is liquid.
    steam_diag = evaluate_steam_state(12.0, 120.0)
    assert steam_diag["is_subcooled_liquid"] is True
    assert steam_diag["is_wet"] is True
    assert steam_diag["suggested_action"] is not None
    assert steam_diag["suggested_action"]["target_service"] == "liquid"
    assert steam_diag["suggested_action"]["preset"] == "Water"


def test_gas_properties_api_returns_phase_diagnostic() -> None:
    payload = {
        "gas_preset": "Doğal Gaz",
        "gas_model": "auto",
        "pressure_value": 6.0,
        "pressure_unit": "bar_a",
        "temperature_value": -150.0,
        "temperature_unit": "C",
    }
    resp = client.post("/api/gas-properties", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "phase_diagnostic" in data
    assert data["phase_diagnostic"]["is_condensed"] is True
    assert "LNG" in data["phase_diagnostic"]["phase_label_tr"]


def test_size_gas_rejects_condensed_phase_with_rich_message() -> None:
    payload = {
        "gas_preset": "Doğal Gaz",
        "gas_model": "auto",
        "flow_value": 500.0,
        "flow_unit": "nm3h",
        "pressure_unit": "bar_a",
        "p1_value": 6.0,
        "p2_value": 4.0,
        "temperature_value": -150.0,
        "temperature_unit": "C",
    }
    resp = client.post("/api/size/gas", json=payload)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Faz Dönüşümü" in detail or "sıvı" in detail.lower()
    assert "LNG" in detail


def test_liquid_sizing_advanced_two_phase_flashing() -> None:
    # Water at 120 C: Pv ≈ 1.98 bar. P1 = 3.0 bar, P2 = 1.0 bar (P2 < Pv => Flashing!)
    props = evaluate_liquid_preset("Water", pressure_bar_a=3.0, temperature_c=120.0)
    base_payload = {
        "flow_value": 20.0,
        "flow_unit": "m3h",
        "pressure_unit": "bar_a",
        "p1_value": 3.0,
        "p2_value": 1.0,
        "temperature_value": 120.0,
        "temperature_unit": "C",
        "density_kg_m3": props["density_kg_m3"],
        "vapor_pressure_value": props["vapor_pressure_bar_a"],
        "vapor_pressure_unit": "bar_a",
        "critical_pressure_value": props["critical_pressure_bar_a"],
        "critical_pressure_unit": "bar_a",
        "viscosity_pa_s": props["viscosity_pa_s"],
    }

    # 1. Without advanced calculation (default standard)
    resp_std = client.post("/api/size/liquid", json={**base_payload, "advanced_two_phase": False})
    assert resp_std.status_code == 200
    data_std = resp_std.json()
    assert "two_phase_analysis" not in data_std or data_std["two_phase_analysis"] is None
    assert data_std.get("flow_regime") == "flashing"

    # 2. With advanced calculation active
    resp_adv = client.post("/api/size/liquid", json={**base_payload, "advanced_two_phase": True})
    assert resp_adv.status_code == 200
    data_adv = resp_adv.json()
    assert "two_phase_analysis" in data_adv
    tp = data_adv["two_phase_analysis"]
    assert tp["enabled"] is True
    assert tp["is_flashing"] is True
    assert tp["quality_x"] > 0.0
    assert tp["rho_tp_kg_m3"] < props["density_kg_m3"]
    assert tp["cv_two_phase"] > data_std["required_cv"]
    assert any("Angle" in rec or "Açılı" in rec for rec in tp["recommendations"])
    assert any("Stellite" in rec or "Tungsten" in rec for rec in tp["recommendations"])


def test_gas_sizing_advanced_two_phase_jt_drop() -> None:
    # High pressure natural gas expansion (P1=80 bar, P2=5 bar)
    payload = {
        "gas_preset": "Doğal Gaz",
        "gas_model": "auto",
        "flow_value": 2000.0,
        "flow_unit": "nm3h",
        "pressure_unit": "bar_a",
        "p1_value": 80.0,
        "p2_value": 5.0,
        "temperature_value": 20.0,
        "temperature_unit": "C",
        "advanced_two_phase": True,
    }
    resp = client.post("/api/size/gas", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "two_phase_analysis" in data
    tp = data["two_phase_analysis"]
    assert tp["enabled"] is True
    assert tp["t2_c"] < 20.0  # Cooling occurred
    assert tp["delta_t_jt_c"] < 0.0 or tp["mu_jt_c_per_bar"] > 0.0
    assert len(tp["recommendations"]) > 0


def test_steam_sizing_advanced_two_phase() -> None:
    payload = {
        "flow_value": 1500.0,
        "flow_unit": "kgh",
        "pressure_unit": "bar_a",
        "p1_value": 10.0,
        "p2_value": 2.0,
        "temperature_value": 220.0,
        "temperature_unit": "C",
        "advanced_two_phase": True,
    }
    resp = client.post("/api/size/steam", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "two_phase_analysis" in data
    tp = data["two_phase_analysis"]
    assert tp["enabled"] is True
    assert tp["t2_c"] > 0.0
    assert len(tp["recommendations"]) > 0



def test_liquid_properties_api_phase_diagnostic() -> None:
    data = evaluate_liquid_preset("Water", 1.0, 150.0)
    assert "phase_diagnostic" in data
    assert data["phase_diagnostic"]["is_boiled_at_inlet"] is True
