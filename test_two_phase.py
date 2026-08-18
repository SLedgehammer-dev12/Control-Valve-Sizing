"""Tests for two-phase flow module."""

from __future__ import annotations

from two_phase import (
    cavitation_index,
    cavitation_severity,
    flash_fraction,
    flashing_check,
    two_phase_density_homogeneous,
    two_phase_viscosity_homogeneous,
)


class TestFlashingCheck:
    def test_flashing_true(self):
        assert flashing_check(10.0, 3.0, 5.0) is True

    def test_flashing_false(self):
        assert flashing_check(10.0, 6.0, 5.0) is False

    def test_at_boundary(self):
        assert flashing_check(10.0, 5.0, 5.0) is False


class TestCavitationIndex:
    def test_no_cavitation(self):
        sigma = cavitation_index(10.0, 8.0, 2.0)
        assert sigma > 1.0

    def test_incipient(self):
        sigma = cavitation_index(10.0, 3.0, 5.0)
        assert 0.7 <= sigma < 1.0

    def test_zero_delta_p(self):
        sigma = cavitation_index(10.0, 10.0, 2.0)
        assert sigma == float("inf")

    def test_vapor_pressure_at_or_above_inlet(self):
        from two_phase import xfz_cavitation_factor

        assert xfz_cavitation_factor(10.0, 8.0, 10.0) == 0.0
        assert xfz_cavitation_factor(10.0, 8.0, 12.0) == 0.0

    def test_severity_classification(self):
        assert cavitation_severity(1.5) == "Kavitasyon yok"
        assert cavitation_severity(0.8) == "Hafif kavitasyon"
        assert cavitation_severity(0.6) == "Orta kavitasyon"
        assert cavitation_severity(0.4) == "Siddetli kavitasyon"
        assert cavitation_severity(0.2) == "Flashing / tam kavitasyon"


class TestTwoPhaseDensity:
    def test_liquid_only(self):
        rho = two_phase_density_homogeneous(0.0, 1000.0, 1.0)
        assert rho == 1000.0

    def test_gas_only(self):
        rho = two_phase_density_homogeneous(1.0, 1000.0, 1.0)
        assert rho == 1.0

    def test_mixed(self):
        rho = two_phase_density_homogeneous(0.5, 1000.0, 1.0)
        assert 1.0 < rho < 1000.0

    def test_quality_5pct(self):
        rho = two_phase_density_homogeneous(0.05, 1000.0, 1.2)
        assert 20.0 < rho < 30.0


class TestTwoPhaseViscosity:
    def test_liquid_only(self):
        mu = two_phase_viscosity_homogeneous(0.0, 1e-3, 1e-5)
        assert mu == 1e-3

    def test_gas_only(self):
        mu = two_phase_viscosity_homogeneous(1.0, 1e-3, 1e-5)
        assert mu == 1e-5

    def test_mixed(self):
        mu = two_phase_viscosity_homogeneous(0.5, 1e-3, 1e-5)
        assert 1e-5 < mu < 1e-3


class TestFlashFraction:
    def test_no_flash_equal_pressure(self):
        x = flash_fraction(10.0, 10.0, 100.0, 4200.0, 2.2e6)
        assert x == 0.0

    def test_flash_positive(self):
        x = flash_fraction(10.0, 2.0, 180.0, 4200.0, 2.0e6)
        assert 0.0 <= x <= 1.0

    def test_non_positive_latent_heat(self):
        assert flash_fraction(10.0, 2.0, 180.0, 4200.0, 0.0) == 0.0
        assert flash_fraction(10.0, 2.0, 180.0, 4200.0, -1000.0) == 0.0


class TestVaporDensityIdealGas:
    def test_water_vapor_at_5bar(self):
        from two_phase import vapor_density_ideal_gas

        rho = vapor_density_ideal_gas(5.0, 100.0, 18.015)
        assert 2.0 < rho < 4.0

    def test_zero_temperature_guard(self):
        from two_phase import vapor_density_ideal_gas

        assert vapor_density_ideal_gas(5.0, -273.15, 18.015) == 0.0


class TestFlashingCvEstimate:
    def test_no_flash_returns_liquid_cv(self):
        from two_phase import flashing_cv_estimate

        cv = flashing_cv_estimate(20.0, 0.0, 1000.0, 1.0)
        assert abs(cv - 20.0) < 1e-9

    def test_flash_increases_cv(self):
        from two_phase import flashing_cv_estimate

        cv_tp = flashing_cv_estimate(20.0, 0.1, 1000.0, 1.2)
        assert cv_tp > 20.0

    def test_non_positive_cv_returns_zero(self):
        from two_phase import flashing_cv_estimate

        assert flashing_cv_estimate(0.0, 0.5, 1000.0, 1.0) == 0.0

    def test_degenerate_two_phase_density_returns_liquid_cv(self):
        from two_phase import flashing_cv_estimate

        cv = flashing_cv_estimate(20.0, 0.5, 1000.0, -1.0)
        assert cv == 20.0
