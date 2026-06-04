"""Tests for unit conversion constants and helpers in units.py."""

from __future__ import annotations

import pytest

from units import (
    AIR_K,
    AIR_MW,
    BAR_TO_PSI,
    CELSIUS_TO_RANKINE,
    CV_TO_KV,
    FF_A,
    FF_B,
    KGH_TO_LBH,
    KV_TO_CV,
    M3H_TO_GPM,
    NM3H_TO_SCFH,
    NORMAL_P_BAR,
    NORMAL_T_K,
    Q_,
    bar_to_pa,
    celsius_to_k,
    k_to_celsius,
    mm_to_m,
    nm3h_to_actual_m3h,
    pa_to_bar,
    ureg,
)

_TOL = 1e-6


class TestConstants:
    def test_bar_to_psi(self):
        assert abs(BAR_TO_PSI - 14.5037738) < _TOL

    def test_m3h_to_gpm(self):
        assert abs(M3H_TO_GPM - 4.4028675) < _TOL

    def test_nm3h_to_scfh(self):
        assert abs(NM3H_TO_SCFH - 35.3146667) < _TOL

    def test_kgh_to_lbh(self):
        assert abs(KGH_TO_LBH - 2.20462262) < _TOL

    def test_cv_to_kv(self):
        assert abs(CV_TO_KV - 0.865) < _TOL

    def test_kv_to_cv(self):
        assert abs(KV_TO_CV - 1.0 / 0.865) < _TOL

    def test_cv_kv_roundtrip(self):
        cv = 100.0
        assert abs(cv * CV_TO_KV * KV_TO_CV - cv) < _TOL

    def test_air_mw(self):
        assert abs(AIR_MW - 28.97) < _TOL

    def test_air_k(self):
        assert abs(AIR_K - 1.4) < _TOL

    def test_ff_a(self):
        assert abs(FF_A - 0.96) < _TOL

    def test_ff_b(self):
        assert abs(FF_B - 0.28) < _TOL

    def test_celsius_to_rankine(self):
        assert abs(CELSIUS_TO_RANKINE - 9.0 / 5.0) < _TOL

    def test_normal_p_bar(self):
        assert abs(NORMAL_P_BAR - 1.01325) < _TOL

    def test_normal_t_k(self):
        assert abs(NORMAL_T_K - 273.15) < _TOL

    def test_zero_celsius_to_rankine(self):
        assert abs(0.0 * CELSIUS_TO_RANKINE - 0.0) < _TOL


class TestBarToPa:
    def test_bar_to_pa(self):
        assert abs(bar_to_pa(1.0) - 1e5) < _TOL

    def test_pa_to_bar(self):
        assert abs(pa_to_bar(1e5) - 1.0) < _TOL

    def test_roundtrip(self):
        bar = 12.5
        assert abs(pa_to_bar(bar_to_pa(bar)) - bar) < _TOL

    def test_zero(self):
        assert bar_to_pa(0.0) == 0.0


class TestMmToM:
    def test_mm_to_m(self):
        assert abs(mm_to_m(1000.0) - 1.0) < _TOL

    def test_dn50(self):
        assert abs(mm_to_m(50.0) - 0.05) < _TOL

    def test_zero(self):
        assert mm_to_m(0.0) == 0.0


class TestTemperature:
    def test_celsius_to_k(self):
        assert abs(celsius_to_k(0.0) - 273.15) < _TOL

    def test_k_to_celsius(self):
        assert abs(k_to_celsius(273.15) - 0.0) < _TOL

    def test_roundtrip(self):
        c = 100.0
        assert abs(k_to_celsius(celsius_to_k(c)) - c) < _TOL

    def test_absolute_zero(self):
        assert abs(k_to_celsius(0.0) + 273.15) < _TOL


class TestNm3hToActual:
    def test_standard_conditions(self):
        result = nm3h_to_actual_m3h(100.0, NORMAL_P_BAR, NORMAL_T_K, 1.0)
        assert abs(result - 100.0) < _TOL

    def test_double_pressure(self):
        result = nm3h_to_actual_m3h(100.0, NORMAL_P_BAR * 2, NORMAL_T_K, 1.0)
        assert abs(result - 50.0) < _TOL

    def test_double_temp(self):
        result = nm3h_to_actual_m3h(100.0, NORMAL_P_BAR, NORMAL_T_K * 2, 1.0)
        assert abs(result - 200.0) < _TOL

    def test_z_factor(self):
        result = nm3h_to_actual_m3h(100.0, NORMAL_P_BAR, NORMAL_T_K, 0.5)
        assert abs(result - 50.0) < _TOL


class TestPintRegistry:
    def test_basic_quantity(self):
        q = 10.0 * ureg.meter
        assert abs(q.to(ureg.centimeter).magnitude - 1000.0) < _TOL

    def test_bar_to_pa_pint(self):
        q = 1.0 * ureg.bar
        assert abs(q.to(ureg.pascal).magnitude - 1e5) < _TOL * 1e5

    def test_celsius_to_kelvin(self):
        q = Q_(0.0, ureg.degC)
        result = q.to(ureg.kelvin)
        assert abs(result.magnitude - 273.15) < _TOL

    def test_compatible_dimensions(self):
        with pytest.raises((Exception,)):
            (1.0 * ureg.meter).to(ureg.kilogram)

    def test_nm3h_concept(self):
        m3h = ureg.meter**3 / ureg.hour
        q = 100.0 * m3h
        assert abs(q.to(ureg.liter / ureg.hour).magnitude - 100000.0) < _TOL

    def test_psi_conversion(self):
        q = 14.5037738 * ureg.psi
        assert abs(q.to(ureg.bar).magnitude - 1.0) < _TOL * 10

    def test_gpm_conversion(self):
        q = 1.0 * ureg.gallon / ureg.minute
        m3h = ureg.meter**3 / ureg.hour
        converted = q.to(m3h).magnitude
        assert abs(converted - 0.2271247) < 1e-4

    def test_lb_per_h_conversion(self):
        q = 1.0 * ureg.pound / ureg.hour
        converted = q.to(ureg.kilogram / ureg.hour).magnitude
        assert abs(converted - 0.453592) < 1e-4

    def test_rankine_concept(self):
        q = 491.67 * ureg.degR
        kelvin = q.to(ureg.kelvin).magnitude
        assert abs(kelvin - 273.15) < 0.1
