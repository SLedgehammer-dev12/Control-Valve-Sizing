"""Control valve sizing engine.

Implements IEC 60534 / ISA-based Cv/Kv calculations for liquid, gas, and steam
services.  Exposes dataclass input types (LiquidSizingInput, GasSizingInput,
SteamSizingInput), sizing functions (size_liquid_valve, size_gas_valve,
size_steam_valve), and valve selection utilities (select_valve_size,
cv_to_kv, kv_to_cv).
"""

from __future__ import annotations

__version__ = "2.0.0"

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from typing import Any, cast

from fluids.control_valve import size_control_valve_g, size_control_valve_l

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


def select_valve_size(required_cv: float, valve_series: list[ValveSize] | None = None) -> ValveSize:
    """Select the smallest valve whose rated Cv >= required_cv.

    Deprecated: use _size_iteration instead (accounts for pipe reducer effects).
    """
    _require_positive("Gerekli Cv", required_cv)
    valve_series = valve_series or DEFAULT_VALVE_SERIES
    for valve in valve_series:
        if valve.cv_rated >= required_cv:
            return valve
    return valve_series[-1]


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


def _size_iteration(
    valve_series: list[ValveSize],
    pipe_inlet_mm: float | None,
    pipe_outlet_mm: float | None,
    compute: Callable[[float, float, float], dict],
) -> tuple[ValveSize, dict, bool]:
    """Common candidate-valve iteration used by liquid/gas/steam sizing."""
    candidates: list[tuple[ValveSize, dict]] = []
    selected: tuple[ValveSize, dict] | None = None
    for valve in valve_series:
        d1 = _diameter_mm_to_m(pipe_inlet_mm, valve.dn_mm)
        d2 = _diameter_mm_to_m(pipe_outlet_mm, valve.dn_mm)
        d = valve.dn_mm / 1000.0
        details = compute(d1, d2, d)
        candidates.append((valve, details))
        if valve.cv_rated >= kv_to_cv(details["Kv"]):
            selected = (valve, details)
            break
    if selected is None:
        valve, details = candidates[-1]
        return valve, details, True
    valve, details = selected
    return valve, details, False


def size_liquid_valve(
    data: LiquidSizingInput,
    valve_series: list[ValveSize] | None = None,
    valve_meta: dict | None = None,
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
    dp_max_bar = (fl ** 2) * (data.inlet_pressure_bar_a - ff * pv)
    dp_max_bar = max(dp_max_bar, 1e-9)
    is_choked = delta_p_bar >= dp_max_bar
    effective_dp_bar = min(delta_p_bar, dp_max_bar)

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
    )

    required_kv = details["Kv"]
    required_cv = kv_to_cv(required_kv)
    fp = details.get("FP") or 1.0
    flp = details.get("FLP")
    rev = details.get("Rev")
    laminar = details.get("laminar")

    cavitation_index = (data.outlet_pressure_bar_a - pv) / max(data.inlet_pressure_bar_a - pv, 1e-9)
    if data.outlet_pressure_bar_a <= pv:
        regime = "flashing"
    elif is_choked:
        regime = "choked-cavitating"
    elif cavitation_index < 0.5:
        regime = "cavitating-risk"
    else:
        regime = "subcritical"

    warning = ""
    if overflow:
        warning = "Gereken Cv secilebilir vana serisinin ustunde; en buyuk boyut secildi. Vendor dogrulamasi gereklidir."

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
            "outlet_margin_to_vapor_bar": data.outlet_pressure_bar_a - pv,
            "ff": ff,
            "flow_regime": regime,
            "cavitation_index": cavitation_index,
            "warning": warning,
            "valve_meta": valve_meta or {},
            "reynolds_valve": rev,
            "laminar": laminar,
            "fp": fp,
            "flp": flp,
        }
    )

    if regime == "flashing":
        result["warning"] = (
            "Flashing bekleniyor: P2, Pv'nin altinda veya esiti. "
            "Iki fazli akista Cv gereksinimi tek faza gore cok daha yuksektir. "
            "Ozel anti-flashing trim ve body secimi icin vendor dogrulamasi sarttir."
        )
    elif regime == "choked-cavitating":
        result["warning"] = "Choked liquid flow / kavitasyon riski mevcut. Trim ve malzeme kontrolu gerekli."
    elif regime == "cavitating-risk":
        result["warning"] = "Kismi kavitasyon riski mevcut. Vendor trim secimi ile kontrol edilmeli."

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
        "Flashing durumunda iki fazli akis modelleri devreye girer; bu surum tek fazli IEC denklemi kullanir.",
    ]
    result["intermediate_values"] = {
        "Q_gpm": q_gpm,
        "SG": sg,
        "FF": ff,
        "DeltaP_actual_bar": delta_p_bar,
        "DeltaP_max_bar": dp_max_bar,
        "DeltaP_effective_bar": effective_dp_bar,
        "Fd": fd,
        "Fp": fp,
        "FLP": flp,
        "mu_Pa_s": mu,
        "Rev": rev,
        "Laminar": laminar,
        "Cavitation_index": cavitation_index,
    }
    logger.info("Liquid sizing: Cv=%.3f, valve=DN%s, regime=%s", required_cv, valve.dn_mm, regime)
    return _pack_result(result)


def size_gas_valve(
    data: GasSizingInput,
    valve_series: list[ValveSize] | None = None,
    valve_meta: dict | None = None,
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
    )

    required_kv = details["Kv"]
    required_cv = kv_to_cv(required_kv)
    fp = details.get("FP") or 1.0
    xtp = details.get("xTP")
    expansion_factor = details.get("Y")
    rev = details.get("Rev")
    laminar = details.get("laminar")
    x_for_eq = min(x, xtp * fk) if xtp else min(x, x_choked)
    is_choked = x >= (xtp if xtp is not None else xt) * fk

    warning = "Gaz sizing IEC/ISA'ya yaklastirildi; yine de final secim vendor yazilimi ile dogrulanmali."
    if overflow:
        warning = "Gereken Cv secilebilir vana serisinin ustunde; en buyuk boyut secildi. Vendor dogrulamasi gereklidir."

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
            "x_choked": x_choked,
            "xtp": xtp,
            "fp": fp,
            "reynolds_valve": rev,
            "laminar": laminar,
            "warning": warning,
            "valve_meta": valve_meta or {},
        }
    )
    result["equations"] = [
        "Fk = k/1.4",
        "x = DeltaP/P1",
        "x_choked = Fk* xTP_e  where xTP_e = xT or xTP (with reducers)",
        "IEC candidate sizing via fluids.control_valve.size_control_valve_g",
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
        "x_choked": x_choked,
        "x_for_equation": x_for_eq,
        "Y": expansion_factor,
        "Fp": fp,
        "xTP": xtp,
        "mu_Pa_s": mu,
        "Rev": rev,
        "Laminar": laminar,
        "Z": z,
        "Z_source": "User input",
    }
    logger.info("Gas sizing: Cv=%.3f, valve=DN%s, x=%.4f, choked=%s", required_cv, valve.dn_mm, x, is_choked)
    return _pack_result(result)


def size_steam_valve(
    data: SteamSizingInput,
    valve_series: list[ValveSize] | None = None,
    valve_meta: dict | None = None,
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
    )

    required_kv = details["Kv"]
    required_cv = kv_to_cv(required_kv)
    fp_val = details.get("FP") or 1.0
    xtp = details.get("xTP")
    expansion_factor = details.get("Y")
    rev = details.get("Rev")
    laminar = details.get("laminar")
    x_for_eq = min(x, xtp * fk) if xtp else min(x, x_choked)
    is_choked = x >= (xtp if xtp is not None else xt) * fk

    warning = "Steam sizing IEC/ISA'ya yaklastirilmistir; yine de final secim vendor yazilimi ile dogrulanmali."
    if iapws_ok:
        pass
    elif not coolprop_ok:
        warning += " Uyari: CoolProp devre disi, ideal gaz yaklasimi kullanildi (30 bar(a) uzerinde hata >%10)."
    if overflow:
        warning = "Gereken Cv secilebilir vana serisinin ustunde; en buyuk boyut secildi. Vendor dogrulamasi gereklidir."

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
            "x_choked": x_choked,
            "xtp": xtp,
            "fp": fp_val,
            "reynolds_valve": rev,
            "laminar": laminar,
            "warning": warning,
            "valve_meta": valve_meta or {},
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
        "x_choked": x_choked,
        "x_for_equation": x_for_eq,
        "Y": expansion_factor,
        "Fp": fp_val,
        "xTP": xtp,
        "mu_Pa_s": mu,
        "Rev": rev,
        "Laminar": laminar,
        "Z": z,
        "Z_source": "Calculated from CoolProp or fallback",
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
