"""Tests for actuator sizing module."""

from __future__ import annotations

import pytest

from actuator_sizing import (
    ACTUATOR_CATALOG,
    estimate_valve_stroke_mm,
    get_actuator_definition,
    get_actuator_options,
    required_thrust_packing,
    required_thrust_shutoff,
    required_thrust_unbalance,
    select_actuator,
    total_required_thrust,
)


class TestActuatorCatalog:
    def test_catalog_nonempty(self):
        assert len(ACTUATOR_CATALOG) > 0

    def test_get_options(self):
        opts = get_actuator_options()
        assert len(opts) > 0
        assert opts == sorted(opts)

    def test_get_definition(self):
        act = get_actuator_definition("DA-100")
        assert act.piston_diameter_mm == 100.0
        assert act.thrust_open_n > 0

    def test_unknown_definition_raises(self):
        with pytest.raises(KeyError):
            get_actuator_definition("not_a_real_actuator")


class TestThrustCalc:
    def test_unbalance_zero_drop(self):
        f = required_thrust_unbalance(100.0, 5.0, 5.0)
        assert f == 0.0

    def test_unbalance_positive(self):
        f = required_thrust_unbalance(100.0, 10.0, 5.0)
        assert f > 0.0

    def test_unbalance_larger_port_higher(self):
        f_small = required_thrust_unbalance(50.0, 10.0, 5.0)
        f_large = required_thrust_unbalance(100.0, 10.0, 5.0)
        assert f_large > f_small

    def test_shutoff_positive(self):
        f = required_thrust_shutoff(100.0, 10.0)
        assert f > 0.0

    def test_shutoff_zero_pressure(self):
        f = required_thrust_shutoff(100.0, 0.0)
        assert f == 0.0

    def test_packing_positive(self):
        f = required_thrust_packing(12.0)
        assert f > 0.0

    def test_total_required(self):
        result = total_required_thrust(100.0, 10.0, 5.0, shutoff_pressure_bar=16.0)
        for key in ("unbalance_n", "shutoff_n", "packing_n", "total_n"):
            assert key in result
        assert result["total_n"] > result["unbalance_n"]


class TestActuatorSelection:
    def test_select_smallest(self):
        result = select_actuator(2000.0, 25.0)
        assert result["selected"] is True
        assert result["thrust_margin_pct"] > 0.0

    def test_select_too_large(self):
        result = select_actuator(50000.0, 200.0)
        assert result["selected"] is False

    def test_select_specific(self):
        result = select_actuator(5000.0, 35.0, actuator_key="DA-200")
        assert result["model"] == "DA-200"

    def test_select_specific_too_small_returns_best_effort(self):
        result = select_actuator(500000.0, 200.0, actuator_key="DA-100")
        assert result["selected"] is False
        assert result["model"] == "DA-100"
        assert result["thrust_margin_pct"] < 0.0


class TestValveStrokeEstimation:
    def test_small_valves(self):
        assert estimate_valve_stroke_mm(15) == 19.0
        assert estimate_valve_stroke_mm(25) == 19.0

    def test_medium_valves(self):
        assert estimate_valve_stroke_mm(50) == 29.0
        assert estimate_valve_stroke_mm(80) == 38.0
        assert estimate_valve_stroke_mm(100) == 38.0

    def test_large_valves(self):
        assert estimate_valve_stroke_mm(150) == 51.0
        assert estimate_valve_stroke_mm(200) == 51.0
        assert estimate_valve_stroke_mm(300) == 76.0


class TestActuatorDynamics:
    def test_dynamics_standard(self):
        from actuator_sizing import analyze_actuator_dynamics

        res = analyze_actuator_dynamics("DA-150", supply_pressure_bar_g=4.0, positioner_flow_capacity_nm3h=14.0)
        assert res.model == "DA-150"
        assert res.chamber_volume_liters > 0.5
        assert res.stroke_time_open_sec > 0.0
        assert res.stroke_time_close_sec > 0.0
        assert res.total_air_consumption_nm3h > res.quiescent_air_consumption_nm3h
        assert "NPT" in res.supply_line_recommendation

    def test_dynamics_booster_recommendation(self):
        from actuator_sizing import analyze_actuator_dynamics

        # Request very fast stroke (0.2s) on a large actuator (DA-350)
        res = analyze_actuator_dynamics(
            "DA-350",
            supply_pressure_bar_g=5.0,
            positioner_flow_capacity_nm3h=12.0,
            target_stroke_time_sec=0.2,
        )
        assert res.booster_recommended is True
        assert res.is_stroking_time_acceptable is False
        assert len(res.warnings) > 0
        assert any("Booster" in w for w in res.warnings)

    def test_dynamics_to_dict(self):
        from actuator_sizing import analyze_actuator_dynamics

        res = analyze_actuator_dynamics("DA-200", target_stroke_time_sec=3.0)
        d = res.to_dict()
        assert d["model"] == "DA-200"
        assert "chamber_volume_liters" in d
        assert "stroke_time_open_sec" in d
        assert "total_air_consumption_nm3h" in d
        assert isinstance(d["warnings"], list)
        assert isinstance(d["engineering_notes"], list)

    def test_dynamics_supply_line_sizing(self):
        from actuator_sizing import analyze_actuator_dynamics

        small = analyze_actuator_dynamics("DA-100")
        assert "1/4\"" in small.supply_line_recommendation

        large = analyze_actuator_dynamics("DA-350")
        assert "3/8\"" in large.supply_line_recommendation

        heavy = analyze_actuator_dynamics("DA-350", positioner_flow_capacity_nm3h=30.0)
        assert "1/2\"" in heavy.supply_line_recommendation

