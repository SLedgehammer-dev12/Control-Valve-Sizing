"""Control valve sizing engine.

Implements IEC 60534 / ISA-based Cv/Kv calculations for liquid, gas, and steam
services.  Exposes dataclass input types (LiquidSizingInput, GasSizingInput,
SteamSizingInput) and sizing functions (size_liquid_valve, size_gas_valve,
size_steam_valve), plus unit conversions (cv_to_kv, kv_to_cv).
"""

from __future__ import annotations

__version__ = "3.3.0"

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from typing import Any, cast

from fluids.control_valve import size_control_valve_g, size_control_valve_l

from trim_guidance import recommend_trim
from two_phase import cavitation_index as _iec_cavitation_index
from two_phase import (
    flash_fraction,
    flashing_cv_estimate,
    two_phase_density_homogeneous,
    vapor_density_ideal_gas,
)
from units import (
    AIR_K,
    AIR_MW,
    BAR_TO_PSI,
    CELSIUS_TO_RANKINE,
    CV_TO_KV,
    FF_A,
    FF_B,
    KV_TO_CV,
    M3H_TO_GPM,
    NM3H_TO_SCFH,
    NORMAL_P_BAR,
    NORMAL_T_K,
)
from valve_selection import build_valve_spec

logger = logging.getLogger(__name__)


SOURCE_LIBRARY = {
    "iec_scope": {
        "title": "IEC 60534-2-1",
        "url": "https://webstore.iec.ch/en/publication/2461",
        "note": "Sizing equations for fluid flow under installed conditions.",
    },
    "isa_committee": {
        "title": "ISA75.01",
        "url": "https://www.isa.org/standards-and-publications/isa-standards/isa-standards-committees/isa75-01",
        "note": "ISA control valve sizing equations committee reference.",
    },
    "primer_liquid": {
        "title": "ISA Control Valve Primer Chapter 5",
        "url": "https://www.isa.org/getmedia/c37b8eb0-dbf9-4cb8-a29a-aac88db297a0/Baumann-ControlValvePrimer_Chapter5.pdf",
        "note": "Simplified liquid, gas and steam sizing equations; choked-flow checks.",
    },
    "fisher_choked": {
        "title": "Understanding Choked Flow in Fisher Valves",
        "url": "https://www.documentation.emersonprocess.com/intradoc-cgi/groups/public/documents/bulletins/d104173x012.pdf",
        "note": "FL, XT and FF guidance. Includes FF correlation per IEC 60534-2-1.",
    },
    "fisher_handbook": {
        "title": "Emerson Fisher Control Valve Handbook",
        "url": "https://stage.www.emerson.com/content/dam/emerson/en/final-control-fctl/isolation-valves/documents/control-valve-handbook-en-3661206.pdf",
        "note": "Representative sizing coefficients for globe and rotary valves.",
    },
}


@dataclass(frozen=True)
class ValveSize:
    """A single valve size with rated Cv."""
    dn_mm: int
    inch: str
    cv_rated: float


@dataclass(frozen=True)
class LiquidSizingInput:
    """Input parameters for liquid control valve sizing."""
    flow_m3h: float
    inlet_pressure_bar_a: float
    outlet_pressure_bar_a: float
    density_kg_m3: float
    vapor_pressure_bar_a: float
    critical_pressure_bar_a: float
    viscosity_pa_s: float
    fl: float
    fd: float = 1.0
    pipe_inlet_diameter_mm: float | None = None
    pipe_outlet_diameter_mm: float | None = None
    temperature_c: float = 25.0
    specific_heat_j_kgk: float = 4186.0
    latent_heat_j_kg: float = 2257000.0
    molecular_weight: float = 18.015


@dataclass(frozen=True)
class GasSizingInput:
    """Input parameters for gas control valve sizing."""
    flow_nm3h: float
    inlet_pressure_bar_a: float
    outlet_pressure_bar_a: float
    temperature_c: float
    molecular_weight: float
    specific_heat_ratio: float
    viscosity_pa_s: float
    z: float = 1.0
    fl: float = 0.9
    fd: float = 1.0
    xt: float = 0.7
    pipe_inlet_diameter_mm: float | None = None
    pipe_outlet_diameter_mm: float | None = None


@dataclass(frozen=True)
class SteamSizingInput:
    """Input parameters for steam control valve sizing."""
    flow_kg_h: float
    inlet_pressure_bar_a: float
    outlet_pressure_bar_a: float
    temperature_c: float
    specific_heat_ratio: float = 1.30
    z: float = 1.0
    xt: float = 0.72
    fp: float = 1.0
    fl: float = 0.9
    fd: float = 1.0
    pipe_inlet_diameter_mm: float | None = None
    pipe_outlet_diameter_mm: float | None = None


@dataclass(frozen=True)
class SizingResult:
    """Result of a control valve sizing calculation.

    Core fields are typed attributes; service-specific values are in `extra`.
    Supports dict-style subscript access for backward compatibility.
    """
    service: str
    required_cv: float
    required_kv: float
    valve_dn_mm: int
    valve_inch: str
    rated_cv: float
    rated_kv: float
    delta_p_bar: float
    is_choked: bool
    warning: str
    design_margin_pct: float = 0.0
    opening_percent: float = 0.0
    cv_ratio: float = 0.0
    rangeability_min_cv: float = 0.0
    rangeability_ok: bool = True
    valve_meta: dict = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    equations: list[str] = field(default_factory=list)
    method_panel: list[str] = field(default_factory=list)
    intermediate_values: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            return self.extra[key]

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


DEFAULT_VALVE_SERIES = [
    ValveSize(15, '1/2"', 4.0),
    ValveSize(20, '3/4"', 7.0),
    ValveSize(25, '1"', 12.0),
    ValveSize(32, '1 1/4"', 20.0),
    ValveSize(40, '1 1/2"', 30.0),
    ValveSize(50, '2"', 48.0),
    ValveSize(65, '2 1/2"', 75.0),
    ValveSize(80, '3"', 115.0),
    ValveSize(100, '4"', 180.0),
    ValveSize(150, '6"', 360.0),
    ValveSize(200, '8"', 600.0),
]


def _require_positive(name: str, value: float) -> float:
    value = float(value)
    if value <= 0:
        logger.warning("Validation failed: %s = %s (must be > 0)", name, value)
        raise ValueError(f"{name} 0'dan buyuk olmalidir.")
    return value


def _validate_pressure_drop(p1: float, p2: float) -> float:
    p1 = float(p1)
    p2 = float(p2)
    if p1 <= p2:
        raise ValueError("Giris basinci cikis basincindan buyuk olmalidir.")
    return p1 - p2


def cv_to_kv(cv: float) -> float:
    """Convert Cv (US gallons/min) to Kv (m³/h)."""
    return float(cv) * CV_TO_KV


def kv_to_cv(kv: float) -> float:
    """Convert Kv (m³/h) to Cv (US gallons/min)."""
    return float(kv) * KV_TO_CV


FLOW_CHARACTERISTICS = ("linear", "equal_percentage")

DEFAULT_RANGEABILITY = 50.0


def estimate_opening(
    required_cv: float,
    rated_cv: float,
    characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
) -> float:
    """Estimate valve opening fraction (0-1) from the inherent characteristic.

    linear: opening = Cv_req/Cv_rated
    equal-percentage: Cv(theta) = Cv_rated * R^(theta-1), so theta is obtained
    by inverting the characteristic. Values are clamped to [0, 1].
    """
    if rated_cv <= 0 or required_cv <= 0:
        return 0.0
    ratio = min(required_cv / rated_cv, 1.0)
    if characteristic == "linear":
        return ratio
    if characteristic == "equal_percentage" and rangeability > 1.0:
        opening = 1.0 + math.log(max(ratio, 1e-9)) / math.log(rangeability)
        return max(0.0, min(opening, 1.0))
    return ratio


def estimate_min_controllable_cv(
    rated_cv: float,
    characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
) -> float:
    """Return the minimum controllable Cv for a given inherent characteristic.

    equal-percentage: rated / rangeability (Cv(R) at ~0% travel).
    linear: 1% of rated Cv (typical positioner/actuator resolution limit).
    """
    if characteristic == "linear":
        return rated_cv * 0.01
    if rangeability > 1.0:
        return rated_cv / rangeability
    return rated_cv


LIQUID_VELOCITY_ADVISORY_M_S = 6.0
LIQUID_VELOCITY_LIMIT_M_S = 8.0
GAS_MACH_ADVISORY = 0.3
GAS_MACH_LIMIT = 0.5
API_14E_C_CONTINUOUS_SI = 122.0
API_14E_C_INTERMITTENT_SI = 152.0


def pipe_velocity_m_s(flow_m3_s: float, diameter_mm: float) -> float:
    """Mean velocity in a circular pipe [m/s]."""
    d = _require_positive("Cap", diameter_mm) / 1000.0
    area = math.pi * d * d / 4.0
    return max(float(flow_m3_s), 0.0) / area


def api_14e_erosion_velocity(rho_mix_kg_m3: float, continuous: bool = True) -> float:
    """API RP 14E erosional velocity limit [m/s] (two-phase guidance).

    v_e = C / sqrt(rho_mix), C = 122 (continuous) or 152 (intermittent) in SI.
    """
    rho = _require_positive("Yogunluk", rho_mix_kg_m3)
    c = API_14E_C_CONTINUOUS_SI if continuous else API_14E_C_INTERMITTENT_SI
    return c / math.sqrt(rho)


def speed_of_sound_m_s(specific_heat_ratio: float, temperature_k: float, molecular_weight: float) -> float:
    """Ideal-gas speed of sound [m/s]; c = sqrt(k * R_specific * T)."""
    k = _require_positive("Isi kapasite orani", specific_heat_ratio)
    t = _require_positive("Sicaklik", temperature_k)
    mw = _require_positive("Molekuler agirlik", molecular_weight)
    return math.sqrt(k * 8314.0 * t / mw)


def _diameter_mm_to_m(value: float | None, fallback_mm: int) -> float:
    raw = float(value) if value is not None else float(fallback_mm)
    return raw / 1000.0


def _base_result_dict(service: str, source_ids: list[str]) -> dict:
    return {
        "service": service,
        "sources": [SOURCE_LIBRARY[source_id] for source_id in source_ids],
        "method_panel": [],
        "equations": [],
        "intermediate_values": {},
    }


_SIZING_RESULT_FIELDS = frozenset(f.name for f in fields(SizingResult))
_CORE_KEYS = _SIZING_RESULT_FIELDS - {"extra"}


def _pack_result(raw: dict) -> SizingResult:
    extra = {k: v for k, v in raw.items() if k not in _CORE_KEYS}
    kwargs: dict[str, Any] = dict(extra=extra)
    for field_name in _CORE_KEYS:
        if field_name in raw:
            kwargs[field_name] = raw[field_name]
    return SizingResult(**kwargs)


def _predict_valve_noise(
    service: str,
    flow_kg_s: float,
    p1_bar: float,
    p2_bar: float,
    t_k: float,
    density_kg_m3: float,
    specific_heat_ratio: float,
    mw: float,
    kv: float,
    valve_diameter_m: float,
    pipe_diameter_m: float,
    fl: float,
    fd: float,
    vapor_pressure_bar: float | None = None,
) -> float | None:
    """Estimate valve noise level [dB(A)] via IEC 60534-8 wrapper. Returns None on failure."""
    try:
        from valve_noise import predict_noise_gas, predict_noise_liquid
    except ImportError:
        return None
    try:
        p1_pa = p1_bar * 1e5
        p2_pa = p2_bar * 1e5
        if service == "liquid":
            pv_pa = (vapor_pressure_bar or 0.0) * 1e5
            return predict_noise_liquid(
                flow_kg_s=flow_kg_s, inlet_pressure_pa=p1_pa, outlet_pressure_pa=p2_pa,
                vapor_pressure_pa=pv_pa, density_kg_m3=density_kg_m3,
                speed_of_sound_m_s=None, kv=kv, valve_diameter_m=valve_diameter_m,
                pipe_diameter_m=pipe_diameter_m, fl=fl, fd=fd,
            )
        return predict_noise_gas(
            flow_kg_s=flow_kg_s, inlet_pressure_pa=p1_pa, outlet_pressure_pa=p2_pa,
            inlet_temperature_k=t_k, density_kg_m3=density_kg_m3,
            specific_heat_ratio=specific_heat_ratio, molecular_weight=mw,
            kv=kv, valve_diameter_m=valve_diameter_m, pipe_diameter_m=pipe_diameter_m,
            fd=fd, fl=fl,
        )
    except Exception:
        return None


def _predict_actuator_thrust(
    valve_dn_mm: int,
    inlet_pressure_bar: float,
    outlet_pressure_bar: float,
) -> dict[str, float] | None:
    """Estimate actuator thrust requirement. Returns None on failure."""
    try:
        from actuator_sizing import total_required_thrust
    except ImportError:
        return None
    try:
        result = total_required_thrust(
            port_diameter_mm=valve_dn_mm,
            inlet_pressure_bar=inlet_pressure_bar,
            outlet_pressure_bar=outlet_pressure_bar,
            shutoff_pressure_bar=inlet_pressure_bar,
        )
        return result
    except Exception:
        return None


def _predict_actuator_selection(
    valve_dn_mm: int,
    thrust_result: dict[str, float] | None,
) -> dict[str, Any] | None:
    """Select actuator meeting thrust and stroke from catalog. Returns None on failure."""
    if not thrust_result or "total_n" not in thrust_result:
        return None
    try:
        from actuator_sizing import estimate_valve_stroke_mm, select_actuator
        stroke_mm = estimate_valve_stroke_mm(valve_dn_mm)
        return select_actuator(thrust_result["total_n"], stroke_mm)
    except Exception:
        return None


def _size_iteration(
    valve_series: list[ValveSize],
    pipe_inlet_mm: float | None,
    pipe_outlet_mm: float | None,
    compute: Callable[[float, float, float], dict],
    design_margin_pct: float = 0.0,
) -> tuple[ValveSize, dict, bool]:
    """Common candidate-valve iteration used by liquid/gas/steam sizing."""
    margin_factor = 1.0 + max(float(design_margin_pct), 0.0) / 100.0
    candidates: list[tuple[ValveSize, dict]] = []
    selected: tuple[ValveSize, dict] | None = None
    for valve in valve_series:
        d1 = _diameter_mm_to_m(pipe_inlet_mm, valve.dn_mm)
        d2 = _diameter_mm_to_m(pipe_outlet_mm, valve.dn_mm)
        d = valve.dn_mm / 1000.0
        details = compute(d1, d2, d)
        candidates.append((valve, details))
        if valve.cv_rated >= kv_to_cv(details["Kv"]) * margin_factor:
            selected = (valve, details)
            break
    if selected is None:
        valve, details = candidates[-1]
        return valve, details, True
    valve, details = selected
    return valve, details, False


def _opening_metrics(
    required_cv: float,
    rated_cv: float,
    design_margin_pct: float,
    flow_characteristic: str,
    rangeability: float,
) -> dict[str, float | bool]:
    margin_factor = 1.0 + max(float(design_margin_pct), 0.0) / 100.0
    required_cv_margin = required_cv * margin_factor
    opening = estimate_opening(required_cv_margin, rated_cv, flow_characteristic, rangeability)
    min_cv = estimate_min_controllable_cv(rated_cv, flow_characteristic, rangeability)
    ratio = required_cv_margin / rated_cv if rated_cv > 0 else 0.0
    return {
        "required_cv_with_margin": required_cv_margin,
        "opening_fraction": opening,
        "opening_percent": opening * 100.0,
        "cv_ratio": ratio,
        "rangeability_min_cv": min_cv,
        "rangeability_ok": required_cv >= min_cv,
    }


def size_liquid_valve(
    data: LiquidSizingInput,
    valve_series: list[ValveSize] | None = None,
    valve_meta: dict | None = None,
    design_margin_pct: float = 0.0,
    flow_characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
) -> SizingResult:
    """Size a control valve for liquid service.

    Uses IEC 60534-2-1 equations via fluids.control_valve.size_control_valve_l.
    Returns a SizingResult with required_cv, required_kv, valve_dn_mm, valve_inch,
    rated_cv, is_choked, and intermediate_values.
    """
    flow_m3h = _require_positive("Debi", data.flow_m3h)
    density = _require_positive("Yogunluk", data.density_kg_m3)
    pv = max(float(data.vapor_pressure_bar_a), 0.0)
    pc = _require_positive("Kritik basinc", data.critical_pressure_bar_a)
    mu = _require_positive("Viskozite", data.viscosity_pa_s)
    fl = _require_positive("FL", data.fl)
    fd = _require_positive("Fd", data.fd)
    delta_p_bar = _validate_pressure_drop(data.inlet_pressure_bar_a, data.outlet_pressure_bar_a)

    sg = density / 999.016
    q_gpm = flow_m3h * M3H_TO_GPM
    ff = FF_A - FF_B * math.sqrt(max(pv / pc, 0.0))
    if data.inlet_pressure_bar_a <= ff * pv:
        raise ValueError(
            f"Giris basinci P1 ({data.inlet_pressure_bar_a:.3f} bar) buhar basincinin ve kavitasyon "
            f"esiginin ({ff * pv:.3f} bar) altinda; akiskan vanaya kaynayarak giriyor. "
            "Tek fazli IEC sivi sizing uygulanamaz; iki-fazli veya buhar/gaz sizing gereklidir."
        )
    dp_max_valve_only_bar = (fl ** 2) * (data.inlet_pressure_bar_a - ff * pv)
    dp_max_valve_only_bar = max(dp_max_valve_only_bar, 1e-9)

    valve_series = valve_series or DEFAULT_VALVE_SERIES

    def _eval(d1: float, d2: float, d: float) -> dict[str, Any]:
        return cast(dict[str, Any], size_control_valve_l(
            rho=density, Psat=pv * 1e5, Pc=pc * 1e5, mu=mu,
            P1=data.inlet_pressure_bar_a * 1e5,
            P2=data.outlet_pressure_bar_a * 1e5,
            Q=flow_m3h / 3600.0,
            D1=d1, D2=d2, d=d, FL=fl, Fd=fd, full_output=True,
        ))

    valve, details, overflow = _size_iteration(
        valve_series, data.pipe_inlet_diameter_mm, data.pipe_outlet_diameter_mm, _eval,
        design_margin_pct=design_margin_pct,
    )

    required_kv = details["Kv"]
    required_cv = kv_to_cv(required_kv)
    opening_metrics = _opening_metrics(
        required_cv, valve.cv_rated, design_margin_pct, flow_characteristic, rangeability,
    )
    fp = details.get("FP") or 1.0
    flp = details.get("FLP")
    rev = details.get("Rev")
    laminar = details.get("laminar")

    fl_effective = flp if flp else fl
    dp_max_bar = (fl_effective ** 2) * (data.inlet_pressure_bar_a - ff * pv)
    dp_max_bar = max(dp_max_bar, 1e-9)
    is_choked = delta_p_bar >= dp_max_bar
    effective_dp_bar = min(delta_p_bar, dp_max_bar)
    dp_max_valve_only_bar = (fl ** 2) * (data.inlet_pressure_bar_a - ff * pv)
    dp_max_valve_only_bar = max(dp_max_bar if flp else dp_max_valve_only_bar, 1e-9)

    sigma = _iec_cavitation_index(data.inlet_pressure_bar_a, data.outlet_pressure_bar_a, pv)
    if data.outlet_pressure_bar_a <= pv:
        regime = "flashing"
    elif is_choked:
        regime = "choked-cavitating"
    elif sigma < 1.0:
        regime = "cavitating-risk"
    else:
        regime = "subcritical"

    warnings: list[str] = []
    if data.inlet_pressure_bar_a <= pv:
        warnings.append(
            f"Giris basinci P1 ({data.inlet_pressure_bar_a:.3f} bar) buhar basincina "
            f"({pv:.3f} bar) esit veya altinda; akiskan vanaya kaynayan/iki-fazli giriyor. "
            "Tek fazli IEC sivi boyutlandirmasi yetersiz kalabilir; iki-fazli analiz gereklidir."
        )
    if overflow:
        warnings.append("Gereken Cv secilebilir vana serisinin ustunde; en buyuk boyut secildi. Vendor dogrulamasi gereklidir.")
    elif not opening_metrics["rangeability_ok"]:
        warnings.append(
            f"Gereken Cv ({required_cv:.3f}), minimum kontrollu Cv'nin "
            f"({opening_metrics['rangeability_min_cv']:.3f}) altinda; vana rangeability disinda "
            "kontrol edemez. Daha kucuk trim veya vana secin."
        )
    elif opening_metrics["opening_percent"] > 85.0:
        warnings.append(
            f"Tasarim acikligi %{opening_metrics['opening_percent']:.1f} onerilen sinirin "
            "(~%85) uzerinde; daha buyuk vana degerlendirilmelidir."
        )

    flow_kg_s_liquid = flow_m3h * density / 3600.0
    noise_db = _predict_valve_noise(
        "liquid", flow_kg_s_liquid, data.inlet_pressure_bar_a, data.outlet_pressure_bar_a,
        0.0, density, 0.0, 0.0, required_kv,
        valve.dn_mm / 1000.0, (data.pipe_inlet_diameter_mm or valve.dn_mm) / 1000.0,
        fl, fd, pv,
    )

    act_thrust = _predict_actuator_thrust(valve.dn_mm, data.inlet_pressure_bar_a, data.outlet_pressure_bar_a)
    act_selection = _predict_actuator_selection(valve.dn_mm, act_thrust)

    q_m3s = flow_m3h / 3600.0
    velocity: dict[str, float | bool] = {
        "pipe_in_m_s": pipe_velocity_m_s(q_m3s, data.pipe_inlet_diameter_mm or valve.dn_mm),
        "pipe_out_m_s": pipe_velocity_m_s(q_m3s, data.pipe_outlet_diameter_mm or valve.dn_mm),
    }
    if velocity["pipe_out_m_s"] > LIQUID_VELOCITY_LIMIT_M_S:
        warnings.append(
            f"Cikis hattinda sivi hizi {velocity['pipe_out_m_s']:.1f} m/s onerilen "
            f"{LIQUID_VELOCITY_LIMIT_M_S:.0f} m/s sinirini asiyor; erozyon riski."
        )
    elif velocity["pipe_out_m_s"] > LIQUID_VELOCITY_ADVISORY_M_S:
        warnings.append(
            f"Cikis hattinda sivi hizi {velocity['pipe_out_m_s']:.1f} m/s; "
            f"{LIQUID_VELOCITY_ADVISORY_M_S:.0f} m/s uzeri uzun sureli servis icin degerlendirilmelidir."
        )

    result = _base_result_dict("liquid", ["iec_scope", "primer_liquid", "fisher_choked"])
    result.update(
        {
            "required_cv": required_cv,
            "required_kv": required_kv,
            "rated_cv": valve.cv_rated,
            "rated_kv": cv_to_kv(valve.cv_rated),
            "valve_dn_mm": valve.dn_mm,
            "valve_inch": valve.inch,
            "delta_p_bar": delta_p_bar,
            "effective_delta_p_bar": effective_dp_bar,
            "specific_gravity": sg,
            "is_choked": is_choked,
            "dp_choked_bar": dp_max_bar,
            "dp_choked_valve_only_bar": dp_max_valve_only_bar,
            "outlet_margin_to_vapor_bar": data.outlet_pressure_bar_a - pv,
            "ff": ff,
            "flow_regime": regime,
            "cavitation_index": sigma,
            "warning": "",
            "velocity": velocity,
            "valve_meta": valve_meta or {},
            "design_margin_pct": float(design_margin_pct),
            "required_cv_with_margin": float(opening_metrics["required_cv_with_margin"]),
            "opening_percent": float(opening_metrics["opening_percent"]),
            "cv_ratio": float(opening_metrics["cv_ratio"]),
            "rangeability_min_cv": float(opening_metrics["rangeability_min_cv"]),
            "rangeability_ok": bool(opening_metrics["rangeability_ok"]),
            "reynolds_valve": rev,
            "laminar": laminar,
            "fp": fp,
            "flp": flp,
            "noise_db": noise_db,
            "actuator_thrust_n": act_thrust,
            "actuator_selection": act_selection,
            "valve_spec": build_valve_spec(
                "liquid", data.inlet_pressure_bar_a, is_choked, regime,
                vendor_pressure_class="", vendor_leakage_class="",
            ),
        }
    )

    if regime == "flashing":
        quality_x = flash_fraction(
            data.inlet_pressure_bar_a,
            data.outlet_pressure_bar_a,
            data.temperature_c,
            data.specific_heat_j_kgk,
            data.latent_heat_j_kg,
        )
        rho_g = vapor_density_ideal_gas(
            data.outlet_pressure_bar_a, data.temperature_c, data.molecular_weight,
        )
        rho_tp = two_phase_density_homogeneous(quality_x, density, rho_g)
        cv_flashing = flashing_cv_estimate(required_cv, quality_x, density, rho_g)
        result["flashing"] = {
            "quality_x": quality_x,
            "rho_vapor_kg_m3": rho_g,
            "rho_tp_kg_m3": rho_tp,
            "required_cv_single_phase": required_cv,
            "required_cv_flashing": cv_flashing,
            "flashing_cv_multiplier": cv_flashing / required_cv if required_cv > 0 else 1.0,
        }
        q_tp_m3s = (flow_m3h * density / rho_tp) / 3600.0
        v_tp = pipe_velocity_m_s(q_tp_m3s, data.pipe_outlet_diameter_mm or valve.dn_mm)
        v_e = api_14e_erosion_velocity(rho_tp)
        velocity["two_phase_out_m_s"] = v_tp
        velocity["api_14e_limit_m_s"] = v_e
        velocity["erosion_risk"] = bool(v_tp > v_e)
        warnings.append(
            f"Flashing bekleniyor: P2 ({data.outlet_pressure_bar_a:.3f} bar) <= Pv "
            f"({pv:.3f} bar). Tahmini flash orani %{quality_x * 100.0:.1f}; iki fazli Cv "
            f"gereksinimi tek faza gore yaklasik {cv_flashing / required_cv:.2f}x daha yuksek. "
            "Ozel anti-flashing trim ve body secimi icin vendor dogrulamasi sarttir."
        )
        if v_tp > v_e:
            warnings.append(
                f"Iki fazli cikis hizi {v_tp:.1f} m/s, API 14E erozyon siniri "
                f"({v_e:.1f} m/s) uzerinde; erozyon korumasi gerekir."
            )
    elif regime == "choked-cavitating":
        warnings.append("Choked liquid flow / kavitasyon riski mevcut. Trim ve malzeme kontrolu gerekli.")
    elif regime == "cavitating-risk":
        warnings.append("Kismi kavitasyon riski mevcut. Vendor trim secimi ile kontrol edilmeli.")

    result["warning"] = " ".join(warnings)
    result["trim_guidance"] = recommend_trim(
        "liquid", regime, is_choked, noise_db,
        float(opening_metrics["opening_percent"]), sigma, temperature_c=data.temperature_c,
    )

    result["equations"] = [
        "FF = 0.96 - 0.28*sqrt(Pv/Pc)",
        "DeltaP_max = FL^2 * (P1 - FF*Pv)",
        "IEC candidate sizing via fluids.control_valve.size_control_valve_l",
        "Kv = 0.865 * Cv",
    ]
    result["method_panel"] = [
        "IEC/ISA liquid sizing yaklasimi fluids.control_valve uygulamasi ile candidate-valve bazinda hesaplandi.",
        "Pipe reducer etkisi icin FP ve FLP otomatik hesaplandi.",
        "Flow regime, P2-Pv iliskisi ve choke siniri uzerinden siniflandirildi.",
        "Flashing durumunda HEM iki fazli Cv tahmini (flash orani, homojen yogunluk) sonuca eklenir; final trim vendor dogrulamasi ile secilmelidir.",
    ]
    result["intermediate_values"] = {
        "Q_gpm": q_gpm,
        "SG": sg,
        "FF": ff,
        "DeltaP_actual_bar": delta_p_bar,
        "DeltaP_max_bar": dp_max_bar,
        "DeltaP_max_valve_only_bar": dp_max_valve_only_bar,
        "DeltaP_effective_bar": effective_dp_bar,
        "FLP": flp,
        "FL_valve_only": fl,
        "Fd": fd,
        "Fp": fp,
        "mu_Pa_s": mu,
        "Rev": rev,
        "Laminar": laminar,
        "Cavitation_index": sigma,
        "Design_margin_pct": float(design_margin_pct),
        "Opening_percent": float(opening_metrics["opening_percent"]),
        "Cv_ratio": float(opening_metrics["cv_ratio"]),
        "Rangeability_min_Cv": float(opening_metrics["rangeability_min_cv"]),
        "Rangeability_ok": bool(opening_metrics["rangeability_ok"]),
        "Flashing_Cv_multiplier": result.get("flashing", {}).get("flashing_cv_multiplier", 1.0),
        "Pipe_in_velocity_m_s": velocity["pipe_in_m_s"],
        "Pipe_out_velocity_m_s": velocity["pipe_out_m_s"],
    }
    logger.info("Liquid sizing: Cv=%.3f, valve=DN%s, regime=%s", required_cv, valve.dn_mm, regime)
    return _pack_result(result)


def size_gas_valve(
    data: GasSizingInput,
    valve_series: list[ValveSize] | None = None,
    valve_meta: dict | None = None,
    design_margin_pct: float = 0.0,
    flow_characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
) -> SizingResult:
    """Size a control valve for gas service.

    Uses IEC 60534-2-1 equations via fluids.control_valve.size_control_valve_g
    with expansion factor Y and choked-flow check against xT * Fk.
    """
    flow_nm3h = _require_positive("Normal debi", data.flow_nm3h)
    t_k = _require_positive("Sicaklik", data.temperature_c + 273.15)
    mw = _require_positive("Molekuler agirlik", data.molecular_weight)
    k = _require_positive("Isi kapasite orani", data.specific_heat_ratio)
    mu = _require_positive("Viskozite", data.viscosity_pa_s)
    z = _require_positive("Sikistirilabilirlik", data.z)
    fl = _require_positive("FL", data.fl)
    fd = _require_positive("Fd", data.fd)
    xt = _require_positive("xT", data.xt)
    delta_p_bar = _validate_pressure_drop(data.inlet_pressure_bar_a, data.outlet_pressure_bar_a)

    q_actual_m3h = flow_nm3h * (NORMAL_P_BAR / data.inlet_pressure_bar_a) * (t_k / NORMAL_T_K) * z
    p1_psia = data.inlet_pressure_bar_a * BAR_TO_PSI
    x = delta_p_bar / data.inlet_pressure_bar_a
    fk = k / AIR_K
    x_choked = fk * xt
    gas_specific_gravity = mw / AIR_MW
    q_scfh = flow_nm3h * NM3H_TO_SCFH
    t_r = t_k * CELSIUS_TO_RANKINE
    valve_series = valve_series or DEFAULT_VALVE_SERIES

    def _eval(d1: float, d2: float, d: float) -> dict[str, Any]:
        return cast(dict[str, Any], size_control_valve_g(
            T=t_k, MW=mw, mu=mu, gamma=k, Z=z,
            P1=data.inlet_pressure_bar_a * 1e5,
            P2=data.outlet_pressure_bar_a * 1e5,
            Q=q_actual_m3h / 3600.0,
            D1=d1, D2=d2, d=d, FL=fl, Fd=fd, xT=xt, full_output=True,
        ))

    valve, details, overflow = _size_iteration(
        valve_series, data.pipe_inlet_diameter_mm, data.pipe_outlet_diameter_mm, _eval,
        design_margin_pct=design_margin_pct,
    )

    required_kv = details["Kv"]
    required_cv = kv_to_cv(required_kv)
    opening_metrics = _opening_metrics(
        required_cv, valve.cv_rated, design_margin_pct, flow_characteristic, rangeability,
    )
    fp = details.get("FP") or 1.0
    xtp = details.get("xTP")
    expansion_factor = details.get("Y")
    rev = details.get("Rev")
    laminar = details.get("laminar")
    x_choked_effective = (xtp if xtp is not None else xt) * fk
    x_for_eq = min(x, x_choked_effective)
    is_choked = x >= x_choked_effective

    warnings: list[str] = ["Gaz sizing IEC/ISA'ya yaklastirildi; yine de final secim vendor yazilimi ile dogrulanmali."]
    if overflow:
        warnings = ["Gereken Cv secilebilir vana serisinin ustunde; en buyuk boyut secildi. Vendor dogrulamasi gereklidir."]
    elif not opening_metrics["rangeability_ok"]:
        warnings = [
            f"Gereken Cv ({required_cv:.3f}), minimum kontrollu Cv'nin "
            f"({opening_metrics['rangeability_min_cv']:.3f}) altinda; vana rangeability disinda "
            "kontrol edemez. Daha kucuk trim veya vana secin."
        ]
    elif opening_metrics["opening_percent"] > 85.0:
        warnings = [
            f"Tasarim acikligi %{opening_metrics['opening_percent']:.1f} onerilen sinirin "
            "(~%85) uzerinde; daha buyuk vana degerlendirilmelidir."
        ]

    gas_density_kg_m3 = (data.inlet_pressure_bar_a * 1e5 * mw * 0.001) / (8.314 * t_k * z)
    flow_kg_s_gas = (flow_nm3h * mw * 0.001) / (22.414 * 3600.0)
    noise_db = _predict_valve_noise(
        "gas", flow_kg_s_gas, data.inlet_pressure_bar_a, data.outlet_pressure_bar_a,
        t_k, gas_density_kg_m3, k, mw, required_kv,
        valve.dn_mm / 1000.0, (data.pipe_inlet_diameter_mm or valve.dn_mm) / 1000.0,
        fd, fl,
    )

    c_out = speed_of_sound_m_s(k, t_k, mw)
    q_out_m3h = q_actual_m3h * (data.inlet_pressure_bar_a / data.outlet_pressure_bar_a)
    v_out = pipe_velocity_m_s(q_out_m3h / 3600.0, data.pipe_outlet_diameter_mm or valve.dn_mm)
    mach_out = v_out / c_out if c_out > 0 else 0.0
    velocity: dict[str, float | bool] = {
        "pipe_out_m_s": v_out,
        "mach_outlet": mach_out,
        "speed_of_sound_m_s": c_out,
    }
    if mach_out > GAS_MACH_LIMIT:
        warnings.append(
            f"Cikis Mach sayisi {mach_out:.2f} onerilen {GAS_MACH_LIMIT:.1f} sinirini asiyor; "
            "gurultu/erozyon riski yuksek."
        )
    elif mach_out > GAS_MACH_ADVISORY:
        warnings.append(
            f"Cikis Mach sayisi {mach_out:.2f}; {GAS_MACH_ADVISORY:.1f} uzeri gurultu acisindan degerlendirilmelidir."
        )

    act_thrust = _predict_actuator_thrust(valve.dn_mm, data.inlet_pressure_bar_a, data.outlet_pressure_bar_a)
    act_selection = _predict_actuator_selection(valve.dn_mm, act_thrust)

    result = _base_result_dict("gas", ["iec_scope", "isa_committee", "primer_liquid"])
    result.update(
        {
            "required_cv": required_cv,
            "required_kv": required_kv,
            "rated_cv": valve.cv_rated,
            "rated_kv": cv_to_kv(valve.cv_rated),
            "valve_dn_mm": valve.dn_mm,
            "valve_inch": valve.inch,
            "delta_p_bar": delta_p_bar,
            "pressure_drop_ratio_x": x,
            "effective_x": x_for_eq,
            "gas_specific_gravity": gas_specific_gravity,
            "expansion_factor_y": expansion_factor,
            "is_choked": is_choked,
            "fk": fk,
            "x_choked": x_choked_effective,
            "x_choked_valve_only": x_choked,
            "xtp": xtp,
            "fp": fp,
            "reynolds_valve": rev,
            "laminar": laminar,
            "warning": " ".join(warnings),
            "velocity": velocity,
            "valve_meta": valve_meta or {},
            "design_margin_pct": float(design_margin_pct),
            "required_cv_with_margin": float(opening_metrics["required_cv_with_margin"]),
            "opening_percent": float(opening_metrics["opening_percent"]),
            "cv_ratio": float(opening_metrics["cv_ratio"]),
            "rangeability_min_cv": float(opening_metrics["rangeability_min_cv"]),
            "rangeability_ok": bool(opening_metrics["rangeability_ok"]),
            "noise_db": noise_db,
            "actuator_thrust_n": act_thrust,
            "actuator_selection": act_selection,
            "valve_spec": build_valve_spec(
                "gas", data.inlet_pressure_bar_a, is_choked,
                vendor_pressure_class="", vendor_leakage_class="",
            ),
            "trim_guidance": recommend_trim(
                "gas", "", is_choked, noise_db,
                float(opening_metrics["opening_percent"]), None, x, data.temperature_c,
            ),
        }
    )
    result["equations"] = [
        "Fk = k/1.4",
        "x = DeltaP/P1",
        "x_choked = Fk* xTP_e  where xTP_e = xT or xTP (with reducers)",
        "Expansion factor Y via fluids.control_valve.size_control_valve_g",
        "Kv = 0.865 * Cv",
    ]
    result["method_panel"] = [
        "Compressible sizing candidate-valve bazinda IEC uygulamasi ile hesaplandi.",
        "Pipe reducer etkisi icin FP ve xTP otomatik hesaplandi.",
        "Choked kontrolu xTP varsa xTP*Fk, yoksa xT*Fk uzerinden izleniyor; son sizing sonucu IEC hesaplayicisindan aliniyor.",
    ]
    result["intermediate_values"] = {
        "Q_nm3h": flow_nm3h,
        "Q_actual_m3h": q_actual_m3h,
        "Q_scfh": q_scfh,
        "P1_psia": p1_psia,
        "T1_R": t_r,
        "Gg": gas_specific_gravity,
        "k": k,
        "Fk": fk,
        "x": x,
        "x_choked": x_choked_effective,
        "x_choked_valve_only": x_choked,
        "x_for_equation": x_for_eq,
        "Y": expansion_factor,
        "Fp": fp,
        "xTP": xtp,
        "mu_Pa_s": mu,
        "Rev": rev,
        "Laminar": laminar,
        "Z": z,
        "Z_source": "User input",
        "Design_margin_pct": float(design_margin_pct),
        "Opening_percent": float(opening_metrics["opening_percent"]),
        "Cv_ratio": float(opening_metrics["cv_ratio"]),
        "Rangeability_min_Cv": float(opening_metrics["rangeability_min_cv"]),
        "Rangeability_ok": bool(opening_metrics["rangeability_ok"]),
        "Pipe_out_velocity_m_s": velocity["pipe_out_m_s"],
        "Mach_outlet": velocity["mach_outlet"],
    }
    logger.info("Gas sizing: Cv=%.3f, valve=DN%s, x=%.4f, choked=%s", required_cv, valve.dn_mm, x, is_choked)
    return _pack_result(result)


def size_steam_valve(
    data: SteamSizingInput,
    valve_series: list[ValveSize] | None = None,
    valve_meta: dict | None = None,
    design_margin_pct: float = 0.0,
    flow_characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
) -> SizingResult:
    """Size a control valve for steam service.

    Converts mass flow to actual volumetric flow using density derived from
    CoolProp (Water at P1, T1), then delegates to the IEC candidate-based
    gas sizing path via fluids.control_valve.size_control_valve_g.
    """
    flow_kg_h = _require_positive("Kutlesel debi", data.flow_kg_h)
    t_k = _require_positive("Sicaklik", data.temperature_c + 273.15)
    k = _require_positive("Isi kapasite orani", data.specific_heat_ratio)
    z = _require_positive("Sikistirilabilirlik", data.z)
    xt = _require_positive("xT", data.xt)
    fl = _require_positive("FL", data.fl)
    fd = _require_positive("Fd", data.fd)
    delta_p_bar = _validate_pressure_drop(data.inlet_pressure_bar_a, data.outlet_pressure_bar_a)

    iapws_ok = False
    coolprop_ok = False
    from fluid_properties import get_steam_properties_iapws

    iapws_props = get_steam_properties_iapws(data.inlet_pressure_bar_a, data.temperature_c)
    if iapws_props is not None:
        density = iapws_props["density_kg_m3"]
        mu = iapws_props["viscosity_pa_s"]
        mw = 18.015
        iapws_ok = True
    else:
        import CoolProp.CoolProp as CP  # noqa: N817
        p_pa = data.inlet_pressure_bar_a * 1e5
        try:
            density = CP.PropsSI("D", "P", p_pa, "T", t_k, "Water")
            mu = CP.PropsSI("V", "P", p_pa, "T", t_k, "Water")
            mw = CP.PropsSI("M", "Water") * 1000.0
            coolprop_ok = True
        except Exception:
            density = (data.inlet_pressure_bar_a * 1e5 * 0.018015) / (8.314 * t_k * max(z, 0.001))
            mu = 1.5e-5
            mw = 18.015
            logger.warning("CoolProp steam properties unavailable; ideal gas fallback used (inaccurate above 30 bar(a)).")

    q_actual_m3h = flow_kg_h / density if density > 0 else 0.0

    p1_psia = data.inlet_pressure_bar_a * BAR_TO_PSI
    x = delta_p_bar / data.inlet_pressure_bar_a
    fk = k / AIR_K
    x_choked = fk * xt
    gas_specific_gravity = mw / AIR_MW
    t_r = t_k * CELSIUS_TO_RANKINE

    valve_series = valve_series or DEFAULT_VALVE_SERIES

    def _eval(d1: float, d2: float, d: float) -> dict[str, Any]:
        return cast(dict[str, Any], size_control_valve_g(
            T=t_k, MW=mw, mu=mu, gamma=k, Z=z,
            P1=data.inlet_pressure_bar_a * 1e5,
            P2=data.outlet_pressure_bar_a * 1e5,
            Q=q_actual_m3h / 3600.0,
            D1=d1, D2=d2, d=d, FL=fl, Fd=fd, xT=xt, full_output=True,
        ))

    valve, details, overflow = _size_iteration(
        valve_series, data.pipe_inlet_diameter_mm, data.pipe_outlet_diameter_mm, _eval,
        design_margin_pct=design_margin_pct,
    )

    required_kv = details["Kv"]
    required_cv = kv_to_cv(required_kv)
    opening_metrics = _opening_metrics(
        required_cv, valve.cv_rated, design_margin_pct, flow_characteristic, rangeability,
    )
    fp_val = details.get("FP") or 1.0
    xtp = details.get("xTP")
    expansion_factor = details.get("Y")
    rev = details.get("Rev")
    laminar = details.get("laminar")
    x_choked_effective = (xtp if xtp is not None else xt) * fk
    x_for_eq = min(x, x_choked_effective)
    is_choked = x >= x_choked_effective

    warning = "Steam sizing IEC/ISA'ya yaklastirilmistir; yine de final secim vendor yazilimi ile dogrulanmali."
    if not iapws_ok and not coolprop_ok:
        warning += " Uyari: CoolProp devre disi, ideal gaz yaklasimi kullanildi (30 bar(a) uzerinde hata >%10)."
    if overflow:
        warning += " Gereken Cv secilebilir vana serisinin ustunde; en buyuk boyut secildi. Vendor dogrulamasi gereklidir."
    elif not opening_metrics["rangeability_ok"]:
        warning += (
            f" Gereken Cv ({required_cv:.3f}) minimum kontrollu Cv'nin "
            f"({opening_metrics['rangeability_min_cv']:.3f}) altinda; vana rangeability disinda "
            "kontrol edemez. Daha kucuk trim veya vana secin."
        )
    elif opening_metrics["opening_percent"] > 85.0:
        warning += (
            f" Tasarim acikligi %{opening_metrics['opening_percent']:.1f} onerilen sinirin "
            "(~%85) uzerinde; daha buyuk vana degerlendirilmelidir."
        )

    c_out = speed_of_sound_m_s(k, t_k, mw)
    q_out_m3h = q_actual_m3h * (data.inlet_pressure_bar_a / data.outlet_pressure_bar_a)
    v_out = pipe_velocity_m_s(q_out_m3h / 3600.0, data.pipe_outlet_diameter_mm or valve.dn_mm)
    mach_out = v_out / c_out if c_out > 0 else 0.0
    velocity: dict[str, float | bool] = {
        "pipe_out_m_s": v_out,
        "mach_outlet": mach_out,
        "speed_of_sound_m_s": c_out,
    }
    if mach_out > GAS_MACH_LIMIT:
        warning += (
            f" Cikis Mach sayisi {mach_out:.2f} onerilen {GAS_MACH_LIMIT:.1f} sinirini asiyor; "
            "gurultu/erozyon riski yuksek."
        )
    elif mach_out > GAS_MACH_ADVISORY:
        warning += f" Cikis Mach sayisi {mach_out:.2f}; {GAS_MACH_ADVISORY:.1f} uzeri gurultu acisindan degerlendirilmelidir."

    noise_db = _predict_valve_noise(
        "steam", flow_kg_h / 3600.0, data.inlet_pressure_bar_a, data.outlet_pressure_bar_a,
        t_k, density, k, mw, required_kv,
        valve.dn_mm / 1000.0, (data.pipe_inlet_diameter_mm or valve.dn_mm) / 1000.0,
        fd, fl,
    )

    act_thrust = _predict_actuator_thrust(valve.dn_mm, data.inlet_pressure_bar_a, data.outlet_pressure_bar_a)
    act_selection = _predict_actuator_selection(valve.dn_mm, act_thrust)

    result = _base_result_dict("steam", ["primer_liquid", "iec_scope", "isa_committee"])
    result.update(
        {
            "required_cv": required_cv,
            "required_kv": required_kv,
            "rated_cv": valve.cv_rated,
            "rated_kv": cv_to_kv(valve.cv_rated),
            "valve_dn_mm": valve.dn_mm,
            "valve_inch": valve.inch,
            "delta_p_bar": delta_p_bar,
            "pressure_drop_ratio_x": x,
            "effective_x": x_for_eq,
            "gas_specific_gravity": gas_specific_gravity,
            "expansion_factor_y": expansion_factor,
            "is_choked": is_choked,
            "fk": fk,
            "x_choked": x_choked_effective,
            "x_choked_valve_only": x_choked,
            "xtp": xtp,
            "fp": fp_val,
            "reynolds_valve": rev,
            "laminar": laminar,
            "warning": warning,
            "velocity": velocity,
            "valve_meta": valve_meta or {},
            "design_margin_pct": float(design_margin_pct),
            "required_cv_with_margin": float(opening_metrics["required_cv_with_margin"]),
            "opening_percent": float(opening_metrics["opening_percent"]),
            "cv_ratio": float(opening_metrics["cv_ratio"]),
            "rangeability_min_cv": float(opening_metrics["rangeability_min_cv"]),
            "rangeability_ok": bool(opening_metrics["rangeability_ok"]),
            "noise_db": noise_db,
            "actuator_thrust_n": act_thrust,
            "actuator_selection": act_selection,
            "valve_spec": build_valve_spec(
                "steam", data.inlet_pressure_bar_a, is_choked,
                vendor_pressure_class="", vendor_leakage_class="",
            ),
            "trim_guidance": recommend_trim(
                "steam", "", is_choked, noise_db,
                float(opening_metrics["opening_percent"]), None, x, data.temperature_c,
            ),
        }
    )
    result["equations"] = [
        "Fk = k/1.4",
        "x = DeltaP/P1",
        "x_choked = Fk* xTP_e  where xTP_e = xT or xTP (with reducers)",
        "IEC candidate sizing via fluids.control_valve.size_control_valve_g (steam -> actual volume via CoolProp density)",
        "Kv = 0.865 * Cv",
    ]
    result["method_panel"] = [
        "Steam sizing: kutlesel debi CoolProp ile hesaplanan yogunluktan hacimsel debiye cevrildi.",
        "Compressible sizing candidate-valve bazinda IEC uygulamasi ile hesaplandi.",
        "Pipe reducer etkisi icin FP ve xTP otomatik hesaplandi.",
        "Choked kontrolu xTP varsa xTP*Fk, yoksa xT*Fk uzerinden izleniyor; son sizing sonucu IEC hesaplayicisindan aliniyor.",
    ]
    result["intermediate_values"] = {
        "W_kg/h": flow_kg_h,
        "P1_psia": p1_psia,
        "T1_R": t_r,
        "Gg": gas_specific_gravity,
        "k": k,
        "Fk": fk,
        "x": x,
        "x_choked": x_choked_effective,
        "x_choked_valve_only": x_choked,
        "x_for_equation": x_for_eq,
        "Y": expansion_factor,
        "Fp": fp_val,
        "xTP": xtp,
        "mu_Pa_s": mu,
        "Rev": rev,
        "Laminar": laminar,
        "Z": z,
        "Z_source": "Calculated from CoolProp or fallback",
        "Design_margin_pct": float(design_margin_pct),
        "Opening_percent": float(opening_metrics["opening_percent"]),
        "Cv_ratio": float(opening_metrics["cv_ratio"]),
        "Rangeability_min_Cv": float(opening_metrics["rangeability_min_cv"]),
        "Rangeability_ok": bool(opening_metrics["rangeability_ok"]),
        "Pipe_out_velocity_m_s": velocity["pipe_out_m_s"],
        "Mach_outlet": velocity["mach_outlet"],
    }
    logger.info("Steam sizing (IEC): Cv=%.3f, valve=DN%s, x=%.4f, choked=%s", required_cv, valve.dn_mm, x, is_choked)
    return _pack_result(result)


def z_sensitivity_gas(
    data: GasSizingInput,
    valve_series: list[ValveSize] | None = None,
    valve_meta: dict | None = None,
    delta_z: float = 0.05,
) -> dict[str, float]:
    base = size_gas_valve(data, valve_series, valve_meta)
    cv_mid = base["required_cv"]

    low = GasSizingInput(
        flow_nm3h=data.flow_nm3h, inlet_pressure_bar_a=data.inlet_pressure_bar_a,
        outlet_pressure_bar_a=data.outlet_pressure_bar_a, temperature_c=data.temperature_c,
        molecular_weight=data.molecular_weight, specific_heat_ratio=data.specific_heat_ratio,
        viscosity_pa_s=data.viscosity_pa_s, z=max(data.z - delta_z, 0.1),
        fl=data.fl, fd=data.fd, xt=data.xt,
        pipe_inlet_diameter_mm=data.pipe_inlet_diameter_mm,
        pipe_outlet_diameter_mm=data.pipe_outlet_diameter_mm,
    )
    cv_low = size_gas_valve(low, valve_series, valve_meta)["required_cv"]

    high = GasSizingInput(
        flow_nm3h=data.flow_nm3h, inlet_pressure_bar_a=data.inlet_pressure_bar_a,
        outlet_pressure_bar_a=data.outlet_pressure_bar_a, temperature_c=data.temperature_c,
        molecular_weight=data.molecular_weight, specific_heat_ratio=data.specific_heat_ratio,
        viscosity_pa_s=data.viscosity_pa_s, z=data.z + delta_z,
        fl=data.fl, fd=data.fd, xt=data.xt,
        pipe_inlet_diameter_mm=data.pipe_inlet_diameter_mm,
        pipe_outlet_diameter_mm=data.pipe_outlet_diameter_mm,
    )
    cv_high = size_gas_valve(high, valve_series, valve_meta)["required_cv"]

    pct = ((cv_high - cv_low) / cv_mid * 100) if cv_mid > 0 else 0.0
    return {"cv_low": cv_low, "cv_mid": cv_mid, "cv_high": cv_high, "delta_percent": pct, "delta_z": delta_z}
