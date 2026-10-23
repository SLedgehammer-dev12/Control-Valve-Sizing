"""Tests for the FastAPI browser backend."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import app

client = TestClient(app)

LIQUID = {
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
    "vendor": "fisher_globe_eqpct",
    "design_margin_pct": 15.0,
    "flow_characteristic": "equal_percentage",
    "pipe_inlet_diameter_mm": 50.0,
    "pipe_outlet_diameter_mm": 50.0,
    "authority_pr": 0.5,
}

GAS = {
    "flow_value": 800.0,
    "flow_unit": "nm3h",
    "pressure_unit": "bar_a",
    "p1_value": 8.0,
    "p2_value": 6.0,
    "temperature_value": 20.0,
    "temperature_unit": "C",
    "gas_preset": "Doğal Gaz",
    "vendor": "fisher_globe_eqpct",
    "design_margin_pct": 15.0,
    "flow_characteristic": "equal_percentage",
    "pipe_inlet_diameter_mm": 80.0,
    "pipe_outlet_diameter_mm": 80.0,
    "authority_pr": 0.5,
}

STEAM = {
    "flow_value": 2500.0,
    "flow_unit": "kgh",
    "pressure_unit": "bar_a",
    "p1_value": 12.0,
    "p2_value": 8.0,
    "temperature_value": 220.0,
    "temperature_unit": "C",
    "vendor": "fisher_globe_eqpct",
    "design_margin_pct": 15.0,
    "flow_characteristic": "equal_percentage",
    "pipe_inlet_diameter_mm": 80.0,
    "pipe_outlet_diameter_mm": 80.0,
    "authority_pr": 0.5,
}


def test_health_and_meta() -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["version"]
    assert len(meta["vendors"]) >= 4
    assert len(meta["liquid_presets"]) >= 5
    assert len(meta["gas_presets"]) >= 5
    assert meta["units"]["pressure"]
    vendors = client.get("/api/vendors")
    assert vendors.status_code == 200
    assert len(vendors.json()) == len(meta["vendors"])


def test_static_index() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Control Valve Sizing" in response.text


def test_liquid_sizing_response() -> None:
    response = client.post("/api/size/liquid", json=LIQUID)
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "liquid"
    assert data["required_cv"] > 0
    assert data["required_kv"] == pytest.approx(data["required_cv"] * 0.865, rel=1e-6)
    assert data["valve_dn_mm"] in {size["dn_mm"] for size in client.get("/api/meta").json()["vendors"][0]["sizes"]}
    assert "actuator_selection" in data
    assert "mesh" not in data
    assert len(data["visuals"]["curve"]["points"]) == 51
    assert len(data["visuals"]["surface"]["flow_pct"]) == len(data["visuals"]["surface"]["authorities"])
    assert data["visuals"]["surface"]["operating"]["opening_pct"] == pytest.approx(
        min(data["opening_percent"], 100.0)
    )
    assert data["visuals"]["curve"]["operating_point"]["opening_pct"] == pytest.approx(
        min(data["opening_percent"], 100.0), abs=0.2
    )


def test_liquid_pressure_units_are_equivalent() -> None:
    converted = client.post(
        "/api/convert",
        json={
            "kind": "pressure",
            "values": [LIQUID["p1_value"], LIQUID["p2_value"]],
            "from_unit": "bar_a",
            "to_unit": "psi_a",
        },
    )
    assert converted.status_code == 200
    p1_psi, p2_psi = converted.json()["values"]
    payload = dict(LIQUID, pressure_unit="psi_a", p1_value=p1_psi, p2_value=p2_psi)
    response = client.post("/api/size/liquid", json=payload)
    assert response.status_code == 200
    base = client.post("/api/size/liquid", json=LIQUID).json()
    assert response.json()["required_cv"] == pytest.approx(base["required_cv"], rel=1e-6)


def test_gas_sizing_response() -> None:
    response = client.post("/api/size/gas", json=GAS)
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "gas"
    assert data["required_cv"] > 0
    assert data["fluid"]["gas_preset"] == "Doğal Gaz"
    assert data["fluid"]["average_molecular_weight"] > 0
    assert data["fluid"]["phase"] == "gas"


def test_gas_liquid_phase_is_rejected() -> None:
    payload = dict(GAS, gas_preset="Propan", p1_value=20.0, p2_value=15.0)
    response = client.post("/api/size/gas", json=payload)
    assert response.status_code == 400
    assert "faz" in response.json()["detail"].lower()


def test_dense_gas_is_not_mistaken_for_liquid() -> None:
    response = client.post("/api/size/gas", json=dict(GAS, p1_value=200.0, p2_value=150.0))
    assert response.status_code == 200
    assert response.json()["fluid"]["phase"] == "gas"


def test_gas_flow_units_are_equivalent() -> None:
    base = client.post("/api/size/gas", json=GAS).json()["required_cv"]
    for unit in ("sm3h", "scfh", "mmscfd"):
        converted = client.post(
            "/api/convert",
            json={"kind": "gas_flow", "values": [GAS["flow_value"]], "from_unit": "nm3h", "to_unit": unit},
        ).json()["values"][0]
        response = client.post("/api/size/gas", json=dict(GAS, flow_unit=unit, flow_value=converted))
        assert response.status_code == 200, unit
        assert response.json()["required_cv"] == pytest.approx(base, rel=1e-6), unit


def test_gas_manual_properties() -> None:
    payload = dict(
        GAS,
        molecular_weight=28.97,
        specific_heat_ratio=1.4,
        z=1.0,
        viscosity_pa_s=1.8e-5,
    )
    response = client.post("/api/size/gas", json=payload)
    assert response.status_code == 200
    assert response.json()["fluid"]["mode"] == "manual"


def test_steam_sizing_response() -> None:
    response = client.post("/api/size/steam", json=STEAM)
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "steam"
    assert data["required_cv"] > 0
    assert data["fluid"]["flow_kg_h"] == pytest.approx(2500.0)
    assert data["fluid"]["phase"] == "superheated"
    assert data["fluid"]["specific_heat_ratio"] > 1.30


def test_wet_steam_is_rejected() -> None:
    response = client.post("/api/size/steam", json=dict(STEAM, temperature_value=150.0))
    assert response.status_code == 400
    assert "islak" in response.json()["detail"].lower()


def test_liquid_pv_pc_stay_absolute_with_gauge_process_pressure() -> None:
    converted = client.post(
        "/api/convert",
        json={
            "kind": "pressure",
            "values": [LIQUID["p1_value"], LIQUID["p2_value"]],
            "from_unit": "bar_a",
            "to_unit": "bar_g",
        },
    ).json()["values"]
    payload = dict(
        LIQUID,
        pressure_unit="bar_g",
        p1_value=converted[0],
        p2_value=converted[1],
    )
    response = client.post("/api/size/liquid", json=payload)
    assert response.status_code == 200
    base = client.post("/api/size/liquid", json=LIQUID).json()
    assert response.json()["required_cv"] == pytest.approx(base["required_cv"], rel=1e-6)


def test_liquid_properties_endpoint_corrects_water() -> None:
    response = client.post(
        "/api/liquid-properties",
        json={"preset": "Water", "pressure_value": 8.0, "pressure_unit": "bar_a", "temperature_value": 150.0, "temperature_unit": "C"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["temperature_corrected"] is True
    assert data["density_kg_m3"] < 950.0
    assert data["vapor_pressure_bar_a"] > 4.0
    assert data["viscosity_pa_s"] < 0.0005


def test_liquid_properties_endpoint_warns_when_not_liquid() -> None:
    response = client.post(
        "/api/liquid-properties",
        json={"preset": "Propane", "pressure_value": 8.0, "pressure_unit": "bar_a", "temperature_value": 25.0, "temperature_unit": "C"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["temperature_corrected"] is False
    assert "sıvı fazında değil" in data["warning"]


def test_liquid_preset_client_keeps_values_on_invalid_input_or_api_error() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    body = js.split("async function applyLiquidPreset", 1)[1].split("function refreshLiquidPresetIfAuto", 1)[0]
    assert "data = preset" not in body
    assert "Preset güncellenmedi" in body
    assert "Preset özellikleri alınamadı" in body


def test_liquid_properties_endpoint_rejects_unknown_preset() -> None:
    response = client.post(
        "/api/liquid-properties",
        json={"preset": "Unobtainium", "pressure_value": 8.0, "temperature_value": 25.0},
    )
    assert response.status_code == 400


def test_gas_pressure_units_are_equivalent() -> None:
    from units import pressure_from_bar_a

    baseline = client.post("/api/size/gas", json=GAS).json()["required_cv"]
    for unit in ("psi_a", "kPa_a", "MPa_a", "bar_g", "psi_g"):
        payload = dict(
            GAS,
            pressure_unit=unit,
            p1_value=pressure_from_bar_a(8.0, unit),
            p2_value=pressure_from_bar_a(6.0, unit),
        )
        response = client.post("/api/size/gas", json=payload)
        assert response.status_code == 200, unit
        assert response.json()["required_cv"] == pytest.approx(baseline, rel=1e-6)


def test_custom_gas_composition_matches_preset() -> None:
    from config import GAS_PRESETS

    rows = [dict(row) for row in GAS_PRESETS["Doğal Gaz"]["components"]]
    preset_props = client.post(
        "/api/gas-properties",
        json={"gas_preset": "Doğal Gaz", "pressure_value": 8.0, "pressure_unit": "bar_a", "temperature_value": 20.0, "temperature_unit": "C"},
    ).json()
    custom_props = client.post(
        "/api/gas-properties",
        json={
            "gas_preset": "Doğal Gaz",
            "composition": rows,
            "composition_basis": "molar",
            "pressure_value": 8.0,
            "pressure_unit": "bar_a",
            "temperature_value": 20.0,
            "temperature_unit": "C",
        },
    ).json()
    assert custom_props["mode"] == "composition"
    for key in ("average_molecular_weight", "z", "density_kg_m3", "specific_heat_ratio", "viscosity_pa_s"):
        assert custom_props[key] == pytest.approx(preset_props[key], rel=1e-6)

    baseline = client.post("/api/size/gas", json=GAS).json()["required_cv"]
    sized = client.post("/api/size/gas", json=dict(GAS, composition=rows, composition_basis="molar")).json()
    assert sized["required_cv"] == pytest.approx(baseline, rel=1e-6)
    assert sized["fluid"]["mode"] == "composition"
    assert sized["fluid"]["gas_preset"] is None
    assert "Methane" in sized["fluid"]["mixture_string"]


def test_custom_gas_composition_normalizes_and_rejects_invalid_rows() -> None:
    rows = [{"component": "Methane", "fraction_pct": 45.0}, {"component": "Ethane", "fraction_pct": 45.0}]
    normalized = client.post(
        "/api/gas-properties",
        json={"composition": rows, "composition_basis": "molar", "pressure_value": 8.0, "temperature_value": 20.0},
    ).json()
    assert normalized["input_total_percent"] == pytest.approx(90.0)
    assert normalized["normalized"] is True
    assert sum(row["fraction_pct"] for row in normalized["components"]) == pytest.approx(100.0)

    direct_rows = [{"component": "Methane", "fraction_pct": 50.0}, {"component": "Ethane", "fraction_pct": 50.0}]
    direct = client.post(
        "/api/gas-properties",
        json={"composition": direct_rows, "composition_basis": "molar", "pressure_value": 8.0, "temperature_value": 20.0},
    ).json()
    assert normalized["density_kg_m3"] == pytest.approx(direct["density_kg_m3"], rel=1e-9)

    for bad in (
        [{"component": "Unobtainium", "fraction_pct": 100.0}],
        [{"component": "Methane", "fraction_pct": 50.0}, {"component": "Methane", "fraction_pct": 50.0}],
        [{"component": "Methane", "fraction_pct": 0.0}],
        [],
    ):
        response = client.post("/api/size/gas", json=dict(GAS, composition=bad, composition_basis="molar"))
        assert response.status_code == 400
        assert response.json()["detail"]
    manual_and_composition = dict(
        GAS,
        composition=[{"component": "Methane", "fraction_pct": 100.0}],
        molecular_weight=18.0,
        specific_heat_ratio=1.3,
        z=0.9,
        viscosity_pa_s=1.1e-5,
    )
    assert client.post("/api/size/gas", json=manual_and_composition).status_code == 400


def test_convert_gas_actual_flow_accepts_composition() -> None:
    composition = [{"component": "Methane", "fraction_pct": 100.0}]
    preset = client.post(
        "/api/convert",
        json={
            "kind": "gas_flow",
            "values": [100.0],
            "from_unit": "nm3h",
            "to_unit": "m3h",
            "pressure_bar_a": 8.0,
            "temperature_c": 20.0,
            "gas_preset": "Doğal Gaz",
        },
    ).json()["values"][0]
    custom = client.post(
        "/api/convert",
        json={
            "kind": "gas_flow",
            "values": [100.0],
            "from_unit": "nm3h",
            "to_unit": "m3h",
            "pressure_bar_a": 8.0,
            "temperature_c": 20.0,
            "composition": composition,
            "composition_basis": "molar",
        },
    )
    assert custom.status_code == 200
    assert custom.json()["values"][0] != pytest.approx(preset)


def test_webapp_custom_composition_contract() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    elements = (
        "gas-composition-toggle",
        "gas-composition-fields",
        "gas-composition-rows",
        "gas-composition-total",
        "gas-composition-normalize",
        "gas-composition-clear",
    )
    for element in elements:
        assert f'id="{element}"' in html
    assert "function readGasComposition()" in js
    assert "function normalizeGasComposition()" in js
    assert "composition: composition.components" in js
    assert "composition_basis: composition.basis" in js
    assert "canonicalGasComponent" in js
    assert "gas_component_aliases" in js
    assert 'id="gas-model"' in html
    assert 'gas_model: $("gas-model").value' in js


def test_meta_exposes_gas_component_options() -> None:
    meta = client.get("/api/meta").json()
    components = meta["gas_components"]
    assert "Methane" in components
    assert "Chlorine" in components
    assert meta["gas_component_aliases"]["CO2"] == "CarbonDioxide"


def test_gas_model_option_real_and_ideal() -> None:
    real = client.post(
        "/api/gas-properties",
        json={"gas_preset": "Doğal Gaz", "pressure_value": 8.0, "temperature_value": 20.0, "gas_model": "real"},
    ).json()
    ideal = client.post(
        "/api/gas-properties",
        json={"gas_preset": "Doğal Gaz", "pressure_value": 8.0, "temperature_value": 20.0, "gas_model": "ideal"},
    ).json()
    assert real["model_used"] == "heos"
    assert real["z"] != pytest.approx(1.0)
    assert ideal["model_used"] == "ideal"
    assert ideal["z"] == pytest.approx(1.0)
    unsupported = client.post(
        "/api/gas-properties",
        json={"gas_preset": "Klor", "pressure_value": 8.0, "temperature_value": 20.0, "gas_model": "real"},
    )
    assert unsupported.status_code == 400
    assert "Gercek gaz" in unsupported.json()["detail"]


def test_custom_gas_composition_accepts_common_aliases() -> None:
    response = client.post(
        "/api/gas-properties",
        json={
            "composition": [{"component": "CO2", "fraction_pct": 100.0}],
            "composition_basis": "molar",
            "pressure_value": 8.0,
            "temperature_value": 20.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["components"][0]["component"] == "CarbonDioxide"
    assert data["average_molecular_weight"] == pytest.approx(44.01, rel=1e-2)


def test_gas_properties_temperature_and_pressure_units_are_equivalent() -> None:
    from units import pressure_from_bar_a, temperature_from_c

    baseline = client.post(
        "/api/gas-properties",
        json={"gas_preset": "Doğal Gaz", "pressure_value": 8.0, "pressure_unit": "bar_a", "temperature_value": 20.0, "temperature_unit": "C"},
    ).json()
    for pres_unit in ("psi_a", "bar_g", "psi_g", "MPa_a"):
        for temp_unit, temp_value in (("F", temperature_from_c(20.0, "F")), ("K", temperature_from_c(20.0, "K"))):
            data = client.post(
                "/api/gas-properties",
                json={
                    "gas_preset": "Doğal Gaz",
                    "pressure_value": pressure_from_bar_a(8.0, pres_unit),
                    "pressure_unit": pres_unit,
                    "temperature_value": temp_value,
                    "temperature_unit": temp_unit,
                },
            ).json()
            for key in ("average_molecular_weight", "z", "density_kg_m3", "specific_heat_ratio"):
                assert data[key] == pytest.approx(baseline[key], rel=1e-6), (pres_unit, temp_unit, key)


def test_gas_properties_error_contract() -> None:
    base = {"gas_preset": "Doğal Gaz", "pressure_value": 8.0, "pressure_unit": "bar_a", "temperature_value": 20.0, "temperature_unit": "C"}
    for payload in (
        {**base, "gas_preset": "Bilinmeyen"},
        {**base, "pressure_value": 0.0},
        {**base, "temperature_value": -300.0},
        {**base, "pressure_unit": "C"},
    ):
        response = client.post("/api/gas-properties", json=payload)
        assert response.status_code == 400
        assert response.json()["detail"]


def test_gas_actual_and_mass_flow_sizing_equivalence() -> None:
    from units import gas_flow_from_nm3h

    props = client.post(
        "/api/gas-properties",
        json={"gas_preset": "Doğal Gaz", "pressure_value": 8.0, "pressure_unit": "bar_a", "temperature_value": 20.0, "temperature_unit": "C"},
    ).json()
    baseline = client.post("/api/size/gas", json=GAS).json()["required_cv"]
    for unit in ("m3h", "kgh"):
        value = gas_flow_from_nm3h(
            800.0,
            unit,
            pressure_bar_a=8.0,
            temperature_c=20.0,
            z=props["z"],
            density_kg_m3=props["density_kg_m3"],
        )
        data = client.post("/api/size/gas", json=dict(GAS, flow_value=value, flow_unit=unit)).json()
        assert data["required_cv"] == pytest.approx(baseline, rel=1e-6), unit
        assert data["fluid"]["flow_nm3h"] == pytest.approx(800.0, rel=1e-6)


def test_gas_reversed_pressure_rejected() -> None:
    assert client.post("/api/size/gas", json=dict(GAS, p2_value=8.0)).status_code == 400
    assert client.post("/api/size/gas", json=dict(GAS, p2_value=9.0)).status_code == 400
    assert client.post("/api/size/gas", json=dict(GAS, p2_value=7.999)).status_code == 200


def test_gas_size_and_properties_are_consistent() -> None:
    props = client.post(
        "/api/gas-properties",
        json={"gas_preset": "Doğal Gaz", "pressure_value": 8.0, "pressure_unit": "bar_a", "temperature_value": 20.0, "temperature_unit": "C"},
    ).json()
    result = client.post("/api/size/gas", json=GAS).json()
    fluid = result["fluid"]
    assert fluid["z"] == pytest.approx(props["z"], rel=1e-6)
    assert fluid["density_kg_m3"] == pytest.approx(props["density_kg_m3"], rel=1e-6)
    assert fluid["average_molecular_weight"] == pytest.approx(props["average_molecular_weight"], rel=1e-6)
    assert fluid["specific_heat_ratio"] == pytest.approx(props["specific_heat_ratio"], rel=1e-6)
    assert fluid["phase"] not in {"liquid", "supercritical_liquid", "two_phase"}


def test_supercritical_co2_is_accepted() -> None:
    payload = dict(GAS, gas_preset="CO2", p1_value=80.0, p2_value=70.0, temperature_value=40.0)
    response = client.post("/api/size/gas", json=payload)
    assert response.status_code == 200
    assert response.json()["fluid"]["phase"] in {"supercritical", "supercritical_gas"}


def test_gas_properties() -> None:
    response = client.post(
        "/api/gas-properties",
        json={
            "gas_preset": "Doğal Gaz",
            "pressure_value": 8.0,
            "pressure_unit": "bar_a",
            "temperature_value": 20.0,
            "temperature_unit": "C",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["average_molecular_weight"] > 0
    assert data["density_kg_m3"] > 0
    assert data["specific_heat_ratio"] > 1


def test_valve_mesh() -> None:
    response = client.get("/api/valve-mesh?dn=50")
    assert response.status_code == 200
    data = response.json()
    assert data["dn_mm"] == 50
    assert len(data["parts"]) == 8
    assert all(len(part["positions"]) % 3 == 0 for part in data["parts"])
    assert all(len(part["indices"]) % 3 == 0 for part in data["parts"])


@pytest.mark.parametrize("dn", [15, 50, 300, 600])
def test_valve_mesh_geometry_contract(dn: int) -> None:
    data = client.get(f"/api/valve-mesh?dn={dn}").json()
    parts = data["parts"]
    assert {"Mil", "El çarkı"} <= {part["name"] for part in parts}
    for part in parts:
        assert part["positions"]
        assert len(part["positions"]) % 3 == 0
        assert all(math.isfinite(value) for value in part["positions"])
        vertex_count = len(part["positions"]) // 3
        assert part["indices"]
        assert len(part["indices"]) % 3 == 0
        assert all(0 <= index < vertex_count for index in part["indices"])
    stem = next(part for part in parts if part["name"] == "Mil")
    bonnet = next(part for part in parts if part["name"] == "Bonnet")
    assert min(stem["positions"][2::3]) <= max(bonnet["positions"][2::3])


def test_valve_mesh_parts_match_colors_and_extents() -> None:
    from api import PART_COLORS

    parts = client.get("/api/valve-mesh?dn=50").json()["parts"]
    assert {part["name"] for part in parts} == set(PART_COLORS)
    for part in parts:
        assert part["color"] == PART_COLORS[part["name"]]
        xs = part["positions"][0::3]
        ys = part["positions"][1::3]
        zs = part["positions"][2::3]
        assert max(xs) > min(xs) and max(ys) > min(ys) and max(zs) > min(zs)


def test_valve_mesh_scales_with_dn_and_is_deterministic() -> None:
    def span(dn: float) -> float:
        parts = client.get(f"/api/valve-mesh?dn={dn}").json()["parts"]
        xs = [value for part in parts for value in part["positions"][0::3]]
        return max(xs) - min(xs)

    assert span(100) / span(50) == pytest.approx(2.0, rel=1e-9)
    assert span(600) / span(15) == pytest.approx(6.25, rel=1e-9)
    assert client.get("/api/valve-mesh?dn=50").json() == client.get("/api/valve-mesh?dn=50").json()
    assert client.get("/api/valve-mesh?dn=50").json() == client.get("/api/valve-mesh?dn=50.4").json()


def test_valve_mesh_cache_reuses_clamped_dn() -> None:
    from api import _valve_mesh, _valve_mesh_cached

    _valve_mesh_cached.cache_clear()
    first = _valve_mesh(537)
    second = _valve_mesh(537.4)
    info = _valve_mesh_cached.cache_info()
    assert info.misses == 1
    assert info.hits == 1
    assert info.maxsize == 64
    assert first == second


def test_valve_mesh_rounds_and_rejects_out_of_range() -> None:
    assert client.get("/api/valve-mesh?dn=50.4").json()["dn_mm"] == 50
    assert client.get("/api/valve-mesh?dn=50.6").json()["dn_mm"] == 51
    assert client.get("/api/valve-mesh?dn=14").status_code in {400, 422}
    assert client.get("/api/valve-mesh?dn=601").status_code in {400, 422}


def test_webapp_status_and_error_are_live_regions() -> None:
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    assert 'id="api-status" aria-live="polite"' in html
    assert 'id="calc-status" aria-live="polite"' in html
    assert 'id="error" role="alert" aria-live="assertive"' in html


def test_webapp_sets_aria_busy_while_calculating() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    body = js.split("async function calculate", 1)[1].split("function scheduleRecalc", 1)[0]
    assert 'setAttribute("aria-busy", "true")' in body
    assert body.count('setAttribute("aria-busy", "false")') == 2


def test_webapp_gas_properties_and_preset_note_are_linked() -> None:
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    assert 'id="gas-properties" role="status" aria-live="polite"' in html
    assert 'aria-describedby="liquid-preset-note"' in html


def test_webapp_tabs_use_aria_controls_and_keyboard() -> None:
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    assert html.count('role="tab"') == 3
    assert html.count('role="tabpanel"') == 3
    for service in ("liquid", "gas", "steam"):
        assert f'id="tab-{service}"' in html
        assert f'aria-controls="panel-{service}"' in html
        assert f'id="panel-{service}"' in html
        assert f'aria-labelledby="tab-{service}"' in html
    assert 'event.key === "ArrowRight"' in js
    assert 'event.key === "Home"' in js and 'event.key === "End"' in js


def test_webapp_dom_ids_match_js_selectors() -> None:
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    used = set(re.findall(r'\$\("([^"]+)"\)', js))
    assert not (used - set(ids)), sorted(used - set(ids))


def test_webapp_document_accessibility_contract() -> None:
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    assert '<html lang="tr">' in html
    assert html.count("<h1") == 1
    assert 'name="viewport"' in html


def test_webapp_serializes_unit_changes() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    change = js.split("async function onUnitChange", 1)[1].split("function bindUnitSelect", 1)[0]
    calculate = js.split("async function calculate", 1)[1].split("function scheduleRecalc", 1)[0]
    assert "state.unitBusy" in change
    assert "clearTimeout(state.recalcTimer)" in change
    assert "const controls = [...new Set" in change
    assert "select.dataset.previous = next" in change
    assert "state.unitBusy = false" in change
    assert "state.unitBusy" in calculate


def test_webapp_gas_startup_and_manual_guards() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    init = js.split("async function init()", 1)[1].split("init();", 1)[0]
    assert "updateGasProperties();" not in init
    assert "loadValveMesh(50, 0)" not in js
    assert "processContext(service)" in js
    assert "if (!$(id).value)" in js
    assert 'if (service === "gas" && kind !== "flow") updateGasProperties();' in js


def test_webapp_dead_code_and_a11y_fixes() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    css = (Path(__file__).with_name("webapp") / "styles.css").read_text(encoding="utf-8")
    assert "escapeText" not in js
    assert "state.result" not in js
    assert 'aria-describedby="curve-note"' in html
    assert "canvas:focus-visible" in css


def test_webapp_stale_result_and_verdict_contract() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    assert 'id="result-stale"' in html
    assert 'id="result-verdict"' in html
    assert "function markResultsStale(stale)" in js
    assert "if (state.hasCalculated) markResultsStale(true);" in js
    assert "Açıklık kontrol aralığında." in js


def test_webapp_unit_change_toast_contract() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    assert 'id="toast"' in (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    assert "function showToast(message)" in js
    assert "} ${oldLabel} → ${" in js


def test_webapp_scenario_buttons_reset_unit_history() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    assert html.count('class="scenario"') == 3
    assert "function applyScenario(service)" in js
    assert '$(id).dataset.previous = $(id).value;' in js


def test_webapp_invalid_field_marking_contract() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    assert "function markFieldInvalid(input)" in js
    assert 'setAttribute("aria-invalid", "true")' in js
    assert 'querySelector(".input-error")' in js


def test_webapp_error_focus_and_result_live_region() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    assert 'id="error" role="alert" aria-live="assertive" tabindex="-1"' in html
    assert 'id="result-title" aria-live="polite"' in html
    assert "function showError(message, focus = false)" in js
    assert "(invalid || box).focus();" in js
    assert "showError(error.message, !silent)" in js


def test_webapp_canvas_has_touch_action() -> None:
    css = (Path(__file__).with_name("webapp") / "styles.css").read_text(encoding="utf-8")
    assert "touch-action: none" in css


def test_webapp_clears_stale_calculating_status() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    body = js.split("async function calculate", 1)[1].split("function scheduleRecalc", 1)[0]
    assert 'status.textContent === "Hesaplanıyor…"' in body
    assert 'status.textContent = state.hasCalculated ? "Güncel" : ""' in body


def test_webapp_hidden_tab_defers_work() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    assert "visibilityPending: false" in js
    assert "function flushVisibilityWork()" in js
    assert js.count("if (document.hidden)") >= 5


def test_cache_control_headers() -> None:
    assert client.get("/vendor/three.module.min.js").headers["Cache-Control"].startswith("public, max-age=")
    assert client.get("/app.js").headers["Cache-Control"] == "no-cache"
    assert client.get("/api/meta").headers["Cache-Control"] == "public, max-age=3600"


def test_webapp_gas_ui_contract() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    assert "gasRequest: 0" in js
    assert js.count("request !== state.gasRequest") == 2
    assert '["Faz", data.phase' in js
    assert 'aria-controls="gas-manual-fields"' in html


def test_webapp_request_lifecycle_guards() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    fetch = js.split("async function fetchJson", 1)[1].split("function postJson", 1)[0]
    calculate = js.split("async function calculate", 1)[1].split("function scheduleRecalc", 1)[0]
    assert "new AbortController()" in fetch
    assert "15000" in fetch
    assert "clearTimeout(timer)" in fetch
    assert "const revision = state.revision" in calculate
    assert "state.service !== service || state.revision !== revision || state.unitBusy" in calculate


def test_webapp_3d_renders_on_demand() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    assert "function schedule3dFrame()" in js
    assert "function render3dFrame()" in js
    assert "if (state.frameRequest) return" in js
    assert "if (active) schedule3dFrame()" in js
    assert "function markViewerDirty(viewer)" in js
    assert "requestAnimationFrame(animate)" not in js


def test_webapp_3d_stem_travel_uses_calculated_opening() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    visuals = js.split("function renderVisuals", 1)[1].split("async function loadValveMesh", 1)[0]
    mesh = js.split("function renderValveMesh", 1)[1].split("function renderSurface", 1)[0]
    assert "operating?.opening_pct" in visuals
    assert '"Mil"' in mesh and '"El çarkı"' in mesh
    assert "child.position.z = travel" in mesh


def test_webapp_3d_recovers_from_context_loss() -> None:
    js = (Path(__file__).with_name("webapp") / "app.js").read_text(encoding="utf-8")
    assert 'addEventListener("webglcontextlost"' in js
    assert 'addEventListener("webglcontextrestored"' in js
    assert "viewer.contextLost" in js
    assert "viewer.renderer.domElement.parentElement !== viewer.container" in js
    assert 'setAttribute("role", "img")' in js
    assert "3B vana modeli" in js
    assert "Kurulu karakteristik yüzeyi" in js
    assert "viewer.group.rotation.x = -Math.PI / 2" in js
    assert "tabIndex = 0" in js
    assert "ArrowLeft" in js
    assert "cihaz tarafından kapatıldı" in js


def test_invalid_units_and_vendor() -> None:
    response = client.post("/api/size/liquid", json=dict(LIQUID, pressure_unit="furlong"))
    assert response.status_code == 400
    response = client.post("/api/size/liquid", json=dict(LIQUID, vendor="unknown_vendor"))
    assert response.status_code == 400


def test_invalid_numbers_return_400() -> None:
    for key, value in (("p1_value", 0.0), ("density_kg_m3", -1.0), ("temperature_value", -300.0)):
        response = client.post("/api/size/liquid", json=dict(LIQUID, **{key: value}))
        assert response.status_code == 400, key
    for key, value in (("temperature_value", float("nan")), ("critical_pressure_value", float("inf"))):
        body = json.dumps(dict(LIQUID, **{key: value}), allow_nan=True)
        response = client.post("/api/size/liquid", content=body, headers={"Content-Type": "application/json"})
        assert response.status_code == 400, key


def test_convert_gas_flow_with_preset() -> None:
    response = client.post(
        "/api/convert",
        json={
            "kind": "gas_flow",
            "values": [800.0],
            "from_unit": "nm3h",
            "to_unit": "kgh",
            "pressure_bar_a": 8.0,
            "temperature_c": 20.0,
            "gas_preset": "Doğal Gaz",
        },
    )
    assert response.status_code == 200
    assert response.json()["values"][0] > 0
    response = client.post(
        "/api/convert",
        json={
            "kind": "gas_flow",
            "values": [800.0],
            "from_unit": "nm3h",
            "to_unit": "m3h",
            "pressure_bar_a": 8.0,
            "temperature_c": 20.0,
            "gas_preset": "Doğal Gaz",
        },
    )
    assert response.status_code == 200
    assert response.json()["values"][0] > 0
    response = client.post(
        "/api/convert",
        json={
            "kind": "gas_flow",
            "values": [800.0],
            "from_unit": "nm3h",
            "to_unit": "scfh",
        },
    )
    assert response.status_code == 200
    assert response.json()["values"][0] > 0


def test_convert_values_are_bounded() -> None:
    response = client.post(
        "/api/convert",
        json={"kind": "temperature", "values": [25.0] * 1001, "from_unit": "C", "to_unit": "C"},
    )
    assert response.status_code in {400, 422}


def test_api_docs_are_closed_by_default() -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_request_body_size_is_bounded() -> None:
    response = client.post(
        "/api/convert",
        content="{" + " " * 2_000_000 + "}",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_security_headers_present() -> None:
    for path in ("/api/health", "/"):
        response = client.get(path)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
        assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
        assert response.headers["X-Permitted-Cross-Domain-Policies"] == "none"
        csp = response.headers["Content-Security-Policy"]
        assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
        assert "form-action 'self'" in csp and "frame-src 'none'" in csp


def test_static_routes_expose_only_web_assets() -> None:
    assert client.get("/").status_code == 200
    assert client.get("/index.html").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/styles.css").status_code == 200
    assert client.get("/vendor/three.module.min.js").status_code == 200
    assert client.get("/__init__.py").status_code == 404


def test_csp_hash_matches_local_importmap() -> None:
    from api import _CSP_IMPORTMAP_HASH

    html = (Path(__file__).with_name("webapp") / "index.html").read_text(encoding="utf-8")
    block = html.split('<script type="importmap">', 1)[1].split("</script>", 1)[0]
    expected = "sha256-" + base64.b64encode(hashlib.sha256(block.encode("utf-8")).digest()).decode()
    assert expected == _CSP_IMPORTMAP_HASH
    assert "vendor/three.module.min.js" in html
    assert "cdn.jsdelivr.net" not in html
    assert expected in client.get("/api/health").headers["Content-Security-Policy"]
    assert client.get("/vendor/three.module.min.js").status_code == 200


def test_sizing_error_hides_internal_detail() -> None:
    response = client.post("/api/size/gas", json=dict(GAS, p1_value=1e308, p2_value=1e307))
    assert response.status_code == 500
    assert response.json()["detail"] == "Hesaplama hatası."


def test_convert_rejects_non_finite_result() -> None:
    response = client.post(
        "/api/convert",
        json={"kind": "temperature", "values": [1e308], "from_unit": "C", "to_unit": "F"},
    )
    assert response.status_code == 400


def test_size_rejects_reversed_pressure() -> None:
    for p2 in (8.0, 9.0):
        response = client.post("/api/size/liquid", json=dict(LIQUID, p2_value=p2))
        assert response.status_code == 400


def test_manual_gas_properties_require_all_fields() -> None:
    for fields in (
        {"molecular_weight": 18.0},
        {"molecular_weight": 18.0, "specific_heat_ratio": 1.3},
        {"molecular_weight": 18.0, "specific_heat_ratio": 1.3, "z": 0.9},
    ):
        response = client.post("/api/size/gas", json=dict(GAS, **fields))
        assert response.status_code == 400
        assert "birlikte" in response.json()["detail"]
    full = dict(GAS, molecular_weight=18.0, specific_heat_ratio=1.3, z=0.9, viscosity_pa_s=1.1e-5)
    assert client.post("/api/size/gas", json=full).status_code == 200


def test_convert_gas_actual_flow_requires_process_context() -> None:
    body = {"kind": "gas_flow", "values": [100.0], "from_unit": "nm3h", "to_unit": "m3h"}
    assert client.post("/api/convert", json=body).status_code == 400
    valid = {**body, "pressure_bar_a": 8.0, "temperature_c": 20.0, "gas_preset": "Doğal Gaz"}
    assert client.post("/api/convert", json=valid).status_code == 200
    assert client.post("/api/convert", json={**valid, "gas_preset": "Bilinmeyen"}).status_code == 400


def test_liquid_pv_pc_gauge_units_are_absolute_safe() -> None:
    from units import pressure_from_bar_a

    baseline = client.post("/api/size/liquid", json=LIQUID).json()["required_cv"]
    gauge = dict(
        LIQUID,
        pressure_unit="bar_g",
        p1_value=pressure_from_bar_a(8.0, "bar_g"),
        p2_value=pressure_from_bar_a(5.0, "bar_g"),
        vapor_pressure_unit="bar_g",
        vapor_pressure_value=pressure_from_bar_a(0.023, "bar_g"),
        critical_pressure_unit="bar_g",
        critical_pressure_value=pressure_from_bar_a(220.64, "bar_g"),
    )
    data = client.post("/api/size/liquid", json=gauge).json()
    assert data["required_cv"] == pytest.approx(baseline, rel=1e-6)


def test_meta_version_units_and_characteristics_contract() -> None:
    from units import DEFAULT_UNITS, UNIT_MAPS
    from valve_sizing import __version__

    meta = client.get("/api/meta").json()
    assert client.get("/api/health").json()["version"] == meta["version"] == __version__
    for kind, key in DEFAULT_UNITS.items():
        assert key in UNIT_MAPS[kind]
    for kind, units in UNIT_MAPS.items():
        keys = [item["key"] for item in meta["units"][kind]]
        assert keys == list(units)
    for item in meta["characteristics"]:
        response = client.post("/api/size/liquid", json=dict(LIQUID, flow_characteristic=item["key"]))
        assert response.status_code == 200


def test_steam_flow_units_are_equivalent() -> None:
    from units import KGH_TO_LBH, steam_flow_from_kgh

    baseline = client.post("/api/size/steam", json=STEAM).json()["required_cv"]
    for unit, value in (
        ("th", steam_flow_from_kgh(2500.0, "th")),
        ("lbh", 2500.0 * KGH_TO_LBH),
        ("kgs", steam_flow_from_kgh(2500.0, "kgs")),
    ):
        data = client.post("/api/size/steam", json=dict(STEAM, flow_value=value, flow_unit=unit)).json()
        assert data["required_cv"] == pytest.approx(baseline, rel=1e-6)


def test_liquid_mass_flow_unit_is_equivalent() -> None:
    baseline = client.post("/api/size/liquid", json=LIQUID).json()["required_cv"]
    mass_flow = 25.0 * 998.0
    data = client.post("/api/size/liquid", json=dict(LIQUID, flow_value=mass_flow, flow_unit="kgh")).json()
    assert data["required_cv"] == pytest.approx(baseline, rel=1e-6)


def test_gas_temperature_units_are_equivalent() -> None:
    baseline = client.post("/api/size/gas", json=GAS).json()["required_cv"]
    for unit, value in (("F", 68.0), ("K", 293.15)):
        data = client.post("/api/size/gas", json=dict(GAS, temperature_value=value, temperature_unit=unit)).json()
        assert data["required_cv"] == pytest.approx(baseline, rel=1e-6)


def test_api_validation_branches() -> None:
    assert client.post("/api/size/liquid", json=dict(LIQUID, flow_characteristic="bad")).status_code == 400
    assert client.post("/api/size/liquid", json=dict(LIQUID, pipe_inlet_diameter_mm=-1.0)).status_code == 400
    assert client.post(
        "/api/convert",
        json={"kind": "bad", "values": [1.0], "from_unit": "C", "to_unit": "C"},
    ).status_code == 400
    assert client.post(
        "/api/convert",
        json={"kind": "temperature", "values": [], "from_unit": "C", "to_unit": "C"},
    ).status_code == 400


def test_convert_liquid_flow() -> None:
    response = client.post(
        "/api/convert",
        json={
            "kind": "liquid_flow",
            "values": [25.0],
            "from_unit": "m3h",
            "to_unit": "gpm",
            "density_kg_m3": 998.0,
        },
    )
    assert response.status_code == 200
    assert response.json()["values"][0] == pytest.approx(110.0717, rel=1e-3)


def test_api_catalog_matches() -> None:
    response = client.get("/api/catalog-matches", params={"required_cv": 35.0, "design_margin": 15.0})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "vendor_name" in data[0]
    assert "opening_pct" in data[0]
    # Check region filter
    res_asia = client.get("/api/catalog-matches", params={"required_cv": 35.0, "region": "Asia"})
    assert res_asia.status_code == 200
    asia_data = res_asia.json()
    assert all("Asia" in m["region"] for m in asia_data)


def test_api_size_steam_contains_direct_mass() -> None:
    payload = {
        "flow_value": 1500.0,
        "flow_unit": "kgh",
        "p1_value": 10.0,
        "p2_value": 6.0,
        "pressure_unit": "bar_a",
        "temperature_value": 220.0,
        "temperature_unit": "C",
        "vendor": "fisher_globe_eqpct",
    }
    response = client.post("/api/size/steam", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "cv_iec_direct_mass" in data
    assert data["cv_iec_direct_mass"] > 0
    assert "kv_iec_direct_mass" in data

