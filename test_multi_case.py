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

    with pytest.raises(ValueError, match="Desteklenmeyen servis tipi"):
        valid_cases = [OperatingCase(name="Test", flow=10.0, p1_bar_a=5.0, p2_bar_a=2.0, temperature_c=20.0)]
        size_multicase("unknown_service", valid_cases, {})


def test_turndown_exceeds_rangeability_warning():
    cases = [
        OperatingCase(name="Min", flow=1.0, p1_bar_a=6.0, p2_bar_a=4.0, temperature_c=25.0),
        OperatingCase(name="Normal", flow=50.0, p1_bar_a=6.0, p2_bar_a=4.0, temperature_c=25.0),
        OperatingCase(name="Max", flow=120.0, p1_bar_a=6.0, p2_bar_a=4.0, temperature_c=25.0),
    ]
    fluid_data = {"density_kg_m3": 1000.0, "fl": 0.9}
    res = size_multicase("liquid", cases, fluid_data, rangeability=50.0)
    assert res.turndown_ratio == 120.0
    assert any("Turndown orani" in w for w in res.warnings)


def test_acceptable_non_perfect_candidates():
    from valve_sizing import ValveSize

    custom_series = [ValveSize(dn_mm=50, inch='2"', cv_rated=50.0)]
    cases = [
        OperatingCase(name="Min", flow=3.0, p1_bar_a=5.0, p2_bar_a=4.0, temperature_c=20.0),
        OperatingCase(name="Normal", flow=15.0, p1_bar_a=5.0, p2_bar_a=4.0, temperature_c=20.0),
        OperatingCase(name="Max", flow=28.0, p1_bar_a=5.0, p2_bar_a=4.0, temperature_c=20.0),
    ]
    fluid_data = {"density_kg_m3": 1000.0, "fl": 0.9}
    res = size_multicase("liquid", cases, fluid_data, valve_series=custom_series)
    assert res.recommended is not None
    assert res.recommended.status_label == "Kabul Edilebilir"


def test_to_isa20_process_cases():
    cases = [
        OperatingCase(name="Min", flow=10.0, p1_bar_a=6.0, p2_bar_a=4.0, temperature_c=25.0),
        OperatingCase(name="Normal", flow=30.0, p1_bar_a=6.0, p2_bar_a=4.0, temperature_c=25.0),
        OperatingCase(name="Max", flow=50.0, p1_bar_a=6.0, p2_bar_a=4.0, temperature_c=25.0),
    ]
    fluid_data = {"density_kg_m3": 1000.0, "fl": 0.9}
    res = size_multicase("liquid", cases, fluid_data)
    rows = res.to_isa20_process_cases()
    assert len(rows) == 3
    assert rows[0]["name"] == "Min"
    assert rows[0]["flow"] == 10.0
    assert rows[0]["flow_unit"] == "m3/h"
    assert rows[1]["name"] == "Normal"
    assert rows[2]["name"] == "Max"




def test_gas_multicase_extra_props_override_base_values():
    base = OperatingCase(name="Normal", flow=1500.0, p1_bar_a=10.0, p2_bar_a=6.0, temperature_c=20.0)
    overridden = OperatingCase(
        name="Normal",
        flow=1500.0,
        p1_bar_a=10.0,
        p2_bar_a=6.0,
        temperature_c=20.0,
        extra_props={"z": 0.85},
    )
    fluid_data = {
        "molecular_weight": 16.04,
        "specific_heat_ratio": 1.31,
        "viscosity_pa_s": 1.1e-5,
        "z": 1.0,
        "fl": 0.85,
        "xt": 0.65,
    }
    baseline = size_multicase("gas", [base], fluid_data)
    changed = size_multicase("gas", [overridden], fluid_data)
    assert baseline.recommended is not None and changed.recommended is not None
    assert changed.recommended.case_details["Normal"].required_cv != pytest.approx(
        baseline.recommended.case_details["Normal"].required_cv
    )
    assert fluid_data["z"] == 1.0
