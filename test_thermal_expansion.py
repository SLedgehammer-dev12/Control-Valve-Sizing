"""Tests for pipe thermal expansion module."""

from __future__ import annotations

import pytest

from thermal_expansion import MATERIAL_ALPHA, expansion_loop_length, pipe_linear_expansion, pipe_thermal_stress


class TestMaterialData:
    def test_materials_nonempty(self):
        assert len(MATERIAL_ALPHA) > 0

    def test_carbon_steel_alpha(self):
        assert MATERIAL_ALPHA["carbon_steel"] == 12.0

    def test_stainless_higher_than_cs(self):
        assert MATERIAL_ALPHA["stainless_304"] > MATERIAL_ALPHA["carbon_steel"]


class TestLinearExpansion:
    def test_zero_delta_t(self):
        dl = pipe_linear_expansion(10.0, 0.0, "carbon_steel")
        assert dl == 0.0

    def test_positive_expansion(self):
        dl = pipe_linear_expansion(10.0, 100.0, "carbon_steel")
        assert dl == 12.0

    def test_longer_pipe_more_expansion(self):
        dl_short = pipe_linear_expansion(10.0, 100.0, "carbon_steel")
        dl_long = pipe_linear_expansion(20.0, 100.0, "carbon_steel")
        assert dl_long == 2 * dl_short

    def test_unknown_material_raises(self):
        with pytest.raises(KeyError):
            pipe_linear_expansion(10.0, 100.0, "unknown_material")


class TestThermalStress:
    def test_zero_delta_t(self):
        sigma = pipe_thermal_stress(0.0, "carbon_steel")
        assert sigma == 0.0

    def test_positive_stress(self):
        sigma = pipe_thermal_stress(100.0, "carbon_steel")
        assert sigma > 200.0
        assert sigma < 250.0

    def test_unknown_material_raises(self):
        with pytest.raises(KeyError):
            pipe_thermal_stress(100.0, "unknown")


class TestExpansionLoop:
    def test_loop_length_positive(self):
        loop_m = expansion_loop_length(20.0, 100.0, "carbon_steel")
        assert loop_m > 0.0

    def test_unknown_material_raises(self):
        with pytest.raises(KeyError, match="Bilinmeyen malzeme"):
            expansion_loop_length(20.0, 100.0, "unknown")

    def test_non_positive_allowable_stress_returns_zero(self):
        assert expansion_loop_length(20.0, 100.0, "carbon_steel", allowable_stress_mpa=0.0) == 0.0
