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
