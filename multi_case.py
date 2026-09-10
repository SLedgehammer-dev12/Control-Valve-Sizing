"""Multi-case operating conditions (Min, Normal, Max) control valve sizing engine.

Evaluates valve candidate series across simultaneous operating regimes to verify:
- Minimum controllable flow (opening >= 10% to prevent wire-drawing and seat erosion)
- Normal duty point controllability (opening between 40% and 75%)
- Maximum upset / design capacity (opening <= 85-90% to maintain control margin)
- Process turndown ratio against valve rangeability
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from valve_sizing import (
    DEFAULT_RANGEABILITY,
    DEFAULT_VALVE_SERIES,
    GasSizingInput,
    LiquidSizingInput,
    SteamSizingInput,
    ValveSize,
    size_gas_valve,
    size_liquid_valve,
    size_steam_valve,
)


@dataclass(frozen=True)
class OperatingCase:
    """Operating conditions for a single operational state."""

    name: str
    flow: float
    p1_bar_a: float
    p2_bar_a: float
    temperature_c: float
    extra_props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseSizingDetail:
    """Detailed sizing metrics for an operating case on a specific valve."""

    name: str
    flow: float
    p1_bar_a: float
    p2_bar_a: float
    temperature_c: float
    required_cv: float
    opening_pct: float
    is_choked: bool
    status: str
    warnings: list[str]


@dataclass(frozen=True)
class MultiCaseCandidate:
    """Candidate valve evaluation across all operating cases."""

    valve: ValveSize
    case_details: dict[str, CaseSizingDetail]
    opening_min_pct: float
    opening_norm_pct: float
    opening_max_pct: float
    is_acceptable: bool
    is_recommended: bool
    status_label: str
    evaluation_notes: list[str]


@dataclass(frozen=True)
class MultiCaseAnalysis:
    """Comprehensive multi-case sizing analysis result."""

    service: str
    cases: list[OperatingCase]
    turndown_ratio: float
    recommended: MultiCaseCandidate | None
    candidates: list[MultiCaseCandidate]
    overall_summary: str
    warnings: list[str]


def _build_case_input(
    service: str,
    case: OperatingCase,
    base_fluid_data: dict[str, Any],
    pipe_inlet_mm: float | None,
    pipe_outlet_mm: float | None,
) -> Any:
    fl = float(base_fluid_data.get("fl", 0.9))
    fd = float(base_fluid_data.get("fd", 1.0))
    xt = float(base_fluid_data.get("xt", 0.7))

    if service == "liquid":
        return LiquidSizingInput(
            flow_m3h=case.flow,
            inlet_pressure_bar_a=case.p1_bar_a,
            outlet_pressure_bar_a=case.p2_bar_a,
            density_kg_m3=float(base_fluid_data.get("density_kg_m3", 998.0)),
            vapor_pressure_bar_a=float(base_fluid_data.get("vapor_pressure_bar_a", 0.023)),
            critical_pressure_bar_a=float(base_fluid_data.get("critical_pressure_bar_a", 220.64)),
            viscosity_pa_s=float(base_fluid_data.get("viscosity_pa_s", 0.001)),
            fl=fl,
            fd=fd,
            pipe_inlet_diameter_mm=pipe_inlet_mm,
            pipe_outlet_diameter_mm=pipe_outlet_mm,
            temperature_c=case.temperature_c,
            specific_heat_j_kgk=float(base_fluid_data.get("specific_heat_j_kgk", 4186.0)),
            latent_heat_j_kg=float(base_fluid_data.get("latent_heat_j_kg", 2257000.0)),
            molecular_weight=float(base_fluid_data.get("molecular_weight", 18.015)),
        )

    if service == "gas":
        return GasSizingInput(
            flow_nm3h=case.flow,
            inlet_pressure_bar_a=case.p1_bar_a,
            outlet_pressure_bar_a=case.p2_bar_a,
            temperature_c=case.temperature_c,
            molecular_weight=float(base_fluid_data.get("molecular_weight", 28.96)),
            specific_heat_ratio=float(base_fluid_data.get("specific_heat_ratio", 1.40)),
            viscosity_pa_s=float(base_fluid_data.get("viscosity_pa_s", 1.8e-5)),
            z=float(base_fluid_data.get("z", 1.0)),
            fl=fl,
            fd=fd,
            xt=xt,
            pipe_inlet_diameter_mm=pipe_inlet_mm,
            pipe_outlet_diameter_mm=pipe_outlet_mm,
        )

    if service == "steam":
        return SteamSizingInput(
            flow_kg_h=case.flow,
            inlet_pressure_bar_a=case.p1_bar_a,
            outlet_pressure_bar_a=case.p2_bar_a,
            temperature_c=case.temperature_c,
            specific_heat_ratio=float(base_fluid_data.get("specific_heat_ratio", 1.30)),
            z=float(base_fluid_data.get("z", 1.0)),
            xt=xt,
            fp=float(base_fluid_data.get("fp", 1.0)),
            fl=fl,
            fd=fd,
            pipe_inlet_diameter_mm=pipe_inlet_mm,
            pipe_outlet_diameter_mm=pipe_outlet_mm,
        )

    raise ValueError(f"Desteklenmeyen servis tipi: {service}")


def _evaluate_single_case(
    service: str,
    case_input: Any,
    valve: ValveSize,
    flow_characteristic: str,
    rangeability: float,
) -> Any:
    if service == "liquid":
        return size_liquid_valve(
            case_input,
            valve_series=[valve],
            flow_characteristic=flow_characteristic,
            rangeability=rangeability,
        )
    if service == "gas":
        return size_gas_valve(
            case_input,
            valve_series=[valve],
            flow_characteristic=flow_characteristic,
            rangeability=rangeability,
        )
    return size_steam_valve(
        case_input,
        valve_series=[valve],
        flow_characteristic=flow_characteristic,
        rangeability=rangeability,
    )


def size_multicase(
    service: str,
    cases: list[OperatingCase],
    base_fluid_data: dict[str, Any],
    valve_series: list[ValveSize] | None = None,
    flow_characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
    pipe_inlet_mm: float | None = None,
    pipe_outlet_mm: float | None = None,
) -> MultiCaseAnalysis:
    """Size and evaluate control valve candidates across multi-case operating conditions."""
    if not cases:
        raise ValueError("En az bir calisma durumu (case) tanimlanmalidir.")

    flows = [c.flow for c in cases if c.flow > 0]
    if not flows:
        raise ValueError("Calisma durumlari icin gecerli pozitif debi bulunamadi.")

    q_min = min(flows)
    q_max = max(flows)
    turndown = q_max / q_min if q_min > 0 else 1.0

    global_warnings: list[str] = []
    if turndown > rangeability:
        global_warnings.append(
            f"Turndown orani ({turndown:.1f}:1) vana dinamik kontrol araligini ({rangeability:.0f}:1) asiyor!"
        )

    series = valve_series if valve_series is not None else DEFAULT_VALVE_SERIES
    candidates: list[MultiCaseCandidate] = []

    for valve in series:
        case_details: dict[str, CaseSizingDetail] = {}
        candidate_notes: list[str] = []

        for case in cases:
            case_inp = _build_case_input(service, case, base_fluid_data, pipe_inlet_mm, pipe_outlet_mm)
            res = _evaluate_single_case(service, case_inp, valve, flow_characteristic, rangeability)

            c_warnings: list[str] = []
            if res.warning:
                c_warnings.append(res.warning)

            status = "Normal"
            if res.opening_percent < 10.0:
                status = "Kritik Dusuk Aciklik"
                c_warnings.append(f"%{res.opening_percent:.1f} < %10 aciklik: Sit asinmasi ve titresim riski.")
            elif res.opening_percent > 85.0:
                status = "Kritik Yuksek Aciklik"
                c_warnings.append(f"%{res.opening_percent:.1f} > %85 aciklik: Tepe marji yetersiz.")

            case_details[case.name] = CaseSizingDetail(
                name=case.name,
                flow=case.flow,
                p1_bar_a=case.p1_bar_a,
                p2_bar_a=case.p2_bar_a,
                temperature_c=case.temperature_c,
                required_cv=res.required_cv,
                opening_pct=res.opening_percent,
                is_choked=res.is_choked,
                status=status,
                warnings=c_warnings,
            )

        min_case = case_details.get("Min") or min(case_details.values(), key=lambda d: d.flow)
        norm_case = case_details.get("Normal") or sorted(case_details.values(), key=lambda d: d.flow)[len(case_details) // 2]
        max_case = case_details.get("Max") or max(case_details.values(), key=lambda d: d.flow)

        h_min = min_case.opening_pct
        h_norm = norm_case.opening_pct
        h_max = max_case.opening_pct

        is_perfect = (h_min >= 10.0) and (40.0 <= h_norm <= 78.0) and (h_max <= 85.0)
        is_acceptable = (h_min >= 5.0) and (h_max <= 92.0)

        if is_perfect:
            status_label = "Mukemmel"
            candidate_notes.append("Tum calisma durumlarinda ideal kontrol araliginda.")
        elif is_acceptable:
            status_label = "Kabul Edilebilir"
            if h_min < 10.0:
                candidate_notes.append(f"Min akis acikligi %{h_min:.1f} dusuk marjda.")
            if h_max > 85.0:
                candidate_notes.append(f"Max akis acikligi %{h_max:.1f} yuksek marjda.")
        else:
            status_label = "Uygun Degil"
            if h_min < 5.0:
                candidate_notes.append(f"Min akista vana cok buyuk (%{h_min:.1f} < %5).")
            if h_max > 92.0:
                candidate_notes.append(f"Max akista vana yetersiz (%{h_max:.1f} > %92).")

        candidates.append(
            MultiCaseCandidate(
                valve=valve,
                case_details=case_details,
                opening_min_pct=h_min,
                opening_norm_pct=h_norm,
                opening_max_pct=h_max,
                is_acceptable=is_acceptable,
                is_recommended=False,
                status_label=status_label,
                evaluation_notes=candidate_notes,
            )
        )

    recommended_candidate: MultiCaseCandidate | None = None
    acceptable_candidates = [c for c in candidates if c.is_acceptable]

    if acceptable_candidates:
        perfect_candidates = [c for c in acceptable_candidates if c.status_label == "Mukemmel"]
        if perfect_candidates:
            recommended_candidate = min(perfect_candidates, key=lambda c: abs(c.opening_norm_pct - 60.0))
        else:
            recommended_candidate = min(acceptable_candidates, key=lambda c: abs(c.opening_norm_pct - 60.0))

    final_candidates: list[MultiCaseCandidate] = []
    for c in candidates:
        is_rec = recommended_candidate is not None and c.valve.dn_mm == recommended_candidate.valve.dn_mm
        final_candidates.append(
            MultiCaseCandidate(
                valve=c.valve,
                case_details=c.case_details,
                opening_min_pct=c.opening_min_pct,
                opening_norm_pct=c.opening_norm_pct,
                opening_max_pct=c.opening_max_pct,
                is_acceptable=c.is_acceptable,
                is_recommended=is_rec,
                status_label=c.status_label,
                evaluation_notes=c.evaluation_notes,
            )
        )

    rec_final = next((c for c in final_candidates if c.is_recommended), None)

    if rec_final:
        summary = (
            f"Onerilen Vana: DN{rec_final.valve.dn_mm} ({rec_final.valve.inch}), Rated Cv: {rec_final.valve.cv_rated}. "
            f"Acikliklar: Min %{rec_final.opening_min_pct:.1f}, "
            f"Normal %{rec_final.opening_norm_pct:.1f}, "
            f"Max %{rec_final.opening_max_pct:.1f}."
        )
    else:
        summary = "Mevcut vana serisinde tum calisma durumlarini ayni anda karsilayan uygun bir vana bulunamadi."

    return MultiCaseAnalysis(
        service=service,
        cases=cases,
        turndown_ratio=turndown,
        recommended=rec_final,
        candidates=final_candidates,
        overall_summary=summary,
        warnings=global_warnings,
    )
