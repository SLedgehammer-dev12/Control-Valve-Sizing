import unittest.mock as mock

import pytest

from fluid_properties import evaluate_gas_mixture, normalize_composition
from valve_sizing import (
    DEFAULT_VALVE_SERIES,
    GasSizingInput,
    LiquidSizingInput,
    SteamSizingInput,
    _size_iteration,
    size_gas_valve,
    size_liquid_valve,
    size_steam_valve,
)
from vendor_catalog import get_vendor_definition


def test_liquid_sizing_returns_reasonable_cv():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=25.0,
            inlet_pressure_bar_a=8.0,
            outlet_pressure_bar_a=5.0,
            density_kg_m3=998.0,
            vapor_pressure_bar_a=0.03,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["required_cv"] > 0.0
    assert result["required_kv"] > 0.0
    assert result["ff"] > 0.0


def test_liquid_choked_condition_detected():
    vendor = get_vendor_definition("fisher_bfly_90")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=40.0,
            inlet_pressure_bar_a=10.0,
            outlet_pressure_bar_a=1.0,
            density_kg_m3=950.0,
            vapor_pressure_bar_a=0.5,
            critical_pressure_bar_a=46.0,
            viscosity_pa_s=0.0008,
            fl=vendor.fl or 0.55,
            fd=vendor.fd or 1.0,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["is_choked"] is True
    assert result["flow_regime"] in {"choked-cavitating", "flashing"}


def test_gas_sizing_returns_cv():
    vendor = get_vendor_definition("fisher_globe_linear")
    result = size_gas_valve(
        GasSizingInput(
            flow_nm3h=800.0,
            inlet_pressure_bar_a=8.0,
            outlet_pressure_bar_a=6.0,
            temperature_c=20.0,
            molecular_weight=18.0,
            specific_heat_ratio=1.28,
            viscosity_pa_s=1.1e-5,
            z=0.98,
            xt=vendor.xt or 0.64,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["required_cv"] > 0.0
    assert result["expansion_factor_y"] <= 1.0
    assert result["x_choked"] > 0.0


def test_gas_noise_receives_fl_then_fd(monkeypatch):
    import valve_sizing

    captured = []

    def fake_noise(service, _flow, _p1, _p2, _t_k, _density, _k, _mw, _kv, _valve_d, _pipe_d, fl, fd, _vapor_pressure_bar=None):
        captured.append((service, fl, fd))
        return 80.0

    monkeypatch.setattr(valve_sizing, "_predict_valve_noise", fake_noise)
    vendor = get_vendor_definition("fisher_globe_eqpct")
    size_gas_valve(
        GasSizingInput(
            flow_nm3h=800.0,
            inlet_pressure_bar_a=8.0,
            outlet_pressure_bar_a=6.0,
            temperature_c=20.0,
            molecular_weight=18.0,
            specific_heat_ratio=1.28,
            viscosity_pa_s=1.1e-5,
            z=0.98,
            xt=vendor.xt or 0.64,
        ),
        valve_series=list(vendor.sizes),
    )
    assert captured == [("gas", 0.9, 1.0)]


def test_gas_required_cv_scales_with_normal_flow():
    vendor = get_vendor_definition("fisher_globe_eqpct")

    def result(flow: float):
        return size_gas_valve(
            GasSizingInput(
                flow_nm3h=flow,
                inlet_pressure_bar_a=8.0,
                outlet_pressure_bar_a=6.0,
                temperature_c=20.0,
                molecular_weight=18.0,
                specific_heat_ratio=1.28,
                viscosity_pa_s=1.1e-5,
                z=0.98,
                xt=vendor.xt or 0.64,
            ),
            valve_series=list(vendor.sizes),
        )

    low = result(200.0)
    high = result(400.0)
    assert high["required_cv"] / low["required_cv"] == pytest.approx(2.0, rel=1e-6)
    assert not low.get("overflow", False)


def test_gas_xt_rejects_out_of_range():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    for xt in (0.0, 1.01, float("nan")):
        with pytest.raises(ValueError, match="xT"):
            size_gas_valve(
                GasSizingInput(
                    flow_nm3h=800.0,
                    inlet_pressure_bar_a=8.0,
                    outlet_pressure_bar_a=6.0,
                    temperature_c=20.0,
                    molecular_weight=18.0,
                    specific_heat_ratio=1.28,
                    viscosity_pa_s=1.1e-5,
                    z=0.98,
                    xt=xt,
                ),
                valve_series=list(vendor.sizes),
            )


def test_gas_fk_and_choke_transition():
    vendor = get_vendor_definition("fisher_globe_eqpct")

    def result(p2: float):
        return size_gas_valve(
            GasSizingInput(
                flow_nm3h=800.0,
                inlet_pressure_bar_a=8.0,
                outlet_pressure_bar_a=p2,
                temperature_c=20.0,
                molecular_weight=18.0,
                specific_heat_ratio=1.68,
                viscosity_pa_s=1.1e-5,
                z=0.98,
                xt=0.5,
            ),
            valve_series=list(vendor.sizes),
        )

    normal = result(7.0)
    choked = result(1.0)
    assert normal["fk"] == pytest.approx(1.2, rel=1e-9)
    assert normal["x_choked"] == pytest.approx(0.6, rel=1e-3)
    assert normal["is_choked"] is False
    assert 0.0 < normal["expansion_factor_y"] <= 1.0
    assert choked["is_choked"] is True
    assert 0.0 < choked["expansion_factor_y"] <= 1.0


def test_steam_sizing_returns_cv():
    vendor = get_vendor_definition("fisher_globe_linear")
    result = size_steam_valve(
        SteamSizingInput(
            flow_kg_h=2500.0,
            inlet_pressure_bar_a=12.0,
            outlet_pressure_bar_a=8.0,
            temperature_c=220.0,
            specific_heat_ratio=1.30,
            xt=vendor.xt or 0.64,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["required_cv"] > 0.0
    assert result["service"] == "steam"


def test_mass_composition_normalizes_to_mole_fraction():
    summary = normalize_composition(
        [
            {"component": "Methane", "fraction_pct": 80.0},
            {"component": "Ethane", "fraction_pct": 20.0},
        ],
        "mass",
    )
    assert abs(sum(summary.mole_fractions.values()) - 1.0) < 1e-9
    assert abs(sum(summary.mass_fractions.values()) - 1.0) < 1e-9


def test_molar_composition_calculates_mass_fractions():
    summary = normalize_composition(
        [
            {"component": "Methane", "fraction_pct": 75.0},
            {"component": "Ethane", "fraction_pct": 25.0},
        ],
        "molar",
    )
    assert abs(sum(summary.mole_fractions.values()) - 1.0) < 1e-9
    assert abs(sum(summary.mass_fractions.values()) - 1.0) < 1e-9
    assert summary.average_molecular_weight > 0


def test_gas_composition_validation_rejects_total_not_100():
    with pytest.raises(ValueError, match="Toplam kompozisyon 100% olmali"):
        evaluate_gas_mixture(
            [
                {"component": "Methane", "fraction_pct": 90.0},
                {"component": "Ethane", "fraction_pct": 5.0},
            ],
            "molar",
            pressure_bar_a=8.0,
            temperature_c=20.0,
        )


def test_gas_composition_fallback_handles_unknown_component():
    result = evaluate_gas_mixture(
        [
            {"component": "Methane", "fraction_pct": 80.0},
            {"component": "NotAFluid", "fraction_pct": 20.0},
        ],
        "molar",
        pressure_bar_a=8.0,
        temperature_c=20.0,
    )
    assert result.z == 1.0
    assert result.specific_heat_ratio == 1.4
    assert 5.0 < result.density_kg_m3 < 7.0


def test_liquid_valve_overflow_selects_largest_and_warns():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=10000.0,
            inlet_pressure_bar_a=8.0,
            outlet_pressure_bar_a=7.9,
            density_kg_m3=998.0,
            vapor_pressure_bar_a=0.023,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
            pipe_inlet_diameter_mm=80.0,
            pipe_outlet_diameter_mm=80.0,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["rated_cv"] == max(v.cv_rated for v in vendor.sizes)
    assert "en buyuk boyut" in result["warning"].lower()


# --- Edge case tests ---

def test_liquid_zero_flow_raises():
    with pytest.raises(ValueError, match="0'dan buyuk"):
        size_liquid_valve(LiquidSizingInput(0, 8, 5, 998, 0.03, 220.64, 0.00089, fl=0.9, fd=1.0))


def test_liquid_p2_greater_than_p1_raises():
    with pytest.raises(ValueError, match="buyuk olmalidir"):
        size_liquid_valve(LiquidSizingInput(25, 5, 8, 998, 0.03, 220.64, 0.00089, fl=0.9, fd=1.0))


def test_liquid_negative_density_raises():
    with pytest.raises(ValueError, match="0'dan buyuk"):
        size_liquid_valve(LiquidSizingInput(25, 8, 5, -1, 0.03, 220.64, 0.00089, fl=0.9, fd=1.0))


def test_gas_zero_flow_raises():
    with pytest.raises(ValueError, match="0'dan buyuk"):
        size_gas_valve(GasSizingInput(0, 8, 6, 20, 18, 1.28, 1.1e-5, z=0.98, xt=0.7))


def test_size_iteration_selects_smallest_adequate():
    valve, details, overflow = _size_iteration(
        DEFAULT_VALVE_SERIES,
        None,
        None,
        lambda _d1, _d2, _d: {"Kv": 18.0},
    )
    assert overflow is False
    assert valve.dn_mm == 40
    assert valve.cv_rated == 30.0


def test_size_iteration_overflow_selects_largest():
    valve, details, overflow = _size_iteration(
        DEFAULT_VALVE_SERIES,
        None,
        None,
        lambda _d1, _d2, _d: {"Kv": 99999.0},
    )
    assert overflow is True
    assert valve == DEFAULT_VALVE_SERIES[-1]


def test_cv_kv_conversion_roundtrip():
    from valve_sizing import cv_to_kv, kv_to_cv
    cv = 100.0
    kv = cv_to_kv(cv)
    assert abs(kv_to_cv(kv) - cv) < 1e-9


def test_diameter_mm_to_m_zero():
    from valve_sizing import _diameter_mm_to_m
    assert _diameter_mm_to_m(0.0, 50) == 0.0  # was bug: returned 0.05


def test_diameter_mm_to_m_none():
    from valve_sizing import _diameter_mm_to_m
    assert _diameter_mm_to_m(None, 50) == 0.05


def test_all_liquid_regimes_parametrized():
    cases = [
        (25, 8, 5, "subcritical"),
        (40, 10, 1, "choked"),
    ]
    for flow, p1, p2, expected in cases:
        result = size_liquid_valve(LiquidSizingInput(flow, p1, p2, 998, 0.03, 220.64, 0.00089, fl=0.9, fd=1.0))
        if expected == "choked":
            assert result["is_choked"] is True
        else:
            assert result["is_choked"] is False


def test_gas_choked_detection():
    # High pressure drop should cause choked flow
    result = size_gas_valve(GasSizingInput(800, 8, 3, 20, 18, 1.28, 1.1e-5, z=0.98, xt=0.5))
    assert result["is_choked"] is True


def test_gas_not_choked():
    # Low pressure drop should not choke
    result = size_gas_valve(GasSizingInput(800, 8, 7.5, 20, 18, 1.28, 1.1e-5, z=0.98, xt=0.7))
    assert result["is_choked"] is False


# --- Steam IEC-sizing edge case tests ---

def test_steam_choked_detection():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_steam_valve(
        SteamSizingInput(
            flow_kg_h=2500.0,
            inlet_pressure_bar_a=12.0,
            outlet_pressure_bar_a=3.0,
            temperature_c=220.0,
            specific_heat_ratio=1.30,
            xt=vendor.xt or 0.69,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 0.31,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["is_choked"] is True


def test_steam_overflow_selects_largest():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_steam_valve(
        SteamSizingInput(
            flow_kg_h=999999.0,
            inlet_pressure_bar_a=50.0,
            outlet_pressure_bar_a=49.9,
            temperature_c=300.0,
            xt=vendor.xt or 0.69,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 0.31,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["rated_cv"] == max(v.cv_rated for v in vendor.sizes)
    assert "en buyuk boyut" in result["warning"].lower()


def test_steam_not_choked():
    result = size_steam_valve(
        SteamSizingInput(
            flow_kg_h=2500.0,
            inlet_pressure_bar_a=12.0,
            outlet_pressure_bar_a=11.0,
            temperature_c=220.0,
            xt=0.72,
        ),
    )
    assert result["is_choked"] is False


def test_steam_returns_expansion_factor():
    result = size_steam_valve(
        SteamSizingInput(
            flow_kg_h=2500.0,
            inlet_pressure_bar_a=12.0,
            outlet_pressure_bar_a=8.0,
            temperature_c=220.0,
            xt=0.72,
        ),
    )
    assert result["expansion_factor_y"] <= 1.0
    assert result["x_choked"] > 0.0


# --- Fluid properties error paths ---

def test_empty_composition_raises():
    with pytest.raises(ValueError, match="En az bir bilesen"):
        normalize_composition([], "molar")


def test_negative_percent_raises():
    with pytest.raises(ValueError, match="negatif"):
        normalize_composition(
            [{"component": "Methane", "fraction_pct": -5.0}],
            "molar",
        )


def test_invalid_basis_raises():
    with pytest.raises(ValueError, match="'molar' veya 'mass'"):
        normalize_composition(
            [{"component": "Methane", "fraction_pct": 100.0}],
            "volume",
        )


# --- Liquid regime edge cases ---

def test_liquid_flashing_regime():
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=25.0, inlet_pressure_bar_a=8.0, outlet_pressure_bar_a=0.01,
            density_kg_m3=998.0, vapor_pressure_bar_a=0.5, critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089, fl=0.9, fd=1.0,
        )
    )
    assert result["flow_regime"] == "flashing"
    assert "Flashing" in result["warning"]


def test_liquid_cavitation_risk_regime():
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=25.0, inlet_pressure_bar_a=8.0, outlet_pressure_bar_a=1.0,
            density_kg_m3=998.0, vapor_pressure_bar_a=0.03, critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089, fl=0.9, fd=1.0,
        )
    )
    assert result["flow_regime"] in {"choked-cavitating", "cavitating-risk", "subcritical"}


# --- Gas overflow test ---

def test_gas_overflow_selects_largest():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_gas_valve(
        GasSizingInput(
            flow_nm3h=999999.0, inlet_pressure_bar_a=1.5, outlet_pressure_bar_a=1.4,
            temperature_c=20.0, molecular_weight=18.0,
            specific_heat_ratio=1.28, viscosity_pa_s=1.1e-5,
            z=0.98, xt=vendor.xt or 0.69,
            fl=vendor.fl or 0.85, fd=vendor.fd or 0.31,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["rated_cv"] == max(v.cv_rated for v in vendor.sizes)
    assert "en buyuk boyut" in result["warning"].lower()


# --- Nm3/h to actual flow conversion ---

def test_gas_normal_to_actual_conversion_reduces_cv():
    result_no_convert = size_gas_valve(
        GasSizingInput(800, 8, 6, 20, 18, 1.28, 1.1e-5, z=0.98, xt=0.7),
    )
    assert result_no_convert["intermediate_values"]["Q_nm3h"] == 800.0
    assert result_no_convert["intermediate_values"]["Q_actual_m3h"] < 800.0
    assert result_no_convert["required_cv"] > 0.0

def test_gas_normal_to_actual_atmospheric_approx_equal():
    result = size_gas_valve(
        GasSizingInput(800, 1.05, 1.0, 0, 18, 1.28, 1.1e-5, z=1.0, xt=0.7),
    )
    q_nm3h = result["intermediate_values"]["Q_nm3h"]
    q_actual = result["intermediate_values"]["Q_actual_m3h"]
    assert abs(q_actual / q_nm3h - 1.0) < 0.05

def test_gas_nm3h_conversion_recorded():
    result = size_gas_valve(
        GasSizingInput(800, 8, 7.5, 20, 18, 1.28, 1.1e-5, z=1.0, xt=0.7),
    )
    iv = result["intermediate_values"]
    expected_actual = 800 * (1.01325 / 8) * (293.15 / 273.15) * 1.0
    assert abs(iv["Q_actual_m3h"] - expected_actual) < 0.01

# --- Steam CoolProp fallback ---

def test_steam_fallback_when_coolprop_fails():
    with mock.patch("CoolProp.CoolProp.PropsSI", side_effect=RuntimeError("CoolProp unavailable")):
        result = size_steam_valve(
            SteamSizingInput(
                flow_kg_h=2500.0, inlet_pressure_bar_a=12.0, outlet_pressure_bar_a=8.0,
                temperature_c=220.0, xt=0.72,
            ),
        )
    assert result["required_cv"] > 0.0
    assert result["is_choked"] is False


# --- Z sensitivity analysis ---

def test_z_sensitivity_returns_three_cv_values():
    from valve_sizing import z_sensitivity_gas
    result = z_sensitivity_gas(
        GasSizingInput(800, 8, 6, 20, 18, 1.28, 1.1e-5, z=0.98, xt=0.7),
    )
    assert result["cv_low"] > 0
    assert result["cv_mid"] > 0
    assert result["cv_high"] > 0
    assert result["delta_z"] == 0.05
    assert result["cv_low"] <= result["cv_mid"] <= result["cv_high"]


def test_z_sensitivity_delta_percent_non_negative():
    from valve_sizing import z_sensitivity_gas
    result = z_sensitivity_gas(
        GasSizingInput(800, 8, 6, 20, 18, 1.28, 1.1e-5, z=0.98, xt=0.7),
        delta_z=0.1,
    )
    assert result["delta_percent"] >= 0
    assert result["delta_z"] == 0.1


def test_z_sensitivity_zero_delta_returns_same():
    from valve_sizing import z_sensitivity_gas
    result = z_sensitivity_gas(
        GasSizingInput(800, 8, 6, 20, 18, 1.28, 1.1e-5, z=0.98, xt=0.7),
        delta_z=0.0,
    )
    assert abs(result["cv_low"] - result["cv_mid"]) < 1e-9
    assert abs(result["cv_high"] - result["cv_mid"]) < 1e-9


# --- Fluid properties edge cases ---

def test_clean_rows_skips_non_numeric_fraction():
    from fluid_properties import normalize_composition
    with pytest.raises(ValueError, match="En az bir bilesen"):
        normalize_composition(
            [{"component": "Methane", "fraction_pct": "abc"}, {"component": "Ethane", "fraction_pct": "def"}],
            "molar",
        )


def test_clean_rows_skips_empty_component():
    from fluid_properties import normalize_composition
    with pytest.raises(ValueError, match="En az bir bilesen"):
        normalize_composition(
            [{"component": "", "fraction_pct": 50.0}],
            "molar",
        )


def test_get_liquid_preset_unknown():
    from fluid_properties import get_liquid_preset
    with pytest.raises(ValueError, match="Bilinmeyen sivi preset"):
        get_liquid_preset("NonExistentFluid")


def test_get_liquid_preset_new_presets():
    from fluid_properties import get_liquid_preset
    for name in ("Propane", "Ammonia", "Hydrogen", "Diesel", "HeavyFuelOil"):
        preset = get_liquid_preset(name)
        assert preset["density_kg_m3"] > 0
        assert preset["viscosity_pa_s"] > 0


def test_list_coolprop_fluids():
    from fluid_properties import list_coolprop_fluids
    fluids = list_coolprop_fluids()
    assert "Water" in fluids
    assert "Methane" in fluids


def test_get_pure_fluid_state_water():
    from fluid_properties import get_pure_fluid_state
    state = get_pure_fluid_state("Water", 1.0, 20.0)
    assert state["density_kg_m3"] > 0
    assert state["z"] > 0


# --- Project I/O validation edge cases ---

def test_validate_project_payload_rejects_non_dict():
    from project_io import validate_project_payload
    with pytest.raises(ValueError, match="JSON nesnesi olmalidir"):
        validate_project_payload("not a dict")


def test_validate_project_payload_rejects_invalid_service():
    from project_io import validate_project_payload
    with pytest.raises(ValueError, match="service degeri"):
        validate_project_payload({
            "project_type": "control_valve_sizing",
            "service": "Plasma",
            "data": {},
        })


# --- Reporting edge cases ---

def test_report_includes_warning():
    from reporting import build_report
    from valve_sizing import LiquidSizingInput, size_liquid_valve
    from vendor_catalog import get_vendor_definition
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(10000, 8, 7.9, 998, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
        valve_series=list(vendor.sizes),
    )
    report = build_report("Liquid", None, result)
    assert "Warning" in report or "Uyari" in report or "warning" in report.lower()


def test_report_includes_vendor_meta():
    from reporting import build_report
    from valve_sizing import LiquidSizingInput, size_liquid_valve
    from vendor_catalog import get_vendor_definition
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(25, 8, 5, 998, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
        valve_series=list(vendor.sizes),
        valve_meta={"vendor": vendor.vendor},
    )
    report = build_report("Liquid", None, result)
    assert "Vendor Data" in report


def test_report_includes_z_when_present():
    from reporting import build_report
    from valve_sizing import GasSizingInput, size_gas_valve
    result = size_gas_valve(GasSizingInput(800, 8, 6, 20, 18, 1.28, 1.1e-5, z=0.95, xt=0.7))
    report = build_report("Gas", None, result)
    assert "Compressibility (Z)" in report
    assert "0.95" in report


# --- Opening / characteristic / design margin (F2.1) ---

def test_estimate_opening_linear_is_ratio():
    from valve_sizing import estimate_opening
    assert estimate_opening(25.0, 50.0, characteristic="linear") == pytest.approx(0.5)
    assert estimate_opening(0.0, 50.0, characteristic="linear") == 0.0
    assert estimate_opening(60.0, 50.0, characteristic="linear") == 1.0


def test_estimate_opening_equal_percentage_bounds():
    from valve_sizing import DEFAULT_RANGEABILITY, estimate_opening
    r = DEFAULT_RANGEABILITY
    assert estimate_opening(50.0, 50.0) == pytest.approx(1.0)
    assert estimate_opening(50.0 / r, 50.0) == pytest.approx(0.0)
    assert estimate_opening(25.0, 50.0) == pytest.approx(0.82301, abs=1e-3)


def test_estimate_opening_fallback():
    from valve_sizing import estimate_opening

    assert estimate_opening(25.0, 50.0, rangeability=1.0) == 0.5
    assert estimate_opening(25.0, 50.0, characteristic="custom") == 0.5


def test_min_controllable_cv():
    from valve_sizing import DEFAULT_RANGEABILITY, estimate_min_controllable_cv
    assert estimate_min_controllable_cv(100.0) == pytest.approx(100.0 / DEFAULT_RANGEABILITY)
    assert estimate_min_controllable_cv(100.0, rangeability=1.0) == 100.0
    assert estimate_min_controllable_cv(100.0, characteristic="linear") == pytest.approx(1.0)


def test_design_margin_increases_required_cv():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result_plain = size_liquid_valve(
        LiquidSizingInput(25, 8, 5, 998, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
        valve_series=list(vendor.sizes),
    )
    result_margin = size_liquid_valve(
        LiquidSizingInput(25, 8, 5, 998, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
        valve_series=list(vendor.sizes),
        design_margin_pct=20.0,
    )
    assert result_margin["required_cv_with_margin"] > result_plain["required_cv"]
    assert result_margin["design_margin_pct"] == 20.0
    assert result_margin["opening_percent"] < result_plain["opening_percent"]


def test_opening_fields_accessible_via_attributes():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(25, 8, 5, 998, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
        valve_series=list(vendor.sizes),
    )
    assert 0.0 <= result.opening_percent <= 100.0
    assert result.cv_ratio > 0.0
    assert result.rangeability_ok is True


def test_opening_warning_when_above_85_percent():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    flow = 20.0
    while True:
        result = size_liquid_valve(
            LiquidSizingInput(flow, 8, 5, 998, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
            valve_series=list(vendor.sizes),
        )
        if result["opening_percent"] > 85.0:
            break
        flow *= 10.0
    assert "%85" in result["warning"] or "85" in result["warning"]


def test_rangeability_warning_when_below_min_cv():
    from valve_sizing import DEFAULT_VALVE_SERIES, LiquidSizingInput, size_liquid_valve
    tiny_flow = 1e-6
    result = size_liquid_valve(
        LiquidSizingInput(tiny_flow, 8, 5, 998, 0.023, 220.64, 0.00089, fl=0.85, fd=1.0),
        valve_series=DEFAULT_VALVE_SERIES,
    )
    assert result["rangeability_ok"] is False
    assert "rangeability" in result["warning"].lower()


def test_flashing_estimates_two_phase_cv():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=40.0,
            inlet_pressure_bar_a=10.0,
            outlet_pressure_bar_a=0.2,
            density_kg_m3=950.0,
            vapor_pressure_bar_a=2.5,
            critical_pressure_bar_a=46.0,
            viscosity_pa_s=0.0008,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
            temperature_c=120.0,
            specific_heat_j_kgk=4200.0,
            latent_heat_j_kg=2.0e6,
            molecular_weight=18.015,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["flow_regime"] == "flashing"
    assert result["flashing"]["required_cv_flashing"] > result["flashing"]["required_cv_single_phase"]
    assert result["flashing"]["flashing_cv_multiplier"] > 1.0


def test_valve_spec_present_in_result():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(25, 8, 5, 998, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
        valve_series=list(vendor.sizes),
    )
    spec = result["valve_spec"]
    assert spec["service"] == "liquid"
    assert spec["pressure_class_recommended"] in {"CL150", "CL300"}
    assert spec["leakage_class_recommended"] in {"IV", "V", "VI"}


def test_pipe_velocity_basic():
    from valve_sizing import pipe_velocity_m_s

    v = pipe_velocity_m_s(0.01, 100.0)
    assert v == pytest.approx(1.2732, abs=1e-3)


def test_api_14e_erosion_velocity():
    from valve_sizing import api_14e_erosion_velocity

    assert api_14e_erosion_velocity(100.0) == pytest.approx(12.2, abs=0.01)
    assert api_14e_erosion_velocity(100.0, continuous=False) == pytest.approx(15.2, abs=0.01)


def test_speed_of_sound_air():
    from valve_sizing import speed_of_sound_m_s

    c = speed_of_sound_m_s(1.4, 293.15, 28.97)
    assert 340.0 < c < 350.0


def test_liquid_result_includes_velocity():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(25, 8, 5, 998, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
        valve_series=list(vendor.sizes),
    )
    assert result["velocity"]["pipe_out_m_s"] > 0.0


def test_gas_result_includes_mach():
    result = size_gas_valve(GasSizingInput(800, 8, 6, 20, 18, 1.28, 1.1e-5, z=0.95, xt=0.7))
    assert 0.0 < result["velocity"]["mach_outlet"] < 1.0


def test_flashing_includes_erosion_check():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=40.0,
            inlet_pressure_bar_a=10.0,
            outlet_pressure_bar_a=0.2,
            density_kg_m3=950.0,
            vapor_pressure_bar_a=2.5,
            critical_pressure_bar_a=46.0,
            viscosity_pa_s=0.0008,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
            temperature_c=120.0,
        ),
        valve_series=list(vendor.sizes),
    )
    assert "api_14e_limit_m_s" in result["velocity"]
    assert "erosion_risk" in result["velocity"]


def test_trim_guidance_present_for_all_services():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    liquid = size_liquid_valve(
        LiquidSizingInput(25, 8, 5, 998, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
        valve_series=list(vendor.sizes),
    )
    gas = size_gas_valve(GasSizingInput(800, 8, 6, 20, 18, 1.28, 1.1e-5, z=0.95, xt=0.7))
    assert isinstance(liquid["trim_guidance"], list) and liquid["trim_guidance"]
    assert isinstance(gas["trim_guidance"], list) and gas["trim_guidance"]


def test_trim_guidance_flashing_rule():
    from trim_guidance import recommend_trim

    recs = recommend_trim("liquid", flow_regime="flashing")
    assert any("Anti-flash" in r for r in recs)


def test_trim_guidance_noise_rule():
    from trim_guidance import recommend_trim

    recs = recommend_trim("gas", noise_db=90.0)
    assert any("dusuk gurultu trimi" in r.lower() for r in recs)


def test_trim_guidance_low_opening_rule():
    from trim_guidance import recommend_trim

    recs = recommend_trim("gas", opening_percent=10.0)
    assert any("reduced capacity trim" in r for r in recs)


def test_trim_guidance_default_when_clean():
    from trim_guidance import recommend_trim

    recs = recommend_trim("gas", opening_percent=50.0, pressure_drop_ratio_x=0.2)
    assert any("Standart trim" in r for r in recs)


def test_actuator_selection_in_sizing_results():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(25, 8, 5, 998, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
        valve_series=list(vendor.sizes),
    )
    act_sel = result.get("actuator_selection")
    assert act_sel is not None
    assert "model" in act_sel
    assert act_sel["selected"] is True
    assert act_sel["thrust_margin_pct"] > 0
    assert act_sel["stroke_ok"] is True


def test_liquid_inlet_below_vapor_pressure_warning():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=25.0,
            inlet_pressure_bar_a=1.02,
            outlet_pressure_bar_a=0.5,
            density_kg_m3=998.0,
            vapor_pressure_bar_a=1.05,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
        ),
        valve_series=list(vendor.sizes),
    )
    assert "buhar basincina" in result["warning"]


def test_liquid_inlet_below_ff_pv_raises():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    with pytest.raises(ValueError, match="kaynayarak giriyor"):
        size_liquid_valve(
            LiquidSizingInput(
                flow_m3h=25.0,
                inlet_pressure_bar_a=1.0,
                outlet_pressure_bar_a=0.5,
                density_kg_m3=998.0,
                vapor_pressure_bar_a=2.0,
                critical_pressure_bar_a=220.64,
                viscosity_pa_s=0.00089,
                fl=vendor.fl or 0.85,
                fd=vendor.fd or 1.0,
            ),
            valve_series=list(vendor.sizes),
        )


def test_predict_actuator_fallbacks(monkeypatch):
    import valve_sizing
    from valve_sizing import _predict_actuator_selection, _predict_actuator_thrust

    def _fail(*_args, **_kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(valve_sizing, "total_required_thrust", _fail)
    assert _predict_actuator_thrust(50, 10.0, 5.0) is None

    assert _predict_actuator_selection(50, None) is None
    assert _predict_actuator_selection(50, {}) is None
    monkeypatch.setattr(valve_sizing, "select_actuator", _fail)
    assert _predict_actuator_selection(50, {"total_n": 1000.0}) is None


def test_size_steam_valve_coolprop_and_ideal_gas_fallbacks(monkeypatch):
    import CoolProp.CoolProp as CP  # noqa: N817

    import fluid_properties
    from valve_sizing import SteamSizingInput, size_steam_valve

    inp = SteamSizingInput(
        flow_kg_h=1000.0,
        inlet_pressure_bar_a=10.0,
        outlet_pressure_bar_a=5.0,
        temperature_c=250.0,
        specific_heat_ratio=1.3,
        z=0.95,
        fl=0.9,
        fd=0.46,
        xt=0.72,
    )

    def _fail(*_args, **_kwargs):
        raise RuntimeError("coolprop down")

    monkeypatch.setattr(fluid_properties, "get_steam_properties_iapws", lambda *_a, **_kw: None)
    res_coolprop = size_steam_valve(inp)
    assert res_coolprop.required_cv > 0

    monkeypatch.setattr(CP, "PropsSI", _fail)
    res_ideal = size_steam_valve(inp)
    assert res_ideal.required_cv > 0
    assert "ideal gaz yaklasimi kullanildi" in res_ideal.warning


def test_sizing_advisory_and_rangeability_warnings():
    from valve_sizing import (
        GasSizingInput,
        LiquidSizingInput,
        SteamSizingInput,
        size_gas_valve,
        size_liquid_valve,
        size_steam_valve,
    )

    liq = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=49.48,
            inlet_pressure_bar_a=15.0,
            outlet_pressure_bar_a=12.0,
            density_kg_m3=1000.0,
            vapor_pressure_bar_a=0.023,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.001,
            fl=0.9,
            fd=0.46,
            pipe_inlet_diameter_mm=50.0,
            pipe_outlet_diameter_mm=50.0,
        )
    )
    assert "uzun sureli servis icin degerlendirilmelidir" in liq.warning

    gas = size_gas_valve(
        GasSizingInput(
            flow_nm3h=0.05,
            inlet_pressure_bar_a=5.0,
            outlet_pressure_bar_a=4.5,
            temperature_c=20.0,
            molecular_weight=28.96,
            specific_heat_ratio=1.4,
            viscosity_pa_s=1.8e-5,
            z=1.0,
            fl=0.9,
            fd=0.46,
            xt=0.72,
        )
    )
    assert "rangeability disinda" in gas.warning

    stm = size_steam_valve(
        SteamSizingInput(
            flow_kg_h=0.5,
            inlet_pressure_bar_a=5.0,
            outlet_pressure_bar_a=4.0,
            temperature_c=200.0,
            specific_heat_ratio=1.3,
            z=0.95,
            fl=0.9,
            fd=0.46,
            xt=0.72,
        )
    )
    assert "rangeability disinda" in stm.warning

    stm_mach = size_steam_valve(
        SteamSizingInput(
            flow_kg_h=5000.0,
            inlet_pressure_bar_a=10.0,
            outlet_pressure_bar_a=2.0,
            temperature_c=300.0,
            specific_heat_ratio=1.3,
            z=0.95,
            fl=0.9,
            fd=0.46,
            xt=0.72,
            pipe_outlet_diameter_mm=105.0,
        )
    )
    assert "uzeri gurultu acisindan degerlendirilmelidir" in stm_mach.warning


# --- Edge cases -----------------------------------------------------------

def test_liquid_p2_equals_pv_flashing_boundary():
    """P2 tam olarak Pv'e esit ise flashing rejimi olmalidir."""
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=25.0,
            inlet_pressure_bar_a=8.0,
            outlet_pressure_bar_a=0.023,
            density_kg_m3=998.0,
            vapor_pressure_bar_a=0.023,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["flow_regime"] == "flashing"
    assert result["required_cv"] > 0.0


def test_liquid_p1_equals_pv_raises():
    """P1 <= FF*Pv ise tek fazli sizing uygulanamaz, hata firlatilmali."""
    vendor = get_vendor_definition("fisher_globe_eqpct")
    # ff = 0.96 - 0.28*sqrt(0.023/220.64) ~ 0.957, ff*pv ~ 0.022
    # P1=0.02 < 0.022 => hata
    with pytest.raises(ValueError, match="buhar basincinin ve kavitasyon"):
        size_liquid_valve(
            LiquidSizingInput(
                flow_m3h=25.0,
                inlet_pressure_bar_a=0.02,
                outlet_pressure_bar_a=0.01,
                density_kg_m3=998.0,
                vapor_pressure_bar_a=0.023,
                critical_pressure_bar_a=220.64,
                viscosity_pa_s=0.00089,
                fl=vendor.fl or 0.85,
                fd=vendor.fd or 1.0,
            ),
            valve_series=list(vendor.sizes),
        )


def test_liquid_very_small_pressure_drop():
    """Cok kucuk DeltaP icin pozitif Cv donmelidir."""
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=1.0,
            inlet_pressure_bar_a=5.0,
            outlet_pressure_bar_a=4.999,
            density_kg_m3=998.0,
            vapor_pressure_bar_a=0.023,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["required_cv"] > 0.0
    assert result["is_choked"] is False


def test_gas_choked_boundary():
    """x tam olarak x_choked'a esit ise choked=True olmalidir."""
    vendor = get_vendor_definition("fisher_globe_eqpct")
    # xT=0.72, k=1.4 => fk=1.0, x_choked=0.72. x=DeltaP/P1 => P2=P1*(1-0.72)=0.28*P1
    p1 = 10.0
    p2 = p1 * (1.0 - 0.72)
    result = size_gas_valve(
        GasSizingInput(
            flow_nm3h=100.0,
            inlet_pressure_bar_a=p1,
            outlet_pressure_bar_a=p2,
            temperature_c=20.0,
            molecular_weight=28.96,
            specific_heat_ratio=1.4,
            viscosity_pa_s=1.8e-5,
            z=1.0,
            fl=vendor.fl or 0.9,
            fd=vendor.fd or 1.0,
            xt=vendor.xt or 0.72,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["is_choked"] is True


def test_steam_very_small_flow_rangeability_warning():
    """Cok kucuk debi icin rangeability uyarisi verilmeli."""
    result = size_steam_valve(
        SteamSizingInput(
            flow_kg_h=0.1,
            inlet_pressure_bar_a=5.0,
            outlet_pressure_bar_a=4.0,
            temperature_c=200.0,
            specific_heat_ratio=1.3,
            z=0.95,
            fl=0.9,
            fd=0.46,
            xt=0.72,
        )
    )
    assert "rangeability disinda" in result["warning"]


def test_cavitation_index_edge_cases():
    from two_phase import cavitation_index, xfz_cavitation_factor
    # DeltaP = 0 => sigma = inf, xFz = 0
    assert cavitation_index(5.0, 5.0, 1.0) == float("inf")
    assert xfz_cavitation_factor(5.0, 5.0, 1.0) == 0.0
    # P2 = Pv => sigma = 1.0, xFz = 1.0 (incipient cavitation boundary)
    assert cavitation_index(5.0, 1.0, 1.0) == 1.0
    assert xfz_cavitation_factor(5.0, 1.0, 1.0) == 1.0
    # Normal case
    sigma = cavitation_index(10.0, 5.0, 2.0)
    assert abs(sigma - 8.0 / 5.0) < 1e-12
    xfz = xfz_cavitation_factor(10.0, 5.0, 2.0)
    assert abs(xfz - 5.0 / 8.0) < 1e-12
    assert abs(sigma * xfz - 1.0) < 1e-12


def test_flash_fraction_zero_pressure_drop():
    from two_phase import flash_fraction
    assert flash_fraction(5.0, 5.0, 25.0, 4186.0, 2257000.0) == 0.0
    assert flash_fraction(5.0, 6.0, 25.0, 4186.0, 2257000.0) == 0.0


def test_flashing_cv_estimate_degenerate():
    from two_phase import flashing_cv_estimate
    assert flashing_cv_estimate(0.0, 0.5, 1000.0, 10.0) == 0.0
    assert flashing_cv_estimate(10.0, 0.0, 1000.0, 10.0) == 10.0
    # quality_x=1.0 => rho_tp=rho_gas=10 => Cv = 10*sqrt(1000/10) = 100
    assert flashing_cv_estimate(10.0, 1.0, 1000.0, 10.0) == 100.0


def test_size_liquid_valve_with_noise_control_no_alt_needed():
    """Low-noise service: no alt needed when noise <= limit."""
    from valve_sizing import LiquidSizingInput, size_liquid_valve, size_liquid_valve_with_noise_control
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=25.0,
            inlet_pressure_bar_a=8.0,
            outlet_pressure_bar_a=5.0,
            density_kg_m3=998.0,
            vapor_pressure_bar_a=0.023,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
        ),
        valve_series=list(vendor.sizes),
    )
    assert result["noise_db"] < 85.0

    res = size_liquid_valve_with_noise_control(
        LiquidSizingInput(
            flow_m3h=25.0,
            inlet_pressure_bar_a=8.0,
            outlet_pressure_bar_a=5.0,
            density_kg_m3=998.0,
            vapor_pressure_bar_a=0.023,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
        ),
        valve_series=list(vendor.sizes),
    )
    assert "alt" not in res  # noise <= limit, no alternative needed


def test_size_liquid_valve_with_noise_control_alt_provided():
    """High-noise service: alt provided when noise > limit."""
    from valve_sizing import LiquidSizingInput, size_liquid_valve, size_liquid_valve_with_noise_control
    vendor = get_vendor_definition("fisher_globe_eqpct")
    # High flow to force choked/noisy conditions
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=200.0,
            inlet_pressure_bar_a=50.0,
            outlet_pressure_bar_a=5.0,
            density_kg_m3=998.0,
            vapor_pressure_bar_a=0.023,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
        ),
        valve_series=list(vendor.sizes),
    )

    res = size_liquid_valve_with_noise_control(
        LiquidSizingInput(
            flow_m3h=200.0,
            inlet_pressure_bar_a=50.0,
            outlet_pressure_bar_a=5.0,
            density_kg_m3=998.0,
            vapor_pressure_bar_a=0.023,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
        ),
        valve_series=list(vendor.sizes),
    )

    if float(result["noise_db"]) > 85.0:
        assert "alt" in res
        assert res["alt"]["rated_cv"] > float(result["rated_cv"])
        assert float(res["alt"]["noise_db"]) <= float(result["noise_db"])
        assert "reason" in res["alt"]
    else:
        # If noise is already below limit, alt should not be present
        assert "alt" not in res


def test_estimate_opening_characteristics():
    from valve_sizing import estimate_opening

    assert estimate_opening(50.0, 100.0, "linear") == 0.5
    assert abs(estimate_opening(50.0, 100.0, "quick_opening") - 0.25) < 1e-12
    eqpct = estimate_opening(50.0, 100.0, "equal_percentage", rangeability=50.0)
    assert 0.0 < eqpct < 1.0
    assert estimate_opening(200.0, 100.0, "linear") == 1.0
    assert estimate_opening(0.0, 100.0, "linear") == 0.0




def test_prepare_composition_rows_normalizes_and_rejects_bad_rows():
    from fluid_properties import prepare_composition_rows

    rows, total = prepare_composition_rows(
        [{"component": "Methane", "fraction_pct": 45.0}, {"component": "Ethane", "fraction_pct": 45.0}]
    )
    assert total == pytest.approx(90.0)
    assert sum(row["fraction_pct"] for row in rows) == pytest.approx(100.0)
    assert rows[0]["fraction_pct"] == pytest.approx(50.0)

    alias_rows, alias_total = prepare_composition_rows([{"component": "CO2", "fraction_pct": 100.0}])
    assert alias_total == pytest.approx(100.0)
    assert alias_rows[0]["component"] == "CarbonDioxide"

    for bad in (
        [{"component": "Methane", "fraction_pct": 50.0}, {"component": "Methane", "fraction_pct": 50.0}],
        [{"component": "Unobtainium", "fraction_pct": 100.0}],
        [{"component": "Methane", "fraction_pct": 0.0}],
        [{"component": "Methane", "fraction_pct": float("nan")}],
    ):
        with pytest.raises(ValueError):
            prepare_composition_rows(bad)


def test_liquid_sizing_fr_and_reducer_dp_max():
    from valve_sizing import LiquidSizingInput, size_liquid_valve

    inp = LiquidSizingInput(
        flow_m3h=50.0,
        inlet_pressure_bar_a=10.0,
        outlet_pressure_bar_a=6.0,
        density_kg_m3=1000.0,
        vapor_pressure_bar_a=0.023,
        critical_pressure_bar_a=220.64,
        viscosity_pa_s=0.001,
        fl=0.90,
        pipe_inlet_diameter_mm=100.0,
        pipe_outlet_diameter_mm=100.0,
    )
    res = size_liquid_valve(inp)
    assert "fr" in res
    assert res["fr"] > 0
    assert "FR" in res["intermediate_values"]
    assert res["dp_choked_bar"] > 0

