"""Tests for web API improvements and new endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import app

client = TestClient(app)


def test_project_export_and_import_roundtrip():
    data = {
        "liquid_flow_m3h": 25.0,
        "liquid_p1": 8.0,
        "liquid_p2": 5.0,
        "liquid_temp_unit": "C",
        "liquid_pres_unit": "bar_a",
        "liquid_flow_unit": "m3h",
    }
    export_resp = client.post("/api/project/export", json={"service": "liquid", "data": data})
    assert export_resp.status_code == 200
    payload = export_resp.json()
    assert payload["project_type"] == "control_valve_sizing"
    assert payload["service"] == "liquid"
    assert payload["schema_version"] == 1

    import_resp = client.post("/api/project/import", json=payload)
    assert import_resp.status_code == 200
    assert import_resp.json()["data"]["liquid_flow_m3h"] == 25.0


def test_isa20_report_generation():
    liquid_payload = {
        "flow_value": 25.0,
        "flow_unit": "m3h",
        "pressure_unit": "bar_a",
        "p1_value": 8.0,
        "p2_value": 5.0,
        "temperature_value": 25.0,
        "temperature_unit": "C",
        "density_kg_m3": 998.0,
        "vapor_pressure_value": 0.023,
        "vapor_pressure_unit": "bar_a",
        "critical_pressure_value": 220.64,
        "critical_pressure_unit": "bar_a",
        "viscosity_pa_s": 0.00089,
        "vendor": "fisher_globe_eqpct",
        "design_margin_pct": 15.0,
        "flow_characteristic": "equal_percentage",
        "pipe_inlet_diameter_mm": 50.0,
        "pipe_outlet_diameter_mm": 50.0,
        "authority_pr": 0.5,
    }
    size_resp = client.post("/api/size/liquid", json=liquid_payload)
    assert size_resp.status_code == 200
    result = size_resp.json()

    isa_resp = client.post(
        "/api/report/isa20",
        json={
            "tag_number": "FCV-1001",
            "service_description": "Boiler Feedwater Control",
            "line_number": '2"-BFW-101',
            "pid_number": "P&ID-402",
            "service_type": "Liquid",
            "fluid_name": "Water",
            "sizing_result": result,
            "vendor_key": "fisher_globe_eqpct",
        },
    )
    assert isa_resp.status_code == 200
    data = isa_resp.json()
    assert "FCV-1001" in data["markdown"]
    assert "ISA FORM 20" in data["html"]
    assert data["datasheet"]["tag_number"] == "FCV-1001"


def test_markdown_report_generation():
    liquid_payload = {
        "flow_value": 25.0,
        "flow_unit": "m3h",
        "pressure_unit": "bar_a",
        "p1_value": 8.0,
        "p2_value": 5.0,
        "temperature_value": 25.0,
        "temperature_unit": "C",
        "density_kg_m3": 998.0,
        "vapor_pressure_value": 0.023,
        "vapor_pressure_unit": "bar_a",
        "critical_pressure_value": 220.64,
        "critical_pressure_unit": "bar_a",
        "viscosity_pa_s": 0.00089,
        "vendor": "fisher_globe_eqpct",
    }
    size_resp = client.post("/api/size/liquid", json=liquid_payload)
    result = size_resp.json()

    report_resp = client.post(
        "/api/report/markdown",
        json={
            "service": "Liquid",
            "fluid_summary": {"Fluid": "Water", "Density": "998 kg/m3"},
            "sizing_result": result,
        },
    )
    assert report_resp.status_code == 200
    md = report_resp.json()["report_markdown"]
    assert "Control Valve Sizing Report" in md
    assert "Required Cv" in md


def test_multicase_endpoint():
    cases = [
        {"name": "Min", "flow": 5.0, "p1_bar_a": 8.5, "p2_bar_a": 5.0, "temperature_c": 25.0},
        {"name": "Norm", "flow": 25.0, "p1_bar_a": 8.0, "p2_bar_a": 5.0, "temperature_c": 25.0},
        {"name": "Max", "flow": 45.0, "p1_bar_a": 7.5, "p2_bar_a": 5.0, "temperature_c": 25.0},
    ]
    base_fluid = {
        "density_kg_m3": 998.0,
        "vapor_pressure_bar_a": 0.023,
        "critical_pressure_bar_a": 220.64,
        "viscosity_pa_s": 0.00089,
        "fl": 0.9,
    }
    resp = client.post(
        "/api/size/multi-case",
        json={
            "service": "liquid",
            "cases": cases,
            "base_fluid_data": base_fluid,
            "vendor": "fisher_globe_eqpct",
            "flow_characteristic": "equal_percentage",
        },
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["service"] == "liquid"
    assert res["turndown_ratio"] == pytest.approx(9.0)
    assert res["recommended"] is not None
    assert "Min" in res["recommended"]["case_details"]
    assert "Norm" in res["recommended"]["case_details"]
    assert "Max" in res["recommended"]["case_details"]
