import pytest

from multi_case import OperatingCase, size_multicase


def test_liquid_multi_case_sizing():
    cases = [
        OperatingCase(name="Min", flow=15.0, p1_bar_a=6.0, p2_bar_a=4.0, temperature_c=25.0),
        OperatingCase(name="Normal", flow=50.0, p1_bar_a=6.0, p2_bar_a=4.0, temperature_c=25.0),
        OperatingCase(name="Max", flow=80.0, p1_bar_a=5.8, p2_bar_a=4.0, temperature_c=25.0),
    ]
    fluid_data = {
        "density_kg_m3": 998.0,
        "vapor_pressure_bar_a": 0.023,
        "critical_pressure_bar_a": 220.64,
        "viscosity_pa_s": 0.001,
        "fl": 0.9,
    }

    res = size_multicase("liquid", cases, fluid_data)
    assert res.turndown_ratio == pytest.approx(80.0 / 15.0, rel=1e-2)
    assert res.recommended is not None
    assert res.recommended.opening_min_pct < res.recommended.opening_norm_pct < res.recommended.opening_max_pct
    assert res.recommended.opening_min_pct >= 5.0
    assert res.recommended.opening_max_pct <= 92.0
    assert len(res.candidates) > 0


def test_gas_multi_case_sizing():
    cases = [
        OperatingCase(name="Min", flow=500.0, p1_bar_a=10.0, p2_bar_a=6.0, temperature_c=20.0),
        OperatingCase(name="Normal", flow=1500.0, p1_bar_a=10.0, p2_bar_a=6.0, temperature_c=20.0),
        OperatingCase(name="Max", flow=2500.0, p1_bar_a=9.5, p2_bar_a=6.0, temperature_c=20.0),
    ]
    fluid_data = {
        "molecular_weight": 16.04,
        "specific_heat_ratio": 1.31,
        "viscosity_pa_s": 1.1e-5,
        "z": 0.98,
        "fl": 0.85,
        "xt": 0.65,
    }

    res = size_multicase("gas", cases, fluid_data)
    assert res.recommended is not None
    assert "DN" in res.overall_summary
    assert res.recommended.is_acceptable is True


def test_steam_multi_case_sizing():
    cases = [
        OperatingCase(name="Min", flow=1000.0, p1_bar_a=15.0, p2_bar_a=8.0, temperature_c=220.0),
        OperatingCase(name="Normal", flow=3000.0, p1_bar_a=15.0, p2_bar_a=8.0, temperature_c=220.0),
        OperatingCase(name="Max", flow=5000.0, p1_bar_a=14.0, p2_bar_a=8.0, temperature_c=220.0),
    ]
    fluid_data = {
        "specific_heat_ratio": 1.30,
        "z": 1.0,
        "fl": 0.9,
        "xt": 0.72,
    }

    res = size_multicase("steam", cases, fluid_data)
    assert res.recommended is not None
    assert res.recommended.valve.dn_mm > 0


def test_invalid_cases_raise():
    with pytest.raises(ValueError, match="En az bir calisma durumu"):
        size_multicase("liquid", [], {})

    with pytest.raises(ValueError, match="gecerli pozitif debi"):
        cases = [OperatingCase(name="Zero", flow=0.0, p1_bar_a=5.0, p2_bar_a=2.0, temperature_c=20.0)]
        size_multicase("liquid", cases, {})
