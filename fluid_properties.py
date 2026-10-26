"""Fluid property calculation via CoolProp HEOS + chemicals fallback.

Provides liquid presets (Water, Oil, etc.), gas mixture evaluation
(normalize_composition, evaluate_gas_mixture), single-fluid state
lookups (get_pure_fluid_state, list_coolprop_fluids, get_liquid_preset),
and chemical database helpers via the chemicals library.

All property-lookup functions implement a cascade fallback chain:
  CoolProp/iapws → thermo → chemicals EOS → ideal gas
"""

from __future__ import annotations

import contextlib
import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import CoolProp.CoolProp as CP  # noqa: N817

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# chemicals library integration (optional fallback for missing fluids)
# ---------------------------------------------------------------------------
_HAS_CHEMICALS = False
try:
    import chemicals.critical as _crit
    import chemicals.vapor_pressure as _vp
    from chemicals import Antoine
    from chemicals.identifiers import CAS_from_any, search_chemical

    _HAS_CHEMICALS = True
except ImportError:
    logger.debug("chemicals library not available; chemical lookup features disabled.")

@lru_cache(maxsize=512)
def _safe_chemical_props(name: str) -> dict[str, Any]:
    if not _HAS_CHEMICALS:
        return {}
    props: dict[str, Any] = {}
    try:
        cas = CAS_from_any(name)
        if not cas:
            return {}
        props["cas"] = cas
        props["cas_int"] = int(cas.replace("-", ""))
    except Exception as exc:
        logger.debug("chemicals CAS lookup failure for '%s': %s", name, exc)
        return {}

    try:
        meta = search_chemical(cas)
        if meta:
            props["mw_g_mol"] = meta.MW
            props["formula"] = meta.formula
            if meta.common_name:
                props["common_name"] = meta.common_name
    except Exception:
        pass

    for func, key in [(_crit.Tc, "tc_k"), (_crit.Pc, "pc_pa"), (_crit.Vc, "vc_m3_mol")]:
        try:
            val = func(cas)
            if val is not None:
                props[key] = float(val)
        except Exception:
            pass

    try:
        row = _vp.Psat_data_AntoinePoling.loc[cas]
        props["antoine_A"] = float(row["A"])
        props["antoine_B"] = float(row["B"])
        props["antoine_C"] = float(row["C"])
        props["antoine_Tmin_K"] = float(row["Tmin"])
        props["antoine_Tmax_K"] = float(row["Tmax"])
    except Exception:
        pass

    return props


def get_chemical_property(name: str, prop: str) -> Any:
    """Look up a pure-component chemical property by common name.

    Supported prop keys: mw_g_mol, formula, tc_k, pc_pa, vc_m3_mol,
    antoine_A, antoine_B, antoine_C, antoine_Tmin_K, antoine_Tmax_K, cas.
    Returns None if the property or chemical is not found.
    """
    props = _safe_chemical_props(name)
    return props.get(prop) if props else None


def get_chemical_vapor_pressure_bar_a(name: str, temperature_c: float) -> float | None:
    """Estimate vapor pressure [bar(a)] via Antoine equation from chemicals library.

    Falls back to None if Antoine coefficients are not available.
    """
    if not _HAS_CHEMICALS:
        return None
    t_k = temperature_c + 273.15
    props = _safe_chemical_props(name)
    if not props:
        return None
    a = props.get("antoine_A")
    b = props.get("antoine_B")
    c = props.get("antoine_C")
    tmin = props.get("antoine_Tmin_K")
    tmax = props.get("antoine_Tmax_K")
    if a is None or b is None or c is None:
        return None
    if tmin is not None and t_k < tmin:
        return None
    if tmax is not None and t_k > tmax:
        return None
    try:
        p_pa = Antoine(t_k, a, b, c)
        return p_pa / 1e5
    except Exception:
        return None


@lru_cache(maxsize=1)
def list_chemical_fluids() -> list[str]:
    """Return sorted common-name list of chemicals that have Antoine data."""
    if not _HAS_CHEMICALS:
        return []
    names: set[str] = set()
    for cas in _vp.Psat_data_AntoinePoling.index:
        try:
            meta = search_chemical(str(cas))
            if meta and meta.common_name:
                names.add(meta.common_name.lower())
        except Exception:
            pass
    return sorted(names)


def _gas_viscosity_fallback(t_k: float) -> float:
    """Estimate gas viscosity [Pa*s] via simplified kinetic theory (mu ~ sqrt(T))."""
    return 1.5e-5 * (t_k / 300.0) ** 0.5


# ---------------------------------------------------------------------------
# CoolProp-based helpers (original)
# ---------------------------------------------------------------------------

LIQUID_PRESETS: dict[str, dict[str, Any]] = {
    "Water": {"label": "Su", "density_kg_m3": 998.0,
              "vapor_pressure_bar_a": 0.023, "critical_pressure_bar_a": 220.64, "viscosity_pa_s": 0.00089},
    "ThermalOil": {"label": "Termal Yag", "density_kg_m3": 860.0,
                   "vapor_pressure_bar_a": 0.01, "critical_pressure_bar_a": 18.0, "viscosity_pa_s": 0.018},
    "LNG": {"label": "LNG", "density_kg_m3": 430.0,
            "vapor_pressure_bar_a": 1.2, "critical_pressure_bar_a": 46.0, "viscosity_pa_s": 0.00016},
    "Methanol": {"label": "Metanol", "density_kg_m3": 792.0,
                 "vapor_pressure_bar_a": 0.17, "critical_pressure_bar_a": 80.9, "viscosity_pa_s": 0.00059},
    "EthyleneGlycol": {"label": "Etilen Glikol", "density_kg_m3": 1110.0,
                       "vapor_pressure_bar_a": 0.01, "critical_pressure_bar_a": 77.0, "viscosity_pa_s": 0.0161},
    "Propane": {"label": "Propan", "density_kg_m3": 500.0,
                "vapor_pressure_bar_a": 8.5, "critical_pressure_bar_a": 42.5, "viscosity_pa_s": 0.00011},
    "Ammonia": {"label": "Amonyak", "density_kg_m3": 682.0,
                "vapor_pressure_bar_a": 8.6, "critical_pressure_bar_a": 113.3, "viscosity_pa_s": 0.00025},
    "Hydrogen": {"label": "Hidrojen (Sivi)", "density_kg_m3": 71.0,
                 "vapor_pressure_bar_a": 1.3, "critical_pressure_bar_a": 12.96, "viscosity_pa_s": 1.3e-5},
    "Diesel": {"label": "Dizel", "density_kg_m3": 832.0,
               "vapor_pressure_bar_a": 0.005, "critical_pressure_bar_a": 18.0, "viscosity_pa_s": 0.0024},
    "HeavyFuelOil": {"label": "Agir Yakit Yagi", "density_kg_m3": 960.0,
                     "vapor_pressure_bar_a": 0.001, "critical_pressure_bar_a": 15.0, "viscosity_pa_s": 0.15},
}


@dataclass(frozen=True)
class CompositionSummary:
    basis: str
    total_percent: float
    mole_fractions: dict[str, float]
    mass_fractions: dict[str, float]
    average_molecular_weight: float
    z: float | None
    density_kg_m3: float | None
    viscosity_pa_s: float | None
    cp_j_kgk: float | None
    cv_j_kgk: float | None
    specific_heat_ratio: float | None
    mixture_string: str
    phase: str | None = None
    fallback_used: bool = False
    model_used: str = "unknown"


def _phase_name(phase: Any) -> str:
    phase_map: dict[Any, str] = {
        getattr(CP, "iphase_liquid", 0): "liquid",
        getattr(CP, "iphase_supercritical", 1): "supercritical",
        getattr(CP, "iphase_supercritical_gas", 2): "supercritical_gas",
        getattr(CP, "iphase_supercritical_liquid", 3): "supercritical_liquid",
        getattr(CP, "iphase_gas", 4): "gas",
        getattr(CP, "iphase_twophase", 5): "two_phase",
        getattr(CP, "iphase_critical_point", 6): "critical_point",
    }
    try:
        return phase_map.get(int(phase), "unknown")
    except (ValueError, TypeError):
        return phase_map.get(phase, "unknown")


@lru_cache(maxsize=1)
def list_coolprop_fluids() -> list[str]:
    """Return sorted list of available CoolProp fluid names (cached)."""
    fluids = CP.get_global_param_string("FluidsList").split(",")
    return sorted(fluids)


# ---------------------------------------------------------------------------
# Molecular weight lookup — cascaded: CoolProp → chemicals → 28.96
# ---------------------------------------------------------------------------
@lru_cache(maxsize=512)
def _get_mw_coolprop(fluid: str) -> float | None:
    try:
        return CP.PropsSI("M", fluid) * 1000.0
    except Exception:
        return None


@lru_cache(maxsize=512)
def _get_mw_chemicals(fluid: str) -> float | None:
    if not _HAS_CHEMICALS:
        return None
    try:
        cas = CAS_from_any(fluid)
        if not cas:
            return None
        meta = search_chemical(cas)
        return float(meta.MW) if meta and meta.MW else None
    except Exception:
        return None


def get_molecular_weight(fluid: str) -> float:
    """Return molecular weight [g/mol] with cascade: CoolProp → chemicals → 28.96."""
    mw = _get_mw_coolprop(fluid)
    if mw is not None:
        return mw
    mw = _get_mw_chemicals(fluid)
    if mw is not None:
        return mw
    return 28.96


GAS_COMPONENT_ALIASES: dict[str, str] = {
    "CO2": "CarbonDioxide",
    "CH4": "Methane",
    "C2H6": "Ethane",
    "C3H8": "Propane",
    "C4H10": "Butane",
    "N2": "Nitrogen",
    "O2": "Oxygen",
    "H2": "Hydrogen",
    "H2S": "HydrogenSulfide",
    "CO": "CarbonMonoxide",
    "H2O": "Water",
}


def canonical_gas_component(name: str) -> str:
    stripped = name.strip()
    return GAS_COMPONENT_ALIASES.get(stripped.upper(), stripped)


def _clean_rows(rows: list[dict]) -> list[dict]:
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        fluid = canonical_gas_component(str(row.get("component", "")))
        percent = row.get("fraction_pct", 0.0)
        try:
            percent = float(percent)
        except (TypeError, ValueError):
            continue
        if not fluid:
            continue
        if not math.isfinite(percent) or percent < 0:
            raise ValueError("Yuzdeler sonlu ve negatif olmayan degerler olmalidir.")
        if any(item["component"] == fluid for item in cleaned):
            raise ValueError(f"Ayni bilesen birden fazla kez girilemez: {fluid}")
        cleaned.append({"component": fluid, "fraction_pct": percent})
    if not cleaned:
        raise ValueError("En az bir bilesen girilmelidir.")
    return cleaned


@lru_cache(maxsize=1)
def gas_component_options() -> list[str]:
    """Return CoolProp gas names plus components used by built-in presets."""
    from config import GAS_PRESETS

    options = list(list_coolprop_fluids())
    seen = set(options)
    for preset in GAS_PRESETS.values():
        for row in preset["components"]:
            name = str(row["component"])
            if name not in seen:
                seen.add(name)
                options.append(name)
    for alias in GAS_COMPONENT_ALIASES:
        if alias not in seen:
            seen.add(alias)
            options.append(alias)
    return options


def prepare_composition_rows(rows: list[dict]) -> tuple[list[dict], float]:
    """Validate custom composition rows and normalize positive total to 100%."""
    if not rows:
        raise ValueError("En az bir gaz bileseni girilmelidir.")
    allowed = set(gas_component_options())
    cleaned: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Gaz kompozisyonu satirlari nesne olmalidir.")
        name = canonical_gas_component(str(row.get("component", "")))
        if not name:
            raise ValueError("Bilesen adi bos olamaz.")
        if name not in allowed:
            raise ValueError(f"Bilinmeyen gaz bileseni: {name}")
        if name in seen:
            raise ValueError(f"Ayni bilesen birden fazla kez girilemez: {name}")
        seen.add(name)
        try:
            percent = float(row.get("fraction_pct", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Gecersiz yuzde degeri: {name}") from exc
        if not math.isfinite(percent) or percent < 0.0:
            raise ValueError("Yuzdeler sonlu ve negatif olmayan degerler olmalidir.")
        cleaned.append({"component": name, "fraction_pct": percent})
    total = sum(row["fraction_pct"] for row in cleaned)
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("Gaz kompozisyonu toplami sifirdan buyuk olmalidir.")
    positive = [row for row in cleaned if row["fraction_pct"] > 0.0]
    if not positive:
        raise ValueError("En az bir gaz bileseni pozitif olmalidir.")
    positive_total = sum(row["fraction_pct"] for row in positive)
    normalized = [
        {"component": row["component"], "fraction_pct": row["fraction_pct"] / positive_total * 100.0}
        for row in positive
    ]
    return normalized, total


def normalize_composition(rows: list[dict], basis: str) -> CompositionSummary:
    """Convert mass or molar fractions to a CompositionSummary with mole/mass fractions.

    MW cascade: CoolProp → chemicals → ideal gas (28.96 g/mol).
    """
    cleaned = _clean_rows(rows)
    total_percent = sum(row["fraction_pct"] for row in cleaned)
    if abs(total_percent - 100.0) > 1e-6:
        raise ValueError(f"Toplam kompozisyon 100% olmali. Mevcut toplam: {total_percent:.4f}%")

    basis_key = basis.strip().lower()
    fractions = {row["component"]: row["fraction_pct"] / 100.0 for row in cleaned}

    molar_masses = {}
    for name in fractions:
        mw = _get_mw_coolprop(name)
        if mw is None:
            mw = _get_mw_chemicals(name)
        if mw is None:
            mw = 28.96
        molar_masses[name] = mw

    if basis_key == "molar":
        mole_fractions = fractions
        total_mass = sum(mole_fractions[name] * molar_masses[name] for name in mole_fractions)
        mass_fractions = {
            name: (mole_fractions[name] * molar_masses[name]) / total_mass
            for name in mole_fractions
        }
    elif basis_key == "mass":
        mass_fractions = fractions
        total_moles = sum(mass_fractions[name] / molar_masses[name] for name in mass_fractions)
        mole_fractions = {
            name: (mass_fractions[name] / molar_masses[name]) / total_moles
            for name in mass_fractions
        }
    else:
        raise ValueError("Kompozisyon bazisi 'molar' veya 'mass' olmalidir.")

    average_mw = sum(mole_fractions[name] * molar_masses[name] for name in mole_fractions)
    mixture_string = "&".join(name for name in mole_fractions)

    return CompositionSummary(
        basis=basis_key,
        total_percent=total_percent,
        mole_fractions=mole_fractions,
        mass_fractions=mass_fractions,
        average_molecular_weight=average_mw,
        z=None,
        density_kg_m3=None,
        viscosity_pa_s=None,
        cp_j_kgk=None,
        cv_j_kgk=None,
        specific_heat_ratio=None,
        mixture_string=mixture_string,
    )


# ---------------------------------------------------------------------------
# Gas mixture evaluation — cascaded: CoolProp HEOS → ideal gas
# ---------------------------------------------------------------------------
@lru_cache(maxsize=256)
def _evaluate_mixture_state_heos(
    mixture_string: str,
    mole_fraction_items: tuple[tuple[str, float], ...],
    pressure_bar_a: float,
    temperature_c: float,
) -> dict[str, Any] | None:
    """CoolProp HEOS evaluation. Returns None if the mixture is not supported."""
    try:
        state = CP.AbstractState("HEOS", mixture_string)
        state.set_mole_fractions([frac for _, frac in mole_fraction_items])
        state.update(CP.PT_INPUTS, pressure_bar_a * 1e5, temperature_c + 273.15)
        z = state.compressibility_factor()
        rho = state.rhomass()
        mu = state.viscosity()
        cp = state.cpmass()
        cv = state.cvmass()
        k = (cp / cv) if cv > 0 else None
        phase = _phase_name(state.phase())
        # shortcut: CoolProp mixture phase() flags gas blends as liquid; T_reducing/density heuristic, revisit near-critical blends
        if phase == "liquid" and len(mole_fraction_items) > 1:
            try:
                t_k = temperature_c + 273.15
                if t_k > state.T_reducing() or rho < 0.5 * state.rhomass_reducing():
                    phase = "gas"
            except Exception:
                pass
        return {"z": z, "density_kg_m3": rho, "viscosity_pa_s": mu,
                "cp_j_kgk": cp, "cv_j_kgk": cv, "specific_heat_ratio": k,
                "phase": phase}
    except Exception:
        return None


@lru_cache(maxsize=256)
def _evaluate_mixture_state_fallback(
    average_mw: float,
    pressure_bar_a: float,
    temperature_c: float,
) -> dict[str, Any]:
    """Ideal gas mixture fallback. Uses air-like defaults (k=1.4, Z=1.0)."""
    t_k = temperature_c + 273.15
    p_pa = pressure_bar_a * 1e5
    r = 8314.0
    avg_rho = (p_pa * average_mw) / (r * t_k)
    return {"z": 1.0, "density_kg_m3": avg_rho, "viscosity_pa_s": _gas_viscosity_fallback(t_k),
            "cp_j_kgk": 1000.0, "cv_j_kgk": 714.0, "specific_heat_ratio": 1.4,
            "phase": None}


def evaluate_gas_mixture(
    rows: list[dict],
    basis: str,
    pressure_bar_a: float,
    temperature_c: float,
    gas_model: str = "auto",
) -> CompositionSummary:
    """Return CompositionSummary with Z, k, density, viscosity.

    ``gas_model``: ``auto`` uses HEOS then ideal fallback, ``real`` requires HEOS,
    ``ideal`` uses ideal-gas properties directly.
    """
    model = gas_model.strip().lower()
    if model not in {"auto", "real", "ideal"}:
        raise ValueError("Gaz modeli 'real', 'auto' veya 'ideal' olmalidir.")
    summary = normalize_composition(rows, basis)
    ordered = list(summary.mole_fractions.items())
    mw = summary.average_molecular_weight

    props = None if model == "ideal" else _evaluate_mixture_state_heos(
        summary.mixture_string, tuple(ordered), pressure_bar_a, temperature_c,
    )
    fallback_used = props is None or model == "ideal"
    if props is None:
        if model == "real":
            raise ValueError("Gercek gaz modeli bu karisim icin kullanilamadi; 'auto' veya 'ideal' secin.")
        props = _evaluate_mixture_state_fallback(mw, pressure_bar_a, temperature_c)
    used_model = "ideal" if fallback_used else "heos"
    assert props is not None

    return CompositionSummary(
        basis=summary.basis,
        total_percent=summary.total_percent,
        mole_fractions=summary.mole_fractions,
        mass_fractions=summary.mass_fractions,
        average_molecular_weight=mw,
        z=props["z"],
        density_kg_m3=props["density_kg_m3"],
        viscosity_pa_s=props["viscosity_pa_s"],
        cp_j_kgk=props["cp_j_kgk"],
        cv_j_kgk=props["cv_j_kgk"],
        specific_heat_ratio=props["specific_heat_ratio"],
        mixture_string=summary.mixture_string,
        phase=props.get("phase") if isinstance(props.get("phase"), str) else None,
        fallback_used=fallback_used,
        model_used=used_model,
    )


# ---------------------------------------------------------------------------
# Phase transition & transformation diagnostics (gas condensation / liquid boiling)
# ---------------------------------------------------------------------------
def _pure_gas_sat(fluid: str, p_pa: float) -> dict[str, Any]:
    try:
        pc = CP.PropsSI("PCRIT", fluid)
        if p_pa >= pc:
            tc = CP.PropsSI("TCRIT", fluid) - 273.15
            return {"t_sat_c": tc, "t_bubble_c": tc, "t_dew_c": tc, "is_supercritical": True, "pc_bar_a": pc / 1e5}
        tsat = CP.PropsSI("T", "P", p_pa, "Q", 1.0, fluid) - 273.15
        return {"t_sat_c": tsat, "t_bubble_c": tsat, "t_dew_c": tsat, "is_supercritical": False, "pc_bar_a": pc / 1e5}
    except Exception:
        return {"t_sat_c": None, "t_bubble_c": None, "t_dew_c": None, "is_supercritical": False, "pc_bar_a": None}


def _mixture_gas_sat(mix_str: str, fracs: list[float], p_pa: float, dom_comp: str) -> dict[str, Any]:
    try:
        state = CP.AbstractState("HEOS", mix_str)
        state.set_mole_fractions(fracs)
        state.update(CP.PQ_INPUTS, p_pa, 0)
        tb = state.T() - 273.15
        state.update(CP.PQ_INPUTS, p_pa, 1)
        td = state.T() - 273.15
        return {"t_sat_c": td, "t_bubble_c": tb, "t_dew_c": td, "is_supercritical": False, "pc_bar_a": None}
    except Exception:
        return _pure_gas_sat(dom_comp, p_pa)


def get_gas_saturation_info(
    gas_preset_or_fluid: str,
    pressure_bar_a: float,
    composition: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calculate saturation / bubble / dew point temperatures for gas preset or composition."""
    from config import GAS_PRESETS

    p_pa = max(float(pressure_bar_a) * 1e5, 1000.0)
    if composition:
        cleaned = _clean_rows(composition)
        if len(cleaned) == 1:
            return _pure_gas_sat(cleaned[0]["component"], p_pa)
        mix_str = "&".join(c["component"] for c in cleaned)
        fracs = [c["fraction_pct"] / 100.0 for c in cleaned]
        return _mixture_gas_sat(mix_str, fracs, p_pa, cleaned[0]["component"])

    if gas_preset_or_fluid in GAS_PRESETS:
        comps = GAS_PRESETS[gas_preset_or_fluid]["components"]
        if len(comps) == 1:
            return _pure_gas_sat(comps[0]["component"], p_pa)
        mix_str = "&".join(c["component"] for c in comps)
        fracs = [c["fraction_pct"] / 100.0 for c in comps]
        return _mixture_gas_sat(mix_str, fracs, p_pa, comps[0]["component"])

    return _pure_gas_sat(canonical_gas_component(gas_preset_or_fluid), p_pa)


def evaluate_gas_phase_state(
    gas_preset: str | None,
    pressure_bar_a: float,
    temperature_c: float,
    composition: list[dict[str, Any]] | None = None,
    composition_basis: str = "molar",
    gas_model: str = "auto",
) -> dict[str, Any]:
    """Diagnose thermodynamic phase of gas stream, detect liquefaction/condensation, and provide transition guidance."""
    from config import GAS_PRESETS

    name = gas_preset or "Doğal Gaz"
    comp_rows = composition
    if comp_rows is None and name in GAS_PRESETS:
        comp_rows = GAS_PRESETS[name]["components"]

    summary = None
    if comp_rows:
        with contextlib.suppress(Exception):
            summary = evaluate_gas_mixture(comp_rows, composition_basis, pressure_bar_a, temperature_c, gas_model)

    phase = summary.phase if summary and summary.phase else "gas"
    density = summary.density_kg_m3 if summary else None
    z = summary.z if summary else 1.0

    sat_info = get_gas_saturation_info(name, pressure_bar_a, composition=composition)
    t_sat = sat_info.get("t_sat_c")
    t_bubble = sat_info.get("t_bubble_c")
    t_dew = sat_info.get("t_dew_c")

    if t_bubble is not None and temperature_c <= t_bubble + 0.1:
        is_condensed = True
        is_two_phase = False
    elif t_dew is not None and t_bubble is not None and t_bubble < temperature_c < t_dew:
        is_condensed = False
        is_two_phase = True
    elif phase in ("liquid", "supercritical_liquid"):
        is_condensed = True
        is_two_phase = False
    elif phase == "two_phase":
        is_condensed = False
        is_two_phase = True
    else:
        is_condensed = False
        is_two_phase = False

    is_phase_mismatch = is_condensed or is_two_phase
    is_lng = name in ("Doğal Gaz", "Metan", "NaturalGas", "Methane")
    is_lpg = name in ("Propan", "Propane", "Bütan", "Butane")

    if is_condensed:
        phase_label_tr = "Sıvı (LNG / Yoğuşmuş)" if is_lng else ("Sıvı (LPG / Yoğuşmuş)" if is_lpg else "Sıvı (Yoğuşmuş Gaz)")
        sat_ref = f"{t_sat:.1f} °C" if t_sat is not None else "doyma sıcaklığının"
        dens_str = f" (Yoğunluk: {density:.1f} kg/m³)" if density else ""
        warning_tr = (
            f"⚠️ Faz Dönüşümü: Girilen sıcaklıkta ({temperature_c:.1f} °C) ve {pressure_bar_a:.2f} bar(a) basınçta "
            f"gaz yoğuşarak {phase_label_tr} fazına geçmiştir{dens_str}. Doyma eşiği: {sat_ref}. "
            f"IEC gaz debi formülleri sıvı akışa uygulanamaz; Sıvı Servis sekmesine geçilmelidir."
        )
        target_preset = "LNG" if is_lng else ("Propane" if is_lpg else None)
        action_label = "💧 Sıvı Servisine (LNG) Aktar" if is_lng else (
            "💧 Sıvı Servisine (Propan) Aktar" if is_lpg else "💧 Sıvı Servisine Aktar"
        )
        suggested_action = {
            "target_service": "liquid",
            "preset": target_preset,
            "density_kg_m3": round(density, 1) if density else 430.0,
            "label": action_label,
        }
    elif is_two_phase:
        phase_label_tr = "İki Fazlı (Kısmi Yoğuşma / Damlacık)"
        t_range = f"({t_bubble:.1f} °C < T < {t_dew:.1f} °C)" if (t_bubble is not None and t_dew is not None) else ""
        warning_tr = (
            f"⚠️ İki Fazlı Akış Uyarısı: Akışkan doyma/yoğuşma bölgesindedir {t_range}. "
            f"Oluşan sıvı damlacıkları vana triminde ve boru hattında aşırı erozyon ve titreşime neden olabilir."
        )
        suggested_action = None
    elif sat_info.get("is_supercritical"):
        phase_label_tr = "Süperkritik Akışkan"
        warning_tr = None
        suggested_action = None
    else:
        phase_label_tr = "Gaz (Tek Fazlı)"
        warning_tr = None
        suggested_action = None

    return {
        "phase": phase,
        "phase_label_tr": phase_label_tr,
        "is_condensed": is_condensed,
        "is_two_phase": is_two_phase,
        "is_phase_mismatch": is_phase_mismatch,
        "t_sat_c": t_sat,
        "t_bubble_c": t_bubble,
        "t_dew_c": t_dew,
        "density_kg_m3": density,
        "z": z,
        "warning_tr": warning_tr,
        "suggested_action": suggested_action,
    }


def evaluate_liquid_phase_state(
    p1_bar_a: float,
    vapor_pressure_bar_a: float,
    temperature_c: float | None = None,
) -> dict[str, Any]:
    """Diagnose liquid phase condition, detect boiling/vaporization at inlet."""
    p1 = float(p1_bar_a)
    pv = float(vapor_pressure_bar_a)
    is_boiled = pv >= p1
    if is_boiled:
        temp_note = f" ({temperature_c:.1f} °C)" if temperature_c is not None else ""
        warning_tr = (
            f"⚠️ Faz Uyarısı: Girilen sıcaklıkta{temp_note} buhar basıncı ({pv:.3f} bar) giriş basıncına ({p1:.3f} bar) "
            "eşit veya büyüktür; akışkan vanaya girmeden kaynamıştır. "
            "Tek fazlı sıvı formülleri geçersizdir; Buhar veya Gaz Servis sekmesini kullanınız."
        )
        suggested_action = {
            "target_service": "steam",
            "label": "♨️ Buhar Servisine Aktar",
        }
    else:
        warning_tr = None
        suggested_action = None

    return {
        "is_boiled_at_inlet": is_boiled,
        "is_phase_mismatch": is_boiled,
        "warning_tr": warning_tr,
        "suggested_action": suggested_action,
    }


# ---------------------------------------------------------------------------
# Pure fluid state — cascaded: CoolProp → thermo → chemicals ideal gas → ideal gas
# ---------------------------------------------------------------------------
# iapws integration — IAPWS-IF97 standard for water/steam
# ---------------------------------------------------------------------------
_HAS_IAPWS = False
try:
    from iapws import IAPWS97

    _HAS_IAPWS = True
except ImportError:
    logger.debug("iapws not available; using CoolProp for steam properties.")


def get_steam_properties_iapws(pressure_bar_a: float, temperature_c: float) -> dict[str, Any] | None:
    """Return steam/water properties via IAPWS-IF97.

    Returns None if iapws is not installed or the state point cannot be solved.
    Output keys: density_kg_m3, viscosity_pa_s, cp_kj_kgk, cv_kj_kgk,
                 specific_heat_ratio, z, enthalpy_kj_kg, entropy_kj_kgk,
                 thermal_conductivity_w_mk, phase.
    """
    if not _HAS_IAPWS:
        return None
    try:
        p_mpa = pressure_bar_a / 10.0
        t_k = temperature_c + 273.15
        steam = IAPWS97(P=p_mpa, T=t_k)
        return {
            "density_kg_m3": float(steam.rho),
            "viscosity_pa_s": float(steam.mu),
            "cp_kj_kgk": float(steam.cp),
            "cv_kj_kgk": float(steam.cv),
            "specific_heat_ratio": float(steam.cp_cv),
            "z": float(steam.Z),
            "enthalpy_kj_kg": float(steam.h),
            "entropy_kj_kgk": float(steam.s),
            "thermal_conductivity_w_mk": float(steam.k),
            "phase": str(steam.phase),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# thermo integration — general fluid property correlations
# ---------------------------------------------------------------------------
_HAS_THERMO = False
try:
    from thermo import Chemical as ThermoChemical

    _HAS_THERMO = True
except ImportError:
    logger.debug("thermo not available; falling back to CoolProp + chemicals.")


@lru_cache(maxsize=128)
def get_thermo_fluid_state(fluid: str, pressure_bar_a: float, temperature_c: float) -> dict[str, Any] | None:
    """Return fluid properties via the thermo library.

    Returns None if thermo is not installed or the fluid is not found.
    Output keys: density_kg_m3, viscosity_pa_s, cp_j_kgk,
                 specific_heat_ratio, z, molecular_weight.
    """
    if not _HAS_THERMO:
        return None
    try:
        p_pa = pressure_bar_a * 1e5
        t_k = temperature_c + 273.15
        chem = ThermoChemical(fluid, T=t_k, P=p_pa)
        rho = getattr(chem, "rho", None)
        mu = getattr(chem, "mu", None)
        cp = getattr(chem, "Cp", None)
        z = getattr(chem, "Z", None)
        mw = getattr(chem, "MW", None)
        if rho is None:
            return None
        return {
            "density_kg_m3": float(rho),
            "viscosity_pa_s": float(mu) if mu else 1e-5,
            "cp_kj_kgk": float(cp) if cp else 1.0,
            "specific_heat_ratio": None,
            "z": float(z) if z else 1.0,
            "molecular_weight": float(mw) if mw else 28.96,
            "phase": str(getattr(chem, "phase", "unknown")),
        }
    except Exception:
        return None


@lru_cache(maxsize=256)
def _evaluate_chemicals_state(fluid: str, pressure_bar_a: float, temperature_c: float) -> dict[str, float] | None:
    """Estimate fluid state via chemicals library properties + ideal gas law.

    Provides density from MW + ideal gas, plus critical properties.
    """
    if not _HAS_CHEMICALS:
        return None
    props = _safe_chemical_props(fluid)
    if not props:
        return None
    mw = props.get("mw_g_mol")
    if mw is None:
        return None
    t_k = temperature_c + 273.15
    p_pa = pressure_bar_a * 1e5
    mw_kg_kmol = mw
    r = 8314.0
    rho = (p_pa * mw_kg_kmol) / (r * t_k)
    tc = props.get("tc_k")
    pc = props.get("pc_pa")
    z = 1.0
    if tc and pc and tc > 0 and pc > 0:
        tr = t_k / tc
        pr = p_pa / pc
        if tr < 1.0 or pr > 0.1:
            z = 1.0 + (0.083 - 0.422 / (tr ** 1.6)) * pr / tr
            z = max(z, 0.2)
    return {
        "density_kg_m3": rho,
        "viscosity_pa_s": _gas_viscosity_fallback(t_k),
        "cp_kj_kgk": 1.0,
        "specific_heat_ratio": 1.4,
        "z": z,
        "molecular_weight": mw,
        "phase": "gas (chemicals estimate)",
    }


def _ideal_gas_fallback(fluid: str, pressure_bar_a: float, temperature_c: float) -> dict[str, float]:
    """Ultimate ideal gas fallback. Always returns a valid state."""
    mw = get_molecular_weight(fluid)
    t_k = temperature_c + 273.15
    p_pa = pressure_bar_a * 1e5
    r = 8314.0
    rho = (p_pa * mw) / (r * t_k)
    return {
        "density_kg_m3": rho,
        "vapor_pressure_bar_a": 0.0,
        "viscosity_pa_s": _gas_viscosity_fallback(t_k),
        "cp_j_kgk": 1000.0,
        "cv_j_kgk": 714.0,
        "z": 1.0,
        "molecular_weight": mw,
        "critical_pressure_bar_a": 0.0,
        "specific_heat_ratio": 1.4,
    }


@lru_cache(maxsize=256)
def get_pure_fluid_state(fluid: str, pressure_bar_a: float, temperature_c: float) -> dict[str, float]:
    """Return fluid state with cascade: CoolProp → thermo → chemicals → ideal gas.

    Output keys match the original CoolProp-only function:
    density_kg_m3, vapor_pressure_bar_a, viscosity_pa_s, cp_j_kgk, cv_j_kgk,
    z, molecular_weight, critical_pressure_bar_a, specific_heat_ratio.
    """
    p_pa = pressure_bar_a * 1e5
    t_k = temperature_c + 273.15

    try:
        try:
            vp = float(CP.PropsSI("P", "T", t_k, "Q", 0, fluid) / 1e5)
        except Exception:
            vp = 0.0
        d = CP.PropsSI("D", "P", p_pa, "T", t_k, fluid)
        mu = CP.PropsSI("V", "P", p_pa, "T", t_k, fluid)
        cp = CP.PropsSI("C", "P", p_pa, "T", t_k, fluid)
        cv = CP.PropsSI("O", "P", p_pa, "T", t_k, fluid)
        z = CP.PropsSI("Z", "P", p_pa, "T", t_k, fluid)
        mw = CP.PropsSI("M", fluid) * 1000.0
        pc = CP.PropsSI("PCRIT", fluid) / 1e5
        return {
            "density_kg_m3": d,
            "vapor_pressure_bar_a": vp,
            "viscosity_pa_s": mu,
            "cp_j_kgk": cp,
            "cv_j_kgk": cv,
            "z": z if (z is not None and math.isfinite(z) and z > 0.01) else 1.0,
            "molecular_weight": mw,
            "critical_pressure_bar_a": pc,
            "specific_heat_ratio": (cp / cv) if (cv and cv > 0 and math.isfinite(cp / cv) and 1.0 <= cp / cv <= 3.0) else 1.4,
        }
    except Exception:
        pass

    thermo_state = get_thermo_fluid_state(fluid, pressure_bar_a, temperature_c)
    if thermo_state is not None:
        rho = thermo_state["density_kg_m3"]
        mu = thermo_state["viscosity_pa_s"]
        mw = thermo_state["molecular_weight"]
        cp_kj = thermo_state["cp_kj_kgk"]
        z = thermo_state["z"]
        return {
            "density_kg_m3": rho,
            "vapor_pressure_bar_a": 0.0,
            "viscosity_pa_s": mu,
            "cp_j_kgk": cp_kj * 1000.0,
            "cv_j_kgk": cp_kj * 1000.0 / 1.4,
            "z": z,
            "molecular_weight": mw,
            "critical_pressure_bar_a": 0.0,
            "specific_heat_ratio": 1.4,
        }

    chems_state = _evaluate_chemicals_state(fluid, pressure_bar_a, temperature_c)
    if chems_state is not None:
        rho = chems_state["density_kg_m3"]
        mw = chems_state["molecular_weight"]
        z = chems_state["z"]
        return {
            "density_kg_m3": rho,
            "vapor_pressure_bar_a": 0.0,
            "viscosity_pa_s": _gas_viscosity_fallback(t_k),
            "cp_j_kgk": 1000.0,
            "cv_j_kgk": 714.0,
            "z": z,
            "molecular_weight": mw,
            "critical_pressure_bar_a": 0.0,
            "specific_heat_ratio": 1.4,
        }

    return _ideal_gas_fallback(fluid, pressure_bar_a, temperature_c)


def get_liquid_preset(name: str) -> dict[str, Any]:
    """Return density, vapor_pressure, critical_pressure, viscosity for a preset liquid."""
    if name not in LIQUID_PRESETS:
        raise ValueError(f"Bilinmeyen sivi preset'i: {name}")
    return LIQUID_PRESETS[name].copy()


LIQUID_PRESET_FLUIDS = {
    "Water": "Water",
    "Methanol": "Methanol",
    "Propane": "Propane",
    "Ammonia": "Ammonia",
    "Hydrogen": "Hydrogen",
}


@lru_cache(maxsize=128)
def _evaluate_liquid_preset_cached(name: str, p_rounded: float, t_rounded: float) -> tuple[tuple[str, Any], ...]:
    result = get_liquid_preset(name)
    result["temperature_corrected"] = False
    fluid = LIQUID_PRESET_FLUIDS.get(name)
    if fluid is None:
        return tuple(result.items())
    try:
        with contextlib.suppress(Exception):
            vp = float(CP.PropsSI("P", "T", t_rounded + 273.15, "Q", 0, fluid) / 1e5)
            result["vapor_pressure_bar_a"] = vp
        phase = _phase_name(int(CP.PropsSI("PHASE", "P", p_rounded * 1e5, "T", t_rounded + 273.15, fluid)))
        if phase not in {"liquid", "supercritical_liquid"}:
            result["warning"] = "Seçilen P/T'de akışkan sıvı fazında değil; preset sabit değerleri kullanıldı."
            return tuple(result.items())
        state = get_pure_fluid_state(fluid, p_rounded, t_rounded)
        result.update(
            density_kg_m3=state["density_kg_m3"],
            viscosity_pa_s=state["viscosity_pa_s"],
            vapor_pressure_bar_a=state["vapor_pressure_bar_a"],
            critical_pressure_bar_a=state["critical_pressure_bar_a"] or result["critical_pressure_bar_a"],
            temperature_corrected=True,
        )
    except Exception:
        pass
    return tuple(result.items())


def evaluate_liquid_preset(name: str, pressure_bar_a: float, temperature_c: float) -> dict[str, Any]:
    """Return preset properties, corrected with CoolProp when P/T are in the liquid phase."""
    res = dict(_evaluate_liquid_preset_cached(name, round(pressure_bar_a, 4), round(temperature_c, 3)))
    pv = float(res.get("vapor_pressure_bar_a", 0.0) or 0.0)
    res["phase_diagnostic"] = evaluate_liquid_phase_state(pressure_bar_a, pv, temperature_c)
    return res


@lru_cache(maxsize=128)
def get_saturated_steam_temperature(pressure_bar_a: float) -> float:
    """Return saturation temperature in Celsius for water/steam at given absolute pressure in bar."""
    p = float(pressure_bar_a)
    if p >= 220.64:
        return 373.95
    p_pa = max(p * 1e5, 611.65)
    try:
        return float(CP.PropsSI("T", "P", p_pa, "Q", 1.0, "Water") - 273.15)
    except Exception:
        return 100.0 + 28.0 * math.log(max(p, 0.1))


@lru_cache(maxsize=128)
def get_saturated_steam_pressure(temperature_c: float) -> float:
    """Return saturation pressure in bar(a) for water/steam at given temperature in Celsius."""
    t = float(temperature_c)
    if t >= 373.95:
        return 220.64
    t_k = max(t + 273.15, 273.16)
    try:
        return float(CP.PropsSI("P", "T", t_k, "Q", 1.0, "Water") / 1e5)
    except Exception:
        t_sat_ref = 100.0
        return float(math.exp((t - t_sat_ref) / 28.0))


def evaluate_steam_state(pressure_bar_a: float, temperature_c: float) -> dict[str, Any]:
    """Evaluate thermodynamic phase state of water/steam with superheat margin and erosion warnings."""
    t_sat = get_saturated_steam_temperature(pressure_bar_a)
    delta_t_sh = float(temperature_c) - t_sat
    warnings: list[str] = []

    suggested_action = None
    if delta_t_sh > 2.0:
        phase = "superheated"
        phase_label = f"Kızgın Buhar (ΔT = +{delta_t_sh:.1f} °C)"
        if temperature_c > 400.0:
            warnings.append(
                f"Yüksek sıcaklık ({temperature_c:.1f} °C): Alaşımlı gövde (WC6/WC9) "
                f"ve yüksek sıcaklık grafit salmastra zorunludur."
            )
    elif delta_t_sh < -2.0:
        phase = "wet_steam"
        phase_label = f"Islak Buhar / İki Fazlı (ΔT = {delta_t_sh:.1f} °C)"
        warnings.append(
            f"Islak buhar uyarısı: Sıcaklık doyma değerinin ({t_sat:.1f} °C) altında. "
            f"Yüksek hızlı sıvı damlacıkları vana triminde ve boruda ağır erozyona yol açar!"
        )
        if delta_t_sh < -10.0:
            warnings.append(
                f"⚠️ Faz Uyarısı: Sıcaklık ({temperature_c:.1f} °C) doyma değerinin ({t_sat:.1f} °C) çok altında; "
                "akışkan sıvı su fazına yoğuşmuştur. Sıvı Servis sekmesini kullanınız veya sıcaklığı artırınız."
            )
            suggested_action = {
                "target_service": "liquid",
                "preset": "Water",
                "label": "💧 Sıvı Servisine (Su) Aktar",
            }
    else:
        phase = "saturated"
        phase_label = f"Doymuş Buhar (ΔT = {delta_t_sh:+.1f} °C)"
        warnings.append(
            "Doymuş buhar: Basınç düşüşü kısmi yoğuşmaya neden olabilir. "
            "Sertleştirilmiş trim (Stellite / CoCr) kullanımı tavsiye edilir."
        )

    return {
        "phase": phase,
        "phase_label": phase_label,
        "phase_label_tr": phase_label,
        "t_sat_c": t_sat,
        "delta_t_superheat": delta_t_sh,
        "is_wet": phase in ("wet_steam", "subcooled_liquid") or delta_t_sh < -2.0,
        "is_subcooled_liquid": delta_t_sh < -10.0,
        "is_superheated": phase == "superheated",
        "is_phase_mismatch": phase in ("wet_steam", "subcooled_liquid") or delta_t_sh < -2.0,
        "warnings": warnings,
        "suggested_action": suggested_action,
    }


# ---------------------------------------------------------------------------
# Multicomponent hydrocarbon VLE PT-Flash (Peng-Robinson + Rachford-Rice)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FlashResult:
    """Thermodynamic vapor-liquid equilibrium flash result."""

    temperature_c: float
    pressure_bar_a: float
    beta_vapor_mole_fraction: float
    liquid_mole_fraction: float
    vapor_mass_fraction: float
    liquid_mass_fraction: float
    phase: str
    phase_label_tr: str
    rho_liquid_kg_m3: float | None
    rho_vapor_kg_m3: float | None
    rho_tp_kg_m3: float
    liquid_mole_fractions: dict[str, float]
    vapor_mole_fractions: dict[str, float]
    feed_mole_fractions: dict[str, float]
    molecular_weight_feed: float
    molecular_weight_liquid: float | None
    molecular_weight_vapor: float | None
    method_used: str


HYDROCARBON_CRITICAL_CONSTANTS: dict[str, dict[str, float]] = {
    "Methane": {"tc_k": 190.564, "pc_pa": 45.992e5, "omega": 0.0115, "mw": 16.0425, "rho_l_std": 422.36},
    "Ethane": {"tc_k": 305.32, "pc_pa": 48.72e5, "omega": 0.0995, "mw": 30.07, "rho_l_std": 546.0},
    "Propane": {"tc_k": 369.83, "pc_pa": 42.48e5, "omega": 0.1523, "mw": 44.096, "rho_l_std": 582.0},
    "Butane": {"tc_k": 425.12, "pc_pa": 37.96e5, "omega": 0.2002, "mw": 58.122, "rho_l_std": 601.0},
    "Nitrogen": {"tc_k": 126.192, "pc_pa": 33.958e5, "omega": 0.0372, "mw": 28.0134, "rho_l_std": 808.0},
    "CarbonDioxide": {"tc_k": 304.128, "pc_pa": 73.773e5, "omega": 0.2239, "mw": 44.01, "rho_l_std": 1032.0},
    "Hydrogen": {"tc_k": 33.145, "pc_pa": 12.964e5, "omega": -0.219, "mw": 2.016, "rho_l_std": 70.8},
}

_THERMO_CANONICAL_NAMES: dict[str, str] = {
    "carbondioxide": "carbon dioxide",
    "co2": "carbon dioxide",
    "karbondioksit": "carbon dioxide",
    "methane": "methane",
    "metan": "methane",
    "ethane": "ethane",
    "etan": "ethane",
    "propane": "propane",
    "propan": "propane",
    "butane": "butane",
    "bütan": "butane",
    "nitrogen": "nitrogen",
    "azot": "nitrogen",
    "hydrogen": "hydrogen",
    "hidrojen": "hydrogen",
    "oxygen": "oxygen",
    "oksijen": "oxygen",
    "argon": "argon",
    "helium": "helium",
    "water": "water",
    "su": "water",
}


def _wilson_k_values(components: list[str], pressure_pa: float, temperature_k: float) -> list[float]:
    ks = []
    for comp in components:
        props = HYDROCARBON_CRITICAL_CONSTANTS.get(comp)
        if props:
            tc = props["tc_k"]
            pc = props["pc_pa"]
            omega = props["omega"]
        else:
            tc = get_chemical_property(comp, "tc_k") or 200.0
            pc = get_chemical_property(comp, "pc_pa") or 45e5
            omega = 0.1
        k_val = (pc / pressure_pa) * math.exp(5.373 * (1.0 + omega) * (1.0 - tc / temperature_k))
        ks.append(max(k_val, 1e-12))
    return ks


def _solve_rachford_rice(zs: list[float], ks: list[float]) -> tuple[float, list[float], list[float]]:
    try:
        from chemicals.rachford_rice import Rachford_Rice_solution
        beta, xs, ys = Rachford_Rice_solution(zs=zs, Ks=ks)
        beta = max(0.0, min(1.0, float(beta)))
        return beta, [float(x) for x in xs], [float(y) for y in ys]
    except Exception:
        pass

    sum_zk = sum(z * k for z, k in zip(zs, ks, strict=False))
    if sum_zk <= 1.0:
        return 0.0, list(zs), [z * k / sum_zk for z, k in zip(zs, ks, strict=False)]
    sum_z_over_k = sum(z / k for z, k in zip(zs, ks, strict=False))
    if sum_z_over_k <= 1.0:
        return 1.0, [z / k / sum_z_over_k for z, k in zip(zs, ks, strict=False)], list(zs)

    low, high = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (low + high)
        f_mid = sum(z * (k - 1.0) / (1.0 + mid * (k - 1.0)) for z, k in zip(zs, ks, strict=False))
        if abs(f_mid) < 1e-9:
            break
        if f_mid > 0:
            low = mid
        else:
            high = mid
    beta = 0.5 * (low + high)
    xs = [z / (1.0 + beta * (k - 1.0)) for z, k in zip(zs, ks, strict=False)]
    total_x = sum(xs) or 1.0
    xs = [x / total_x for x in xs]
    ys = [x * k for x, k in zip(xs, ks, strict=False)]
    total_y = sum(ys) or 1.0
    ys = [y / total_y for y in ys]
    return beta, xs, ys


def flash_multicomponent_mixture(
    composition: list[dict[str, Any]] | str,
    pressure_bar_a: float,
    temperature_c: float,
    composition_basis: str = "molar",
) -> FlashResult:
    """Calculate multicomponent VLE PT-flash with Peng-Robinson EOS and Rachford-Rice."""
    from config import GAS_PRESETS

    t_k = temperature_c + 273.15
    p_pa = max(float(pressure_bar_a) * 1e5, 1000.0)

    if isinstance(composition, str):
        rows = (
            GAS_PRESETS[composition]["components"]
            if composition in GAS_PRESETS
            else [{"component": composition, "fraction_pct": 100.0}]
        )
    else:
        rows = composition

    summary = normalize_composition(rows, composition_basis)
    comps = list(summary.mole_fractions.keys())
    zs = [summary.mole_fractions[c] for c in comps]
    mw_feed = summary.average_molecular_weight

    beta = None
    xs, ys = None, None
    rho_l, rho_v = None, None
    method_used = "unknown"

    if _HAS_THERMO:
        try:
            from thermo import Mixture as ThermoMixture
            chem_ids = [_THERMO_CANONICAL_NAMES.get(canonical_gas_component(c).lower(), canonical_gas_component(c).lower()) for c in comps]
            mix = ThermoMixture(IDs=chem_ids, zs=zs, T=t_k, P=p_pa)
            vf = getattr(mix, "V_over_F", None)
            if vf is None:
                vf = getattr(mix, "VF", None)
            if vf is not None:
                beta = max(0.0, min(1.0, float(vf)))
                rho_l = getattr(mix, "rhol", None) or getattr(mix, "rholmass", None)
                rho_v = getattr(mix, "rhog", None) or getattr(mix, "rhogmass", None)
                xs = getattr(mix, "xs", None)
                ys = getattr(mix, "ys", None)
                method_used = "thermo_pr"
        except Exception:
            beta = None

    if beta is None:
        ks = _wilson_k_values(comps, p_pa, t_k)
        beta, xs, ys = _solve_rachford_rice(zs, ks)
        method_used = "rachford_rice_wilson"

    if xs is None or len(xs) != len(comps):
        xs = list(zs)
    if ys is None or len(ys) != len(comps):
        ys = list(zs)

    mws = [get_molecular_weight(c) for c in comps]
    mw_l = sum(x * mw for x, mw in zip(xs, mws, strict=False)) if beta < 1.0 else None
    mw_v = sum(y * mw for y, mw in zip(ys, mws, strict=False)) if beta > 0.0 else None

    if beta <= 1e-6:
        beta = 0.0
        w_v = 0.0
        w_l = 1.0
        phase = "liquid"
        phase_label_tr = "Sıvı (LNG / Yoğuşmuş)"
    elif beta >= 1.0 - 1e-6:
        beta = 1.0
        w_v = 1.0
        w_l = 0.0
        phase = "gas"
        phase_label_tr = "Gaz (Tek Fazlı)"
    else:
        w_v = (beta * (mw_v or mw_feed)) / mw_feed
        w_v = max(0.0, min(1.0, w_v))
        w_l = 1.0 - w_v
        phase = "two_phase"
        phase_label_tr = f"İki Fazlı (%{(1.0 - beta) * 100.0:.1f} Yoğuşma)"

    if rho_v is None:
        rho_v = (p_pa * (mw_v or mw_feed)) / (8314.0 * t_k)

    if rho_l is None:
        rho_l_weighted = sum(
            x * HYDROCARBON_CRITICAL_CONSTANTS.get(c, {}).get("rho_l_std", 500.0)
            for x, c in zip(xs, comps, strict=False)
        )
        rho_l = max(350.0, rho_l_weighted)

    if phase == "liquid":
        rho_tp = float(rho_l)
    elif phase == "gas":
        rho_tp = float(rho_v)
    else:
        rho_tp = 1.0 / (w_v / float(rho_v) + w_l / float(rho_l))

    return FlashResult(
        temperature_c=temperature_c,
        pressure_bar_a=pressure_bar_a,
        beta_vapor_mole_fraction=round(beta, 6),
        liquid_mole_fraction=round(1.0 - beta, 6),
        vapor_mass_fraction=round(w_v, 6),
        liquid_mass_fraction=round(w_l, 6),
        phase=phase,
        phase_label_tr=phase_label_tr,
        rho_liquid_kg_m3=round(float(rho_l), 2) if beta < 1.0 else None,
        rho_vapor_kg_m3=round(float(rho_v), 3) if beta > 0.0 else None,
        rho_tp_kg_m3=round(float(rho_tp), 2),
        liquid_mole_fractions=dict(zip(comps, [round(x, 6) for x in xs], strict=False)),
        vapor_mole_fractions=dict(zip(comps, [round(y, 6) for y in ys], strict=False)),
        feed_mole_fractions=dict(zip(comps, [round(z, 6) for z in zs], strict=False)),
        molecular_weight_feed=round(mw_feed, 4),
        molecular_weight_liquid=round(mw_l, 4) if mw_l is not None else None,
        molecular_weight_vapor=round(mw_v, 4) if mw_v is not None else None,
        method_used=method_used,
    )

