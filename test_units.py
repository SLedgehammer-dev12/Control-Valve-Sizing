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
    gas_flow_from_nm3h,
    gas_flow_to_nm3h,
    k_to_celsius,
    liquid_flow_from_m3h,
    liquid_flow_to_m3h,
    mm_to_m,
    nm3h_to_actual_m3h,
    pa_to_bar,
    pressure_from_bar_a,
    pressure_to_bar_a,
    steam_flow_from_kgh,
    steam_flow_to_kgh,
    temperature_from_c,
    temperature_to_c,
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


class TestTemperatureConverters:
    def test_c_to_c(self):
        assert temperature_to_c(25.0, "C") == 25.0

    def test_f_to_c(self):
        assert abs(temperature_to_c(212.0, "F") - 100.0) < _TOL

    def test_k_to_c(self):
        assert abs(temperature_to_c(298.15, "K") - 25.0) < _TOL

    def test_c_to_f(self):
        assert abs(temperature_from_c(100.0, "F") - 212.0) < _TOL

    def test_c_to_k(self):
        assert abs(temperature_from_c(0.0, "K") - 273.15) < _TOL

    def test_roundtrip(self):
        for unit in ("C", "F", "K"):
            for value in (0.0, 25.0, 120.0, -40.0):
                assert abs(temperature_to_c(temperature_from_c(value, unit), unit) - value) < _TOL

    def test_unknown_unit(self):
        with pytest.raises(ValueError, match="Bilinmeyen sicaklik birimi"):
            temperature_to_c(1.0, "R")


class TestPressureConverters:
    def test_bar_a(self):
        assert pressure_to_bar_a(8.0, "bar_a") == 8.0

    def test_bar_g_to_abs(self):
        assert abs(pressure_to_bar_a(0.0, "bar_g") - 1.01325) < _TOL

    def test_psi_a_to_bar(self):
        assert abs(pressure_to_bar_a(14.5037738, "psi_a") - 1.0) < _TOL

    def test_psi_g_to_abs(self):
        assert abs(pressure_to_bar_a(0.0, "psi_g") - 1.01325) < _TOL

    def test_kpa_a_to_bar(self):
        assert abs(pressure_to_bar_a(1000.0, "kPa_a") - 10.0) < _TOL

    def test_mpa_a_to_bar(self):
        assert abs(pressure_to_bar_a(1.0, "MPa_a") - 10.0) < _TOL

    def test_atm_to_bar(self):
        assert abs(pressure_to_bar_a(1.0, "atm_a") - 1.01325) < _TOL

    def test_bar_to_psi(self):
        assert abs(pressure_from_bar_a(1.0, "psi_a") - 14.5037738) < _TOL

    def test_roundtrip(self):
        for unit in ("bar_a", "bar_g", "psi_a", "psi_g", "kPa_a", "MPa_a", "atm_a"):
            for value in (1.0, 8.0, 50.0):
                assert abs(pressure_to_bar_a(pressure_from_bar_a(value, unit), unit) - value) < _TOL

    def test_unknown_unit(self):
        with pytest.raises(ValueError, match="Bilinmeyen basinc birimi"):
            pressure_to_bar_a(1.0, "ksi")


class TestLiquidFlowConverters:
    def test_m3h(self):
        assert liquid_flow_to_m3h(25.0, "m3h") == 25.0

    def test_gpm_to_m3h(self):
        assert abs(liquid_flow_to_m3h(110.0, "gpm") - 110.0 / M3H_TO_GPM) < _TOL

    def test_lpm_to_m3h(self):
        assert abs(liquid_flow_to_m3h(1000.0, "lpm") - 60.0) < _TOL

    def test_m3d_to_m3h(self):
        assert abs(liquid_flow_to_m3h(2400.0, "m3d") - 100.0) < _TOL

    def test_bbl_d_to_m3h(self):
        assert abs(liquid_flow_to_m3h(1000.0, "bbl_d") - 1000.0 * 0.158987 / 24.0) < _TOL

    def test_kgh_to_m3h(self):
        assert abs(liquid_flow_to_m3h(9980.0, "kgh", density_kg_m3=998.0) - 10.0) < _TOL

    def test_roundtrip(self):
        for unit in ("m3h", "gpm", "lpm", "m3d", "bbl_d"):
            for value in (1.0, 25.0, 500.0):
                assert abs(liquid_flow_to_m3h(liquid_flow_from_m3h(value, unit), unit) - value) < _TOL

    def test_kgh_requires_density(self):
        with pytest.raises(ValueError, match="yogunlugu gereklidir"):
            liquid_flow_to_m3h(10.0, "kgh")

    def test_unknown_unit(self):
        with pytest.raises(ValueError, match="Bilinmeyen sivi debi birimi"):
            liquid_flow_to_m3h(1.0, "cfh")


class TestSteamFlowConverters:
    def test_kgh(self):
        assert steam_flow_to_kgh(2500.0, "kgh") == 2500.0

    def test_th_to_kgh(self):
        assert steam_flow_to_kgh(2.5, "th") == 2500.0

    def test_lbh_to_kgh(self):
        assert abs(steam_flow_to_kgh(2204.6, "lbh") - 1000.0) < 0.5

    def test_kgs_to_kgh(self):
        assert steam_flow_to_kgh(1.0, "kgs") == 3600.0

    def test_roundtrip(self):
        for unit in ("kgh", "th", "lbh", "kgs"):
            for value in (100.0, 2500.0):
                assert abs(steam_flow_to_kgh(steam_flow_from_kgh(value, unit), unit) - value) < _TOL

    def test_unknown_unit(self):
        with pytest.raises(ValueError, match="Bilinmeyen buhar debi birimi"):
            steam_flow_to_kgh(1.0, "scfh")


class TestGasFlowConverters:
    def test_nm3h(self):
        assert gas_flow_to_nm3h(800.0, "nm3h") == 800.0

    def test_sm3h_to_nm3h(self):
        assert abs(gas_flow_to_nm3h(1000.0, "sm3h") - 1000.0 * NORMAL_T_K / 288.15) < _TOL

    def test_scfh_to_nm3h(self):
        assert abs(gas_flow_to_nm3h(35314.6667, "scfh") - 1000.0) < 0.01

    def test_mmscfd_to_nm3h(self):
        assert abs(gas_flow_to_nm3h(1.0, "mmscfd") - 1e6 / 24.0 / NM3H_TO_SCFH) < _TOL

    def test_actual_m3h_to_nm3h(self):
        result = gas_flow_to_nm3h(100.0, "m3h", pressure_bar_a=8.0, temperature_c=20.0, z=0.98)
        assert abs(result - 100.0 * (8.0 / NORMAL_P_BAR) * (NORMAL_T_K / 293.15) / 0.98) < _TOL

    def test_kgh_to_nm3h(self):
        density = 7.0
        result = gas_flow_to_nm3h(700.0, "kgh", pressure_bar_a=8.0, temperature_c=20.0, z=1.0, density_kg_m3=density)
        expected = 100.0 * (8.0 / NORMAL_P_BAR) * (NORMAL_T_K / 293.15)
        assert abs(result - expected) < _TOL

    def test_roundtrip(self):
        for unit in ("nm3h", "sm3h", "scfh", "mmscfd"):
            for value in (100.0, 800.0):
                assert abs(gas_flow_to_nm3h(gas_flow_from_nm3h(value, unit), unit) - value) < 1e-3

    def test_roundtrip_m3h_and_kgh(self):
        for value in (50.0, 200.0):
            converted = gas_flow_from_nm3h(value, "m3h", pressure_bar_a=8.0, temperature_c=20.0, z=0.92)
            recovered = gas_flow_to_nm3h(converted, "m3h", pressure_bar_a=8.0, temperature_c=20.0, z=0.92)
            assert abs(recovered - value) < 1e-3

        for value in (100.0, 500.0):
            converted = gas_flow_from_nm3h(value, "kgh", pressure_bar_a=8.0, temperature_c=20.0, z=0.92, density_kg_m3=6.5)
            recovered = gas_flow_to_nm3h(converted, "kgh", pressure_bar_a=8.0, temperature_c=20.0, z=0.92, density_kg_m3=6.5)
            assert abs(recovered - value) < 1e-3

    def test_kgh_requires_density(self):
        with pytest.raises(ValueError, match="yogunlugu gereklidir"):
            gas_flow_to_nm3h(100.0, "kgh")

    def test_unknown_unit(self):
        with pytest.raises(ValueError, match="Bilinmeyen gaz debi birimi"):
            gas_flow_to_nm3h(1.0, "gpm")


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
