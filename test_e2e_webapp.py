"""Comprehensive End-to-End (E2E) and Dynamic Evaluation Test Suite for WebApp and API.

Verifies:
1. Live dynamic data entry (scheduleRecalc / calculate silent flow).
2. Phase transformations (gas condensation at -150 C into LNG, boiling liquids)
   and Advanced Two-Phase HEM calculation returning 200 OK.
3. Service tab switching, preset changes, and bidirectional unit conversions.
4. Static DOM contract and user journey validation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Suite 1: DOM Elements & Contract Integrity
# ---------------------------------------------------------------------------
class TestWebappDomContract:
    """Verifies that index.html contains all critical DOM elements bound by app.js."""

    def test_index_page_returns_200_and_contains_html(self) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "<!DOCTYPE html>" in response.text or "<html" in response.text

    def test_dom_has_tab_elements(self) -> None:
        html = client.get("/").text
        for tab_id in ["tab-liquid", "tab-gas", "tab-steam"]:
            assert f'id="{tab_id}"' in html, f"Missing tab element: {tab_id}"

    def test_dom_has_phase_alert_boxes_and_switch_buttons(self) -> None:
        html = client.get("/").text
        expected_ids = [
            "liquid-phase-alert",
            "gas-phase-alert",
            "steam-phase-alert",
            "gas-phase-switch-btn",
            "liquid-phase-switch-btn",
            "steam-phase-switch-btn",
        ]
        for el_id in expected_ids:
            assert f'id="{el_id}"' in html, f"Missing phase transition element: {el_id}"

    def test_dom_has_advance_calc_and_target_dn_elements(self) -> None:
        html = client.get("/").text
        for el_id in ["btn-advance-calc", "target-dn", "sizing-form", "calculate", "calc-status", "error"]:
            assert f'id="{el_id}"' in html, f"Missing element: {el_id}"

    def test_dom_has_param_info_modal_and_technical_details_info_contract(self) -> None:
        """Verifies that Technical Details info modal and interactive elements exist and are bound."""
        html = client.get("/").text
        expected_info_ids = [
            "info-modal",
            "info-modal-title",
            "info-modal-close",
            "info-modal-symbol",
            "info-modal-key",
            "info-modal-formula-wrap",
            "info-modal-formula",
            "info-modal-desc",
            "info-modal-ok",
        ]
        for el_id in expected_info_ids:
            assert f'id="{el_id}"' in html, f"Missing info modal element: {el_id}"

        js = client.get("/app.js").text
        assert "showParamInfo" in js
        assert "setupInfoModal" in js
        assert "PARAMETER_INFOS" in js
        assert "info-icon-btn" in js

    def test_static_assets_available(self) -> None:
        js_resp = client.get("/app.js")
        assert js_resp.status_code == 200
        assert "scheduleRecalc" in js_resp.text
        assert "calculate" in js_resp.text

        css_resp = client.get("/styles.css")
        assert css_resp.status_code == 200


# ---------------------------------------------------------------------------
# Suite 2: Live Dynamic Evaluation Flow (Silent Recalculation)
# ---------------------------------------------------------------------------
class TestLiveDynamicEvaluation:
    """Verifies smooth, uninterrupted calculation when inputs change live."""

    def test_initial_liquid_live_calculation(self) -> None:
        payload = {
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 15.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_value": 25.0,
            "flow_unit": "m3h",
            "pressure_unit": "bar_a",
            "p1_value": 8.0,
            "p2_value": 5.0,
            "temperature_value": 25.0,
            "temperature_unit": "C",
            "density_kg_m3": 998.0,
            "vapor_pressure_value": 0.023,
            "critical_pressure_value": 220.64,
            "viscosity_pa_s": 0.00089,
            "advanced_two_phase": False,
        }
        res = client.post("/api/size/liquid", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["service"] == "liquid"
        assert data["required_cv"] > 0
        assert data["valve_dn_mm"] in (25, 40, 50, 80)
        assert 20 <= data["opening_percent"] <= 90

    def test_live_keystroke_flow_variation(self) -> None:
        """Simulates rapid typing into the flow input (10 -> 25 -> 50 -> 100 m3/h)."""
        base_payload = {
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_unit": "m3h",
            "pressure_unit": "bar_a",
            "p1_value": 10.0,
            "p2_value": 7.0,
            "temperature_value": 20.0,
            "temperature_unit": "C",
            "density_kg_m3": 998.2,
            "vapor_pressure_value": 0.0234,
            "critical_pressure_value": 220.64,
            "viscosity_pa_s": 0.001,
            "advanced_two_phase": False,
        }
        previous_cv = 0.0
        for flow in [10.0, 25.0, 50.0, 100.0]:
            payload = dict(base_payload, flow_value=flow)
            res = client.post("/api/size/liquid", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["required_cv"] > previous_cv
            previous_cv = data["required_cv"]

    def test_live_delta_p_variation(self) -> None:
        """Simulates moving P2 closer to P1 (DeltaP shrinks -> required Cv increases)."""
        base_payload = {
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_value": 30.0,
            "flow_unit": "m3h",
            "pressure_unit": "bar_a",
            "p1_value": 10.0,
            "temperature_value": 25.0,
            "temperature_unit": "C",
            "density_kg_m3": 998.0,
            "vapor_pressure_value": 0.023,
            "critical_pressure_value": 220.64,
            "viscosity_pa_s": 0.00089,
            "advanced_two_phase": False,
        }
        res_high_dp = client.post("/api/size/liquid", json=dict(base_payload, p2_value=5.0))
        res_low_dp = client.post("/api/size/liquid", json=dict(base_payload, p2_value=9.0))
        assert res_high_dp.status_code == 200
        assert res_low_dp.status_code == 200
        assert res_low_dp.json()["required_cv"] > res_high_dp.json()["required_cv"]

    def test_live_target_dn_override(self) -> None:
        payload = {
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 15.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_value": 25.0,
            "flow_unit": "m3h",
            "pressure_unit": "bar_a",
            "p1_value": 8.0,
            "p2_value": 5.0,
            "temperature_value": 25.0,
            "temperature_unit": "C",
            "density_kg_m3": 998.0,
            "vapor_pressure_value": 0.023,
            "critical_pressure_value": 220.64,
            "viscosity_pa_s": 0.00089,
            "target_dn_mm": 80,
            "advanced_two_phase": False,
        }
        res = client.post("/api/size/liquid", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["valve_dn_mm"] == 80


# ---------------------------------------------------------------------------
# Suite 3: Phase Transformations & Advanced Two-Phase (HEM) Handling
# ---------------------------------------------------------------------------
class TestPhaseTransformationsAndTwoPhaseHEM:
    """Focus Area 2: Gas condensing into LNG (-150 C), flashing liquid, boiling."""

    def test_gas_diagnostic_identifies_lng_condensation_at_minus_150c(self) -> None:
        """POST /api/gas-properties should identify liquid/LNG condensation."""
        payload = {
            "gas_preset": "Doğal Gaz",
            "gas_model": "auto",
            "pressure_value": 8.0,
            "pressure_unit": "bar_a",
            "temperature_value": -150.0,
            "temperature_unit": "C",
        }
        res = client.post("/api/gas-properties", json=payload)
        assert res.status_code == 200
        diag = res.json().get("phase_diagnostic") or {}
        assert diag.get("is_phase_mismatch") is True
        assert "LNG" in (diag.get("phase_label_tr") or "")
        assert diag.get("suggested_action") is not None
        assert diag["suggested_action"]["target_service"] == "liquid"

    def test_gas_condensing_without_two_phase_flag_returns_diagnostic_warning(self) -> None:
        """Standard gas sizing without advanced_two_phase rejects non-gas phase with informative error."""
        payload = {
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_value": 800.0,
            "flow_unit": "nm3h",
            "pressure_unit": "bar_a",
            "p1_value": 8.0,
            "p2_value": 5.0,
            "temperature_value": -150.0,
            "temperature_unit": "C",
            "gas_preset": "Doğal Gaz",
            "gas_model": "auto",
            "advanced_two_phase": False,
        }
        res = client.post("/api/size/gas", json=payload)
        assert res.status_code == 400
        assert "sıvı" in res.json()["detail"].lower() or "faz" in res.json()["detail"].lower()

    def test_gas_condensing_with_advanced_two_phase_returns_200_and_hem_result(self) -> None:
        """Focus Area 2 Core: When advanced_two_phase=True, -150 C LNG condensation MUST return 200 OK."""
        payload = {
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_value": 800.0,
            "flow_unit": "nm3h",
            "pressure_unit": "bar_a",
            "p1_value": 8.0,
            "p2_value": 5.0,
            "temperature_value": -150.0,
            "temperature_unit": "C",
            "gas_preset": "Doğal Gaz",
            "gas_model": "auto",
            "advanced_two_phase": True,
        }
        res = client.post("/api/size/gas", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["required_cv"] > 0
        assert data["valve_dn_mm"] > 0
        assert "two_phase_analysis" in data
        analysis = data["two_phase_analysis"]
        assert analysis["enabled"] is True

    def test_flashing_liquid_with_advanced_two_phase_hem(self) -> None:
        """Flashing water (P2 < Pv): P1=5 bar, P2=0.5 bar, T=100 C (Pv=1.013 bar)."""
        payload = {
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 15.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_value": 40.0,
            "flow_unit": "m3h",
            "pressure_unit": "bar_a",
            "p1_value": 5.0,
            "p2_value": 0.5,
            "temperature_value": 100.0,
            "temperature_unit": "C",
            "density_kg_m3": 958.0,
            "vapor_pressure_value": 1.013,
            "critical_pressure_value": 220.64,
            "viscosity_pa_s": 0.00028,
            "advanced_two_phase": True,
            "pipe_inlet_diameter_mm": 80.0,
            "pipe_outlet_diameter_mm": 80.0,
        }
        res = client.post("/api/size/liquid", json=payload)
        assert res.status_code == 200
        data = res.json()
        analysis = data.get("two_phase_analysis")
        assert analysis is not None
        assert analysis["is_flashing"] is True
        assert analysis["cv_two_phase"] >= analysis["cv_single_phase"]
        assert analysis["rho_tp_kg_m3"] < payload["density_kg_m3"]
        assert len(analysis["recommendations"]) > 0

    def test_steam_wetness_detection_with_advanced_two_phase(self) -> None:
        """Low temperature steam near condensation (P1=10 bar, P2=3 bar, T=185 C)."""
        payload = {
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_value": 2000.0,
            "flow_unit": "kgh",
            "pressure_unit": "bar_a",
            "p1_value": 10.0,
            "p2_value": 3.0,
            "temperature_value": 185.0,
            "temperature_unit": "C",
            "advanced_two_phase": True,
        }
        res = client.post("/api/size/steam", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["required_cv"] > 0
        analysis = data.get("two_phase_analysis")
        assert analysis is not None
        assert analysis["enabled"] is True


# ---------------------------------------------------------------------------
# Suite 4: Tab Switching, Presets, and Inter-Service Continuity
# ---------------------------------------------------------------------------
class TestServiceSwitchingAndPresets:
    """Focus Area 3: Liquid, Gas, and Steam continuity."""

    def test_liquid_preset_fetch_water(self) -> None:
        res = client.post(
            "/api/liquid-properties",
            json={
                "preset": "Water",
                "pressure_value": 8.0,
                "pressure_unit": "bar_a",
                "temperature_value": 25.0,
                "temperature_unit": "C",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["density_kg_m3"] == pytest.approx(997.0, rel=0.01)

    def test_liquid_preset_fetch_lng(self) -> None:
        res = client.post(
            "/api/liquid-properties",
            json={
                "preset": "LNG",
                "pressure_value": 5.0,
                "pressure_unit": "bar_a",
                "temperature_value": -160.0,
                "temperature_unit": "C",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["density_kg_m3"] == pytest.approx(430.0, rel=0.1)

    def test_seamless_cross_service_sizing(self) -> None:
        """Simulates user clicking Liquid -> Gas -> Steam tabs in one session."""
        liq = client.post("/api/size/liquid", json={
            "vendor": "samson_globe_eqpct", "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage", "authority_pr": 0.5,
            "flow_value": 35.0, "flow_unit": "m3h", "pressure_unit": "bar_a",
            "p1_value": 6.0, "p2_value": 4.0, "temperature_value": 30.0,
            "temperature_unit": "C", "density_kg_m3": 995.0,
            "vapor_pressure_value": 0.042, "critical_pressure_value": 220.64,
            "viscosity_pa_s": 0.0008, "advanced_two_phase": False,
        })
        assert liq.status_code == 200

        gas = client.post("/api/size/gas", json={
            "vendor": "samson_globe_eqpct", "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage", "authority_pr": 0.5,
            "flow_value": 1200.0, "flow_unit": "nm3h", "pressure_unit": "bar_a",
            "p1_value": 7.0, "p2_value": 4.0, "temperature_value": 25.0,
            "temperature_unit": "C", "gas_preset": "Hava", "gas_model": "auto",
            "advanced_two_phase": False,
        })
        assert gas.status_code == 200

        stm = client.post("/api/size/steam", json={
            "vendor": "samson_globe_eqpct", "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage", "authority_pr": 0.5,
            "flow_value": 1800.0, "flow_unit": "kgh", "pressure_unit": "bar_a",
            "p1_value": 12.0, "p2_value": 8.0, "temperature_value": 230.0,
            "temperature_unit": "C", "advanced_two_phase": False,
        })
        assert stm.status_code == 200


# ---------------------------------------------------------------------------
# Suite 5: Dynamic Unit Conversion & Recalculation Consistency
# ---------------------------------------------------------------------------
class TestUnitConversionsAndEquivalence:
    """Focus Area 3: Bidirectional unit conversions maintain sizing equivalence."""

    def test_pressure_conversion_roundtrip(self) -> None:
        res = client.post("/api/convert", json={
            "kind": "pressure",
            "values": [10.0],
            "from_unit": "bar_a",
            "to_unit": "psi_a",
        })
        assert res.status_code == 200
        psi_val = res.json()["values"][0]
        assert psi_val == pytest.approx(145.038, rel=1e-3)

        res_back = client.post("/api/convert", json={
            "kind": "pressure",
            "values": [psi_val],
            "from_unit": "psi_a",
            "to_unit": "bar_a",
        })
        assert res_back.status_code == 200
        assert res_back.json()["values"][0] == pytest.approx(10.0, rel=1e-3)

    def test_liquid_flow_conversion_m3h_to_gpm(self) -> None:
        res = client.post("/api/convert", json={
            "kind": "liquid_flow",
            "values": [25.0],
            "from_unit": "m3h",
            "to_unit": "gpm",
            "density_kg_m3": 1000.0,
        })
        assert res.status_code == 200
        gpm_val = res.json()["values"][0]
        assert gpm_val == pytest.approx(25.0 * 4.40287, rel=1e-3)

    def test_sizing_identical_under_unit_switch(self) -> None:
        """Sizing with 25 m3/h at 8/5 bar_a must match sizing with 110.07 gpm at 116.03/72.52 psi_a."""
        res_si = client.post("/api/size/liquid", json={
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_value": 25.0,
            "flow_unit": "m3h",
            "pressure_unit": "bar_a",
            "p1_value": 8.0,
            "p2_value": 5.0,
            "temperature_value": 20.0,
            "temperature_unit": "C",
            "density_kg_m3": 998.2,
            "vapor_pressure_value": 0.0234,
            "critical_pressure_value": 220.64,
            "viscosity_pa_s": 0.001,
        })
        assert res_si.status_code == 200
        cv_si = res_si.json()["required_cv"]

        res_imperial = client.post("/api/size/liquid", json={
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_value": 25.0 * 4.402868,
            "flow_unit": "gpm",
            "pressure_unit": "psi_a",
            "p1_value": 8.0 * 14.50377,
            "p2_value": 5.0 * 14.50377,
            "temperature_value": 68.0,
            "temperature_unit": "F",
            "density_kg_m3": 998.2,
            "vapor_pressure_value": 0.0234 * 14.50377,
            "critical_pressure_value": 220.64 * 14.50377,
            "viscosity_pa_s": 0.001,
        })
        assert res_imperial.status_code == 200
        cv_imperial = res_imperial.json()["required_cv"]

        assert cv_si == pytest.approx(cv_imperial, rel=0.002)


# ---------------------------------------------------------------------------
# Suite 6: Multi-Case Operating Envelope & Robust Error Paths
# ---------------------------------------------------------------------------
class TestMultiCaseAndRobustness:
    """Verifies operating envelope and graceful error recovery."""

    def test_multicase_envelope_evaluation(self) -> None:
        payload = {
            "service": "liquid",
            "vendor": "fisher_globe_eqpct",
            "flow_characteristic": "equal_percentage",
            "cases": [
                {"name": "Min", "flow": 10.0, "p1_bar_a": 9.0, "p2_bar_a": 6.0, "temperature_c": 20.0},
                {"name": "Norm", "flow": 25.0, "p1_bar_a": 8.0, "p2_bar_a": 5.0, "temperature_c": 25.0},
                {"name": "Max", "flow": 40.0, "p1_bar_a": 7.0, "p2_bar_a": 4.0, "temperature_c": 30.0},
            ],
            "base_fluid_data": {
                "density_kg_m3": 998.0,
                "vapor_pressure_bar_a": 0.023,
                "critical_pressure_bar_a": 220.64,
                "viscosity_pa_s": 0.00089,
            },
        }
        res = client.post("/api/size/multi-case", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert len(data["cases"]) == 3
        assert data["recommended"] is not None

    def test_invalid_negative_flow_returns_graceful_400(self) -> None:
        payload = {
            "vendor": "fisher_globe_eqpct",
            "design_margin_pct": 10.0,
            "flow_characteristic": "equal_percentage",
            "authority_pr": 0.5,
            "flow_value": -15.0,
            "flow_unit": "m3h",
            "pressure_unit": "bar_a",
            "p1_value": 8.0,
            "p2_value": 5.0,
            "temperature_value": 20.0,
            "temperature_unit": "C",
            "density_kg_m3": 998.0,
            "vapor_pressure_value": 0.023,
            "critical_pressure_value": 220.64,
            "viscosity_pa_s": 0.001,
        }
        res = client.post("/api/size/liquid", json=payload)
        assert res.status_code == 400
        assert "pozitif" in res.json()["detail"].lower()
