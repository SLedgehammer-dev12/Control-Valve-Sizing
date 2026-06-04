"""Tests for valve noise prediction module."""

from __future__ import annotations

from valve_noise import predict_noise_gas, predict_noise_liquid


class TestNoiseLiquid:
    def test_water_low_drop(self):
        spl = predict_noise_liquid(
            flow_kg_s=10.0,
            inlet_pressure_pa=5e5,
            outlet_pressure_pa=4.5e5,
            vapor_pressure_pa=2000.0,
            density_kg_m3=998.0,
            speed_of_sound_m_s=1400.0,
            kv=100.0,
            valve_diameter_m=0.1,
            pipe_diameter_m=0.1,
            fl=0.9,
            fd=0.46,
        )
        assert 40.0 < spl < 100.0

    def test_high_drop_louder(self):
        spl_low = predict_noise_liquid(10.0, 5e5, 4.5e5, 2000.0, 998.0, 1400.0, 100.0, 0.1, 0.1, 0.9, 0.46)
        spl_high = predict_noise_liquid(10.0, 5e5, 1e5, 2000.0, 998.0, 1400.0, 100.0, 0.1, 0.1, 0.9, 0.46)
        assert spl_high > spl_low

    def test_no_vapor_pressure(self):
        spl = predict_noise_liquid(5.0, 4e5, 3e5, None, 998.0, None, 80.0, 0.08, 0.1, 0.85, 0.3)
        assert spl > 0.0


class TestNoiseGas:
    def test_air_flow(self):
        spl = predict_noise_gas(
            flow_kg_s=1.0,
            inlet_pressure_pa=5e5,
            outlet_pressure_pa=3e5,
            inlet_temperature_k=300.0,
            density_kg_m3=5.0,
            specific_heat_ratio=1.4,
            molecular_weight=28.96,
            kv=50.0,
            valve_diameter_m=0.1,
            pipe_diameter_m=0.1,
            fd=0.46,
            fl=0.85,
        )
        assert 40.0 < spl < 110.0

    def test_higher_flow_louder(self):
        spl_low = predict_noise_gas(0.5, 5e5, 3e5, 300.0, 5.0, 1.4, 28.96, 50.0, 0.1, 0.1, 0.46, 0.85)
        spl_high = predict_noise_gas(2.0, 5e5, 3e5, 300.0, 5.0, 1.4, 28.96, 50.0, 0.1, 0.1, 0.46, 0.85)
        assert spl_high > spl_low
