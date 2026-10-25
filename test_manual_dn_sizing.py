"""Tests for manual valve diameter (DN) override and rating evaluation."""

from fastapi.testclient import TestClient

from api import app
from valve_sizing import (
    GasSizingInput,
    LiquidSizingInput,
    SteamSizingInput,
    size_gas_valve,
    size_liquid_valve,
    size_steam_valve,
)

client = TestClient(app)


def test_manual_dn_liquid_exact_selection():
    data = LiquidSizingInput(
        flow_m3h=25.0,
        inlet_pressure_bar_a=8.0,
        outlet_pressure_bar_a=5.0,
        density_kg_m3=998.0,
        vapor_pressure_bar_a=0.023,
        critical_pressure_bar_a=220.64,
        viscosity_pa_s=0.00089,
        fl=0.9,
    )
    # Force DN80 even though DN25 or DN50 would be optimal
    res = size_liquid_valve(data, target_dn_mm=80.0)
    assert res.valve_dn_mm == 80
    assert res.rated_cv > res.required_cv


def test_manual_dn_liquid_oversized_warning():
    data = LiquidSizingInput(
        flow_m3h=3.0,
        inlet_pressure_bar_a=8.0,
        outlet_pressure_bar_a=5.0,
        density_kg_m3=998.0,
        vapor_pressure_bar_a=0.023,
        critical_pressure_bar_a=220.64,
        viscosity_pa_s=0.00089,
        fl=0.9,
    )
    # Manually select huge DN150 for tiny flow
    res = size_liquid_valve(data, target_dn_mm=150.0)
    assert res.valve_dn_mm == 150
    assert res.opening_percent < 20.0
    # Must have oversized warning
    assert "asiri buyuk" in str(res.warning) or "avlanma" in str(res.warning)


def test_manual_dn_liquid_undersized_warning():
    data = LiquidSizingInput(
        flow_m3h=80.0,
        inlet_pressure_bar_a=8.0,
        outlet_pressure_bar_a=5.0,
        density_kg_m3=998.0,
        vapor_pressure_bar_a=0.023,
        critical_pressure_bar_a=220.64,
        viscosity_pa_s=0.00089,
        fl=0.9,
    )
    # Select small DN15 for huge 80 m3/h flow
    res = size_liquid_valve(data, target_dn_mm=15.0)
    assert res.valve_dn_mm == 15
    assert "kapasitesi yetersiz" in str(res.warning)


def test_manual_dn_gas_selection():
    data = GasSizingInput(
        flow_nm3h=500.0,
        inlet_pressure_bar_a=10.0,
        outlet_pressure_bar_a=6.0,
        temperature_c=25.0,
        molecular_weight=28.97,
        specific_heat_ratio=1.4,
        viscosity_pa_s=1.8e-5,
    )
    res = size_gas_valve(data, target_dn_mm=50.0)
    assert res.valve_dn_mm == 50


def test_manual_dn_steam_selection():
    data = SteamSizingInput(
        flow_kg_h=1500.0,
        inlet_pressure_bar_a=12.0,
        outlet_pressure_bar_a=6.0,
        temperature_c=220.0,
        specific_heat_ratio=1.3,
    )
    res = size_steam_valve(data, target_dn_mm=40.0)
    assert res.valve_dn_mm == 40


def test_manual_dn_api_endpoint():
    resp = client.post(
        "/api/size/liquid",
        json={
            "flow_value": 25.0,
            "flow_unit": "m3h",
            "pressure_unit": "bar_a",
            "p1_value": 8.0,
            "p2_value": 5.0,
            "density_kg_m3": 998.0,
            "vapor_pressure_value": 0.023,
            "vapor_pressure_unit": "bar_a",
            "critical_pressure_value": 220.64,
            "critical_pressure_unit": "bar_a",
            "viscosity_pa_s": 0.00089,
            "target_dn_mm": 80.0,
        },
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["valve_dn_mm"] == 80


def test_large_valve_sizes_in_default_series():
    from valve_sizing import DEFAULT_VALVE_SERIES

    max_valve = DEFAULT_VALVE_SERIES[-1]
    assert max_valve.dn_mm == 1000
    assert max_valve.inch == '40"'
    assert max_valve.cv_rated == 15500.0


def test_large_valve_sizes_in_vendor_catalog():
    import vendor_catalog

    for key in ("fisher_globe_eqpct", "fisher_vnotch_90", "fisher_bfly_90"):
        v = vendor_catalog.get_vendor_definition(key)
        dns = [s.dn_mm for s in v.sizes]
        assert 1000 in dns
        assert v.sizes[-1].dn_mm == 1000


def test_large_valve_sizing_auto_recommends_large_dn():
    # Enormous liquid flow (15,000 m3/h) requires DN > 200 (8")
    data = LiquidSizingInput(
        flow_m3h=15000.0,
        inlet_pressure_bar_a=8.0,
        outlet_pressure_bar_a=6.0,
        density_kg_m3=998.0,
        vapor_pressure_bar_a=0.023,
        critical_pressure_bar_a=220.64,
        viscosity_pa_s=0.00089,
        fl=0.9,
    )
    res = size_liquid_valve(data)
    assert res.valve_dn_mm >= 500  # Automatically chooses large DN >= 20"
    assert res.opening_percent <= 100.0


def test_flow_2d_simulation_large_scale_aspect_ratio():
    from flow_2d_model import simulate_flow_2d

    res = simulate_flow_2d(
        d1_mm=1000.0,
        d2_mm=1000.0,
        dn_mm=600.0,
        p1_bar=10.0,
        p2_bar=6.0,
        pv_bar=0.023,
        density_kg_m3=998.0,
        flow_rate_m3_h=20000.0,
        opening_pct=70.0,
        valve_type="butterfly",
    )
    # Check physical coordinates and scaling
    g = res.geometry
    assert g.d1_mm == 1000.0
    assert g.dn_mm == 600.0
    assert g.d2_mm == 1000.0
    assert g.x_inlet_mm < -1000.0
    assert g.x_outlet_mm > 1200.0
    # Reducer should transition from r=500 down to r=300
    radii = [pt[1] for pt in g.top_wall]
    assert radii[0] == 500.0
    assert 300.0 in radii
    assert radii[-1] == 500.0

