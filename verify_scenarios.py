"""Independent calculation verification for the control valve sizing engine.

Runs 12 representative scenarios across liquid / gas / steam services and
cross-checks the program output against independent references: published
IEC worked examples, analytic IEC/ISA equations implemented from first
principles, CoolProp fluid properties, unit round-trips, design margin and
vendor catalog selection.

Run directly (python verify_scenarios.py) or import the scenario functions
/ run_scenario_verification from tests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import CoolProp.CoolProp as CP  # noqa: N817
from fluids.control_valve import N9, size_control_valve_g

from config import GAS_PRESETS
from fluid_properties import evaluate_gas_mixture
from units import (
    BAR_TO_PSI,
    M3H_TO_GPM,
    NORMAL_P_BAR,
    NORMAL_T_K,
    liquid_flow_from_m3h,
    liquid_flow_to_m3h,
    pressure_from_bar_a,
    pressure_to_bar_a,
    temperature_from_c,
    temperature_to_c,
)
from valve_sizing import (
    DEFAULT_VALVE_SERIES,
    GasSizingInput,
    LiquidSizingInput,
    SteamSizingInput,
    size_gas_valve,
    size_liquid_valve,
    size_steam_valve,
)
from vendor_catalog import get_vendor_definition

LIQUID_CV_DEV_MAX_PCT = 1.0
GAS_ANCHOR_DEV_MAX_PCT = 0.05
GAS_ANALYTIC_DEV_MAX_PCT = 1.0
STEAM_DEV_MAX_PCT = 1.0
KV_CV_RATIO = 0.865


@dataclass(frozen=True)
class ScenarioResult:
    """Verdict of a single verification scenario."""
    name: str
    service: str
    passed: bool
    detail: str
    required_kv: float = 0.0
    reference_kv: float | None = None
    deviation_pct: float | None = None
    is_choked: bool | None = None
    valve_dn_mm: int | None = None
    regime: str | None = None


def _liquid_kv_reference(flow_m3h: float, p1: float, p2: float, rho: float, pv: float, pc: float, fl: float) -> tuple[float, float, float]:
    """Independent IEC liquid Kv from Q_gpm*sqrt(SG/dP) with choke limit."""
    ff = 0.96 - 0.28 * math.sqrt(max(pv / pc, 0.0))
    delta_p_choked = max((fl ** 2) * (p1 - ff * pv), 1e-9)
    delta_p_eff = min(p1 - p2, delta_p_choked)
    sg = rho / 999.016
    kv = 0.865 * (flow_m3h * M3H_TO_GPM) * math.sqrt(sg / (delta_p_eff * BAR_TO_PSI))
    return kv, delta_p_choked, ff


def _gas_kv_from_actual(
    q_actual_m3h: float, p1: float, p2: float, t_c: float, mw: float, k: float, z: float, xt: float,
) -> tuple[float, float, float, float, bool]:
    """Independent IEC gas Kv from actual inlet volumetric flow (N9, P in kPa)."""
    t_k = t_c + 273.15
    fk = k / 1.4
    x = (p1 - p2) / p1
    x_choked = fk * xt
    choked = x >= x_choked
    y = max(1.0 - x / (3.0 * fk * xt), 2.0 / 3.0)
    denom = x_choked if choked else x
    kv = q_actual_m3h / (N9 * p1 * 1.0e2 * y) * math.sqrt(mw * t_k * z / denom)
    return kv, x, x_choked, y, choked


def _gas_kv_reference(
    flow_nm3h: float, p1: float, p2: float, t_c: float, mw: float, k: float, z: float, xt: float,
) -> tuple[float, float, float, float, bool]:
    """Independent IEC gas Kv (IEC 60534-2-1 eq. 8a / 14a, N9 constant)."""
    t_k = t_c + 273.15
    q_actual = flow_nm3h * (NORMAL_P_BAR / p1) * (t_k / NORMAL_T_K) * z
    kv, x, x_choked, y, choked = _gas_kv_from_actual(q_actual, p1, p2, t_c, mw, k, z, xt)
    return kv, x, x_choked, y, choked


def _deviation_pct(actual: float, reference: float) -> float:
    return abs(actual - reference) / reference * 100.0 if reference else 0.0


def verify_liquid_subcritical() -> ScenarioResult:
    """L1: Water globe valve, subcritical, matches analytic IEC liquid Kv."""
    data = LiquidSizingInput(
        flow_m3h=360.0, inlet_pressure_bar_a=6.8, outlet_pressure_bar_a=2.2,
        density_kg_m3=965.4, vapor_pressure_bar_a=0.701, critical_pressure_bar_a=221.2,
        viscosity_pa_s=3.1472e-4, fl=0.9, fd=0.46,
    )
    result = size_liquid_valve(data, valve_series=DEFAULT_VALVE_SERIES)
    kv_ref, dp_choked, ff = _liquid_kv_reference(360.0, 6.8, 2.2, 965.4, 0.701, 221.2, 0.9)
    dev = _deviation_pct(result.required_kv, kv_ref)
    checks = [
        dev <= LIQUID_CV_DEV_MAX_PCT,
        not result.is_choked,
        result["flow_regime"] == "subcritical",
        abs(result.required_kv / result.required_cv - KV_CV_RATIO) < 1e-6,
        result.rated_cv >= result.required_cv,
    ]
    return ScenarioResult(
        name="L1 - Sivi (su), kritik alti globe",
        service="liquid",
        passed=all(checks),
        detail=(
            f"Kv=program {result.required_kv:.3f}, analitik {kv_ref:.3f} (sapma %{dev:.3f}); "
            f"DeltaP_choked={dp_choked:.3f} bar (FF={ff:.4f}), choked={result.is_choked}, "
            f"rejim={result['flow_regime']}, secilen DN{result.valve_dn_mm}."
        ),
        required_kv=result.required_kv, reference_kv=kv_ref, deviation_pct=dev,
        is_choked=result.is_choked, valve_dn_mm=result.valve_dn_mm, regime=result["flow_regime"],
    )


def verify_liquid_choked() -> ScenarioResult:
    """L2: Water ball valve in choke, matches analytic choked liquid Kv."""
    data = LiquidSizingInput(
        flow_m3h=360.0, inlet_pressure_bar_a=6.8, outlet_pressure_bar_a=2.2,
        density_kg_m3=965.4, vapor_pressure_bar_a=0.701, critical_pressure_bar_a=221.2,
        viscosity_pa_s=3.1472e-4, fl=0.6, fd=0.98,
    )
    result = size_liquid_valve(data, valve_series=DEFAULT_VALVE_SERIES)
    kv_ref, dp_choked, ff = _liquid_kv_reference(360.0, 6.8, 2.2, 965.4, 0.701, 221.2, 0.6)
    dev = _deviation_pct(result.required_kv, kv_ref)
    sigma_ref = (6.8 - 0.701) / (6.8 - 2.2)
    checks = [
        dev <= LIQUID_CV_DEV_MAX_PCT,
        result.is_choked,
        result["flow_regime"] == "choked-cavitating",
        abs(result["cavitation_index"] - sigma_ref) / sigma_ref < 0.01,
        abs(result.required_kv / result.required_cv - KV_CV_RATIO) < 1e-6,
    ]
    return ScenarioResult(
        name="L2 - Sivi (su), ball valf, choking",
        service="liquid",
        passed=all(checks),
        detail=(
            f"Kv=program {result.required_kv:.3f}, analitik {kv_ref:.3f} (sapma %{dev:.3f}); "
            f"DeltaP_choked={dp_choked:.3f} bar, choked={result.is_choked}, "
            f"rejim={result['flow_regime']}, sigma={result['cavitation_index']:.3f}."
        ),
        required_kv=result.required_kv, reference_kv=kv_ref, deviation_pct=dev,
        is_choked=result.is_choked, valve_dn_mm=result.valve_dn_mm, regime=result["flow_regime"],
    )


def verify_liquid_flashing() -> ScenarioResult:
    """L3: Propane flashing service, HEM two-phase Cv self-consistency."""
    data = LiquidSizingInput(
        flow_m3h=50.0, inlet_pressure_bar_a=12.0, outlet_pressure_bar_a=2.0,
        density_kg_m3=500.0, vapor_pressure_bar_a=8.5, critical_pressure_bar_a=42.5,
        viscosity_pa_s=1.1e-4, fl=0.9, fd=1.0, temperature_c=25.0,
        specific_heat_j_kgk=2500.0, latent_heat_j_kg=425000.0, molecular_weight=44.1,
    )
    result = size_liquid_valve(data, valve_series=DEFAULT_VALVE_SERIES)
    flashing = result.get("flashing")
    self_consistent = False
    if flashing:
        rho_tp_check = 1.0 / (
            flashing["quality_x"] / flashing["rho_vapor_kg_m3"]
            + (1.0 - flashing["quality_x"]) / 500.0
        )
        mult_check = math.sqrt(500.0 / rho_tp_check)
        self_consistent = (
            _deviation_pct(flashing["rho_tp_kg_m3"], rho_tp_check) < 0.1
            and _deviation_pct(flashing["flashing_cv_multiplier"], mult_check) < 0.1
        )
    checks = [
        result["flow_regime"] == "flashing",
        flashing is not None,
        flashing is not None and 0.0 < flashing["quality_x"] < 1.0,
        flashing is not None and flashing["flashing_cv_multiplier"] > 1.0,
        self_consistent,
        "flashing" in result.warning.lower(),
    ]
    kv_flash = flashing["required_cv_flashing"] * KV_CV_RATIO if flashing else None
    return ScenarioResult(
        name="L3 - Sivi (propan), flashing (HEM)",
        service="liquid",
        passed=all(checks),
        detail=(
            f"rejim={result['flow_regime']} (P2=2.0 < Pv=8.5 bar); "
            f"flash orani={flashing['quality_x']:.4f}, iki fazli Cv carpani="
            f"{flashing['flashing_cv_multiplier']:.3f}; HEM tutarliligi={self_consistent}."
        ),
        required_kv=result.required_kv, reference_kv=kv_flash, deviation_pct=None,
        is_choked=result.is_choked, valve_dn_mm=result.valve_dn_mm, regime=result["flow_regime"],
    )


def verify_liquid_velocity() -> ScenarioResult:
    """L4: High-velocity subcritical water, pipe velocity and erosion checks."""
    data = LiquidSizingInput(
        flow_m3h=300.0, inlet_pressure_bar_a=20.0, outlet_pressure_bar_a=15.0,
        density_kg_m3=998.0, vapor_pressure_bar_a=0.023, critical_pressure_bar_a=220.64,
        viscosity_pa_s=8.9e-4, fl=0.9, fd=1.0,
        pipe_inlet_diameter_mm=100.0, pipe_outlet_diameter_mm=80.0,
    )
    result = size_liquid_valve(data, valve_series=DEFAULT_VALVE_SERIES)
    v_out_ref = 300.0 / 3600.0 / (math.pi * 0.04 ** 2)
    sigma_ref = (20.0 - 0.023) / (20.0 - 15.0)
    checks = [
        result["flow_regime"] == "subcritical",
        not result.is_choked,
        _deviation_pct(result["velocity"]["pipe_out_m_s"], v_out_ref) < 0.1,
        _deviation_pct(result["cavitation_index"], sigma_ref) < 0.01,
        len(result.warning) > 0,
    ]
    return ScenarioResult(
        name="L4 - Sivi (su), yuksek hiz / erozyon kontrolu",
        service="liquid",
        passed=all(checks),
        detail=(
            f"rejim={result['flow_regime']}; cikis hizi program "
            f"{result['velocity']['pipe_out_m_s']:.2f} m/s, analitik {v_out_ref:.2f} m/s; "
            f"sigma={result['cavitation_index']:.3f}; uyari: {result.warning[:80]}..."
        ),
        required_kv=result.required_kv, reference_kv=None, deviation_pct=None,
        is_choked=result.is_choked, valve_dn_mm=result.valve_dn_mm, regime=result["flow_regime"],
    )


def verify_gas_iec_anchor() -> ScenarioResult:
    """G1: IEC published gas example (CO2) reproduced by the wrapper."""
    q_actual_m3h = (38.0 / 36.0) * 3600.0
    flow_nm3h = q_actual_m3h / ((1.01325 / 6.8) * (433.15 / 273.15) * 0.988)
    anchor = cast(float, size_control_valve_g(
        T=433.0, MW=44.01, mu=1.4665e-4, gamma=1.30, Z=0.988,
        P1=680e3, P2=310e3, Q=q_actual_m3h / 3600.0,
        D1=0.08, D2=0.1, d=0.05, FL=0.85, Fd=0.42, xT=0.60,
    ))
    data = GasSizingInput(
        flow_nm3h=flow_nm3h, inlet_pressure_bar_a=6.8, outlet_pressure_bar_a=3.1,
        temperature_c=159.85, molecular_weight=44.01, specific_heat_ratio=1.30,
        viscosity_pa_s=1.4665e-4, z=0.988, fl=0.85, fd=0.42, xt=0.60,
        pipe_inlet_diameter_mm=80.0, pipe_outlet_diameter_mm=100.0,
    )
    result = size_gas_valve(data, valve_series=DEFAULT_VALVE_SERIES)
    t_k = 159.85 + 273.15
    d = result.valve_dn_mm / 1000.0
    ref = cast(float, size_control_valve_g(
        T=t_k, MW=44.01, mu=1.4665e-4, gamma=1.30, Z=0.988,
        P1=680e3, P2=310e3, Q=q_actual_m3h / 3600.0,
        D1=0.08, D2=0.1, d=d, FL=0.85, Fd=0.42, xT=0.60,
    ))
    dev = _deviation_pct(result.required_kv, ref)
    x = result["pressure_drop_ratio_x"]
    xtp = result["xtp"] if result["xtp"] is not None else 0.60
    choked_self_consistent = result.is_choked == (x >= result["fk"] * xtp)
    checks = [
        _deviation_pct(anchor, 72.5866454539105) < 1e-4,
        dev <= GAS_ANCHOR_DEV_MAX_PCT,
        choked_self_consistent,
        2.0 / 3.0 <= result["expansion_factor_y"] <= 1.0,
    ]
    return ScenarioResult(
        name="G1 - Gaz (CO2), IEC yayinli ornek",
        service="gas",
        passed=all(checks),
        detail=(
            f"Kv=program {result.required_kv:.4f}, IEC referans {ref:.4f} (sapma %{dev:.4f}); "
            f"capa degeri 72.5866 dogrulandi; x={x:.4f}, x_choked={result['x_choked']:.4f}, "
            f"Y={result['expansion_factor_y']:.4f}, choked={result.is_choked} "
            f"(kendiyle tutarli={choked_self_consistent})."
        ),
        required_kv=result.required_kv, reference_kv=ref, deviation_pct=dev,
        is_choked=result.is_choked, valve_dn_mm=result.valve_dn_mm, regime="cikisa yakin",
    )


def verify_gas_choked_analytic() -> ScenarioResult:
    """G2: Air in choke, matches independent analytic IEC choked Kv."""
    data = GasSizingInput(
        flow_nm3h=10000.0, inlet_pressure_bar_a=7.0, outlet_pressure_bar_a=1.5,
        temperature_c=20.0, molecular_weight=28.97, specific_heat_ratio=1.4,
        viscosity_pa_s=1.8e-5, z=1.0, fl=0.9, fd=1.0, xt=0.7,
    )
    result = size_gas_valve(data, valve_series=DEFAULT_VALVE_SERIES)
    kv_ref, x, x_choked, y, choked = _gas_kv_reference(10000.0, 7.0, 1.5, 20.0, 28.97, 1.4, 1.0, 0.7)
    dev = _deviation_pct(result.required_kv, kv_ref)
    checks = [
        dev <= GAS_ANALYTIC_DEV_MAX_PCT,
        result.is_choked,
        choked,
        abs(result["expansion_factor_y"] - 2.0 / 3.0) < 1e-6,
        x > x_choked,
    ]
    return ScenarioResult(
        name="G2 - Gaz (hava), choking (analitik IEC)",
        service="gas",
        passed=all(checks),
        detail=(
            f"Kv=program {result.required_kv:.4f}, analitik {kv_ref:.4f} (sapma %{dev:.3f}); "
            f"x={x:.4f} > x_choked={x_choked:.4f}, Y={y:.4f} (alt sinir 0.667), "
            f"choked={result.is_choked}."
        ),
        required_kv=result.required_kv, reference_kv=kv_ref, deviation_pct=dev,
        is_choked=result.is_choked, valve_dn_mm=result.valve_dn_mm, regime="choked",
    )


def verify_gas_energy_blend() -> ScenarioResult:
    """G3: H2-NG %20 blend via CoolProp mixture, Cv monotonicity."""
    rows = GAS_PRESETS["H2-NG %20 (blend)"]["components"]
    summary = evaluate_gas_mixture(rows, "molar", 10.0, 20.0)
    assert summary.z is not None and summary.specific_heat_ratio is not None
    assert summary.viscosity_pa_s is not None
    mw, z, k, mu = (
        summary.average_molecular_weight, summary.z, summary.specific_heat_ratio, summary.viscosity_pa_s,
    )
    checks_props = [
        14.0 <= mw <= 16.0,
        z is not None and 0.85 < z <= 1.0,
        k is not None and 1.30 <= k <= 1.42,
        mu is not None and mu > 0.0,
    ]

    def _run(flow: float):
        return size_gas_valve(
            GasSizingInput(
                flow_nm3h=flow, inlet_pressure_bar_a=10.0, outlet_pressure_bar_a=7.0,
                temperature_c=20.0, molecular_weight=mw, specific_heat_ratio=k,
                viscosity_pa_s=mu, z=z, fl=0.85, fd=1.0, xt=0.69,
            ),
            valve_series=DEFAULT_VALVE_SERIES,
        )

    low, high = _run(20000.0), _run(30000.0)
    d = low.valve_dn_mm / 1000.0
    q_actual = 20000.0 * (NORMAL_P_BAR / 10.0) * (293.15 / NORMAL_T_K) * z
    ref = cast(float, size_control_valve_g(
        T=293.15, MW=mw, mu=mu, gamma=k, Z=z, P1=10e5, P2=7e5,
        Q=q_actual / 3600.0, D1=d, D2=d, d=d, FL=0.85, Fd=1.0, xT=0.69,
    ))
    dev = _deviation_pct(low.required_kv, ref)
    checks = [
        *checks_props,
        high.required_cv > low.required_cv,
        dev <= GAS_ANCHOR_DEV_MAX_PCT,
    ]
    return ScenarioResult(
        name="G3 - Enerji gazi (H2-NG %20, CoolProp)",
        service="gas",
        passed=all(checks),
        detail=(
            f"MW={mw:.2f} g/mol, Z={z:.3f}, k={k:.3f}; Kv=program {low.required_kv:.4f}, "
            f"referans {ref:.4f} (sapma %{dev:.3f}); Cv(20k)={low.required_cv:.2f} < "
            f"Cv(30k)={high.required_cv:.2f} (monoton)."
        ),
        required_kv=low.required_kv, reference_kv=ref, deviation_pct=dev,
        is_choked=low.is_choked, valve_dn_mm=low.valve_dn_mm, regime="subsonic",
    )


def verify_steam_superheated() -> ScenarioResult:
    """S1: Superheated steam, Kv via CoolProp density vs analytic IEC."""
    data = SteamSizingInput(
        flow_kg_h=5000.0, inlet_pressure_bar_a=12.0, outlet_pressure_bar_a=8.0,
        temperature_c=220.0, specific_heat_ratio=1.30, z=1.0, xt=0.72, fl=0.9, fd=1.0,
    )
    result = size_steam_valve(data, valve_series=DEFAULT_VALVE_SERIES)
    rho = CP.PropsSI("D", "P", 12e5, "T", 493.15, "Water")
    q_actual = 5000.0 / rho
    kv_ref, x, x_choked, y, choked = _gas_kv_from_actual(q_actual, 12.0, 8.0, 220.0, 18.015, 1.30, 1.0, 0.72)
    dev = _deviation_pct(result.required_kv, kv_ref)
    checks = [
        dev <= STEAM_DEV_MAX_PCT,
        not result.is_choked,
        not choked,
        result.required_kv > 0.0,
    ]
    return ScenarioResult(
        name="S1 - Kizgin buhar 12->8 bar(a)",
        service="steam",
        passed=all(checks),
        detail=(
            f"CoolProp yogunluk={rho:.3f} kg/m3; Kv=program {result.required_kv:.4f}, "
            f"analitik {kv_ref:.4f} (sapma %{dev:.3f}); x={x:.3f} < x_choked={x_choked:.3f}, "
            f"choked={result.is_choked}."
        ),
        required_kv=result.required_kv, reference_kv=kv_ref, deviation_pct=dev,
        is_choked=result.is_choked, valve_dn_mm=result.valve_dn_mm, regime="subsonic",
    )


def verify_steam_near_saturated() -> ScenarioResult:
    """S2: Near-saturated steam, real-gas density consistency."""
    data = SteamSizingInput(
        flow_kg_h=8000.0, inlet_pressure_bar_a=6.0, outlet_pressure_bar_a=3.0,
        temperature_c=165.0, specific_heat_ratio=1.30, z=1.0, xt=0.72, fl=0.9, fd=1.0,
    )
    result = size_steam_valve(data, valve_series=DEFAULT_VALVE_SERIES)
    rho = CP.PropsSI("D", "P", 6e5, "T", 438.15, "Water")
    q_actual = 8000.0 / rho
    kv_ref, x, x_choked, y, choked = _gas_kv_from_actual(q_actual, 6.0, 3.0, 165.0, 18.015, 1.30, 1.0, 0.72)
    dev = _deviation_pct(result.required_kv, kv_ref)
    checks = [
        dev <= STEAM_DEV_MAX_PCT,
        not result.is_choked,
        result.required_kv > 0.0,
    ]
    return ScenarioResult(
        name="S2 - Doygunluga yakin buhar 6->3 bar(a)",
        service="steam",
        passed=all(checks),
        detail=(
            f"CoolProp yogunluk={rho:.3f} kg/m3; Kv=program {result.required_kv:.4f}, "
            f"analitik {kv_ref:.4f} (sapma %{dev:.3f}); x={x:.3f} < x_choked={x_choked:.3f}, "
            f"choked={result.is_choked}."
        ),
        required_kv=result.required_kv, reference_kv=kv_ref, deviation_pct=dev,
        is_choked=result.is_choked, valve_dn_mm=result.valve_dn_mm, regime="subsonic",
    )


def verify_unit_equivalence() -> ScenarioResult:
    """X1: SI (bar/m3h/C) vs US (psi/gpm/F) inputs yield identical Cv."""
    si = LiquidSizingInput(
        flow_m3h=360.0, inlet_pressure_bar_a=6.8, outlet_pressure_bar_a=2.2,
        density_kg_m3=998.0, vapor_pressure_bar_a=0.023, critical_pressure_bar_a=220.64,
        viscosity_pa_s=8.9e-4, fl=0.9, fd=1.0, temperature_c=25.0,
    )
    us = LiquidSizingInput(
        flow_m3h=liquid_flow_to_m3h(liquid_flow_from_m3h(360.0, "gpm"), "gpm"),
        inlet_pressure_bar_a=pressure_to_bar_a(pressure_from_bar_a(6.8, "psi_a"), "psi_a"),
        outlet_pressure_bar_a=pressure_to_bar_a(pressure_from_bar_a(2.2, "psi_a"), "psi_a"),
        density_kg_m3=998.0, vapor_pressure_bar_a=0.023, critical_pressure_bar_a=220.64,
        viscosity_pa_s=8.9e-4, fl=0.9, fd=1.0,
        temperature_c=temperature_to_c(temperature_from_c(25.0, "F"), "F"),
    )
    r_si = size_liquid_valve(si, valve_series=DEFAULT_VALVE_SERIES)
    r_us = size_liquid_valve(us, valve_series=DEFAULT_VALVE_SERIES)
    rel = _deviation_pct(r_si.required_cv, r_us.required_cv) / 100.0
    checks = [rel < 1e-9, r_si.valve_dn_mm == r_us.valve_dn_mm]
    return ScenarioResult(
        name="X1 - Birim tutarliligi (SI <-> US)",
        service="liquid",
        passed=all(checks),
        detail=(
            f"Cv(SI)={r_si.required_cv:.6f}, Cv(US)={r_us.required_cv:.6f}, "
            f"bagil fark={rel:.2e}; secilen DN ayni (DN{r_si.valve_dn_mm})."
        ),
        required_kv=r_si.required_kv, reference_kv=r_us.required_kv, deviation_pct=rel * 100.0,
        is_choked=r_si.is_choked, valve_dn_mm=r_si.valve_dn_mm, regime=r_si["flow_regime"],
    )


def verify_design_margin() -> ScenarioResult:
    """X2: 15% design margin scales required Cv and grows the selected size."""
    def _run(margin: float):
        return size_liquid_valve(
            LiquidSizingInput(
                flow_m3h=320.0, inlet_pressure_bar_a=6.8, outlet_pressure_bar_a=2.2,
                density_kg_m3=965.4, vapor_pressure_bar_a=0.701, critical_pressure_bar_a=221.2,
                viscosity_pa_s=3.1472e-4, fl=0.9, fd=0.46,
            ),
            valve_series=DEFAULT_VALVE_SERIES, design_margin_pct=margin,
        )

    base, marg = _run(0.0), _run(15.0)
    rel = _deviation_pct(marg["required_cv_with_margin"], base.required_cv * 1.15) / 100.0
    checks = [
        rel < 1e-9,
        abs(marg.required_cv - base.required_cv) / base.required_cv < 1e-9,
        marg.valve_dn_mm > base.valve_dn_mm,
        base.opening_percent > 85.0,
        0.0 < marg.opening_percent <= 85.0,
    ]
    return ScenarioResult(
        name="X2 - Tasarim marji %15",
        service="liquid",
        passed=all(checks),
        detail=(
            f"marjsiz Cv={base.required_cv:.3f} (DN{base.valve_dn_mm}, aciklik %{base.opening_percent:.1f}); "
            f"%15 marjli Cv_margin={marg['required_cv_with_margin']:.3f} (DN{marg.valve_dn_mm}, "
            f"aciklik %{marg.opening_percent:.1f}); carpan hatasi={rel:.2e}."
        ),
        required_kv=base.required_kv, reference_kv=marg.required_kv, deviation_pct=rel * 100.0,
        is_choked=base.is_choked, valve_dn_mm=marg.valve_dn_mm, regime=base["flow_regime"],
    )


def verify_vendor_catalog() -> ScenarioResult:
    """X3: Fisher globe catalog selection and coefficients honored."""
    definition = get_vendor_definition("fisher_globe_eqpct")
    assert definition.fl is not None and definition.fd is not None and definition.xt is not None
    data = GasSizingInput(
        flow_nm3h=120000.0, inlet_pressure_bar_a=15.0, outlet_pressure_bar_a=10.0,
        temperature_c=40.0, molecular_weight=17.3, specific_heat_ratio=1.31,
        viscosity_pa_s=1.1e-5, z=0.95, fl=definition.fl, fd=definition.fd, xt=definition.xt,
    )
    result = size_gas_valve(
        data, valve_series=list(definition.sizes),
        valve_meta={"vendor": definition.vendor, "family": definition.family, "style": definition.style},
    )
    d = result.valve_dn_mm / 1000.0
    q_actual = 120000.0 * (NORMAL_P_BAR / 15.0) * (313.15 / NORMAL_T_K) * 0.95
    ref = cast(float, size_control_valve_g(
        T=313.15, MW=17.3, mu=1.1e-5, gamma=1.31, Z=0.95, P1=15e5, P2=10e5,
        Q=q_actual / 3600.0, D1=d, D2=d, d=d, FL=definition.fl, Fd=definition.fd, xT=definition.xt,
    ))
    dev = _deviation_pct(result.required_kv, ref)
    catalog_dns = {v.dn_mm for v in definition.sizes}
    checks = [
        result.valve_meta.get("vendor") == "Emerson Fisher",
        result.valve_dn_mm in catalog_dns,
        result.rated_cv >= result.required_cv,
        dev <= GAS_ANCHOR_DEV_MAX_PCT,
        len(result.equations) > 0,
        len(result.method_panel) > 0,
    ]
    return ScenarioResult(
        name="X3 - Fisher vendor katalogu secimi",
        service="gas",
        passed=all(checks),
        detail=(
            f"secilen DN{result.valve_dn_mm} ({result.valve_inch}), rated Cv={result.rated_cv:.1f} "
            f">= gerekli {result.required_cv:.2f}; FL={definition.fl}, xT={definition.xt}; "
            f"Kv=program {result.required_kv:.4f}, referans {ref:.4f} (sapma %{dev:.4f})."
        ),
        required_kv=result.required_kv, reference_kv=ref, deviation_pct=dev,
        is_choked=result.is_choked, valve_dn_mm=result.valve_dn_mm, regime="subsonic",
    )


SCENARIO_RUNNERS = [
    verify_liquid_subcritical,
    verify_liquid_choked,
    verify_liquid_flashing,
    verify_liquid_velocity,
    verify_gas_iec_anchor,
    verify_gas_choked_analytic,
    verify_gas_energy_blend,
    verify_steam_superheated,
    verify_steam_near_saturated,
    verify_unit_equivalence,
    verify_design_margin,
    verify_vendor_catalog,
]


def run_scenario_verification() -> list[ScenarioResult]:
    """Run all verification scenarios and return the verdicts."""
    return [runner() for runner in SCENARIO_RUNNERS]


def _print_report(results: list[ScenarioResult]) -> None:
    header = f"{'Senaryo':<44}{'Servis':<8}{'Kv':>10}{'Ref':>10}{'Sapma%':>9}{'Chk':>6}{'DN':>6}{'KARAR':>7}"
    print(header)
    print("-" * len(header))
    for r in results:
        kv = f"{r.required_kv:.3f}" if r.required_kv else "-"
        ref = f"{r.reference_kv:.3f}" if r.reference_kv is not None else "-"
        dev = f"{r.deviation_pct:.4f}" if r.deviation_pct is not None else "-"
        chk = "EVET" if r.is_choked else "HAYIR"
        dn = str(r.valve_dn_mm) if r.valve_dn_mm else "-"
        verdict = "PASS" if r.passed else "FAIL"
        print(f"{r.name:<44}{r.service:<8}{kv:>10}{ref:>10}{dev:>9}{chk:>6}{dn:>6}{verdict:>7}")
    print()
    for r in results:
        print(f"[{'OK' if r.passed else 'HATA'}] {r.name}")
        print(f"      {r.detail}")
    print()


def main() -> int:
    """Run verification and print the evaluation report."""
    results = run_scenario_verification()
    _print_report(results)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"OZET: {passed}/{total} senaryo GECTI.")
    if passed == total:
        print("DEGERLENDIRME: Tum hesaplamalar bagimsiz referanslarla uyumlu; motor dogru calisiyor.")
    else:
        print("DEGERLENDIRME: Bir veya daha fazla senaryo dogrulanamadi; yukaridaki HATA kayitlarini inceleyin.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
