"""Tests for flow_2d_model module."""

from flow_2d_model import Flow2DSimulationResult, simulate_flow_2d


def test_simulate_flow_2d_nominal_liquid():
    res = simulate_flow_2d(
        d1_mm=50.0,
        d2_mm=50.0,
        dn_mm=50.0,
        p1_bar=8.0,
        p2_bar=5.0,
        pv_bar=0.023,
        density_kg_m3=998.0,
        flow_rate_m3_h=25.0,
        opening_pct=70.0,
        fl=0.90,
    )
    assert isinstance(res, Flow2DSimulationResult)
    # Check physical velocities
    assert 2.0 < res.summary.inlet_velocity_m_s < 5.0
    assert res.summary.vena_contracta_velocity_m_s > res.summary.inlet_velocity_m_s
    assert res.summary.outlet_velocity_m_s == res.summary.inlet_velocity_m_s
    # Pressures
    assert res.summary.p1_bar == 8.0
    assert res.summary.p2_bar == 5.0
    assert res.summary.p_vc_bar < 5.0
    assert not res.summary.is_cavitating
    assert not res.summary.is_flashing
    # Geometry
    assert len(res.geometry.top_wall) >= 5
    assert len(res.geometry.plug) >= 4
    # Grid
    assert res.grid.nx == 140
    assert res.grid.ny == 50
    assert len(res.grid.u) == 50
    assert len(res.grid.u[0]) == 140
    # Streamline seeds
    assert len(res.streamline_seeds) == 13


def test_simulate_flow_2d_cavitation_detection():
    # Severe pressure drop below vapor pressure
    res = simulate_flow_2d(
        d1_mm=50.0,
        d2_mm=50.0,
        dn_mm=50.0,
        p1_bar=6.0,
        p2_bar=1.2,
        pv_bar=1.0,
        density_kg_m3=998.0,
        flow_rate_m3_h=30.0,
        opening_pct=85.0,
        fl=0.85,
    )
    assert res.summary.is_cavitating is True
    # Verify cavitation cells exist in the grid (cell_type == 3)
    found_cav_cell = any(3 in row for row in res.grid.cell_type)
    assert found_cav_cell is True


def test_simulate_flow_2d_flashing():
    # Outlet pressure below vapor pressure
    res = simulate_flow_2d(
        d1_mm=50.0,
        d2_mm=50.0,
        dn_mm=50.0,
        p1_bar=5.0,
        p2_bar=0.8,
        pv_bar=1.0,
        density_kg_m3=998.0,
        flow_rate_m3_h=25.0,
        opening_pct=60.0,
        fl=0.90,
    )
    assert res.summary.is_flashing is True


def test_simulate_flow_2d_gas_choked_mach():
    # Gas service under choked conditions
    res = simulate_flow_2d(
        d1_mm=80.0,
        d2_mm=80.0,
        dn_mm=80.0,
        p1_bar=10.0,
        p2_bar=2.0,
        pv_bar=0.0,
        density_kg_m3=15.0,
        flow_rate_m3_h=2000.0,
        opening_pct=90.0,
        fl=0.85,
        is_choked=True,
        fluid_type="gas",
        sonic_velocity_m_s=340.0,
    )
    assert res.summary.is_choked is True
    assert res.summary.max_mach >= 0.5


def test_simulate_flow_2d_plug_opening_effect():
    # At 20% opening, throat velocity is higher than at 90% opening for same flow
    res_low = simulate_flow_2d(
        d1_mm=50.0, d2_mm=50.0, dn_mm=50.0,
        p1_bar=8.0, p2_bar=5.0, pv_bar=0.02, density_kg_m3=1000.0,
        flow_rate_m3_h=20.0, opening_pct=20.0, fl=0.90,
    )
    res_high = simulate_flow_2d(
        d1_mm=50.0, d2_mm=50.0, dn_mm=50.0,
        p1_bar=8.0, p2_bar=5.0, pv_bar=0.02, density_kg_m3=1000.0,
        flow_rate_m3_h=20.0, opening_pct=90.0, fl=0.90,
    )
    assert res_low.summary.throat_velocity_m_s > res_high.summary.throat_velocity_m_s


def test_simulate_flow_2d_different_pipe_sizes():
    # D1 = 80mm, D2 = 50mm (contraction)
    res = simulate_flow_2d(
        d1_mm=80.0,
        d2_mm=50.0,
        dn_mm=50.0,
        p1_bar=6.0,
        p2_bar=4.0,
        pv_bar=0.02,
        density_kg_m3=1000.0,
        flow_rate_m3_h=30.0,
        opening_pct=60.0,
    )
    assert res.summary.outlet_velocity_m_s > res.summary.inlet_velocity_m_s


def test_simulate_flow_2d_edge_cases():
    # Handles near-zero or extreme inputs gracefully without ZeroDivisionError
    res = simulate_flow_2d(
        d1_mm=0.0,
        d2_mm=0.0,
        dn_mm=0.0,
        p1_bar=0.0,
        p2_bar=10.0,
        pv_bar=-5.0,
        density_kg_m3=0.0,
        flow_rate_m3_h=0.0,
        opening_pct=0.0,
    )
    assert res.summary.inlet_velocity_m_s >= 0.0
    assert res.summary.p1_bar >= 0.01


def test_simulate_flow_2d_butterfly():
    res = simulate_flow_2d(
        d1_mm=80.0,
        d2_mm=80.0,
        dn_mm=80.0,
        p1_bar=6.0,
        p2_bar=4.5,
        pv_bar=0.02,
        density_kg_m3=1000.0,
        flow_rate_m3_h=50.0,
        opening_pct=65.0,
        valve_type="butterfly",
    )
    assert res.summary.valve_type == "butterfly"
    assert len(res.geometry.plug) == 4
    assert res.summary.vena_contracta_velocity_m_s > res.summary.inlet_velocity_m_s


def test_simulate_flow_2d_ball():
    res = simulate_flow_2d(
        d1_mm=50.0,
        d2_mm=50.0,
        dn_mm=50.0,
        p1_bar=8.0,
        p2_bar=5.0,
        pv_bar=0.02,
        density_kg_m3=1000.0,
        flow_rate_m3_h=25.0,
        opening_pct=45.0,
        valve_type="ball",
    )
    assert res.summary.valve_type == "ball"
    assert len(res.geometry.plug) == 5


def test_simulate_flow_2d_angle_cage():
    res = simulate_flow_2d(
        d1_mm=50.0,
        d2_mm=50.0,
        dn_mm=50.0,
        p1_bar=12.0,
        p2_bar=4.0,
        pv_bar=0.02,
        density_kg_m3=1000.0,
        flow_rate_m3_h=30.0,
        opening_pct=75.0,
        valve_type="angle_cage",
    )
    assert res.summary.valve_type == "angle_cage"
    assert res.summary.is_cavitating is False
