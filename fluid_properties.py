"""Fluid property calculation via CoolProp HEOS + chemicals fallback.

Provides liquid presets (Water, Oil, etc.), gas mixture evaluation
(normalize_composition, evaluate_gas_mixture), single-fluid state
lookups (get_pure_fluid_state, list_coolprop_fluids, get_liquid_preset),
and chemical database helpers via the chemicals library.

All property-lookup functions implement a cascade fallback chain:
  CoolProp/iapws → thermo → chemicals EOS → ideal gas
"""

from __future__ import annotations

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

_CHEMICAL_CACHE: dict[str, dict[str, Any]] = {}


_CHEMICAL_CACHE_MAX = 512

def _safe_chemical_props(name: str) -> dict[str, Any]:
    if name in _CHEMICAL_CACHE:
        return _CHEMICAL_CACHE[name]
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

    if props and len(_CHEMICAL_CACHE) < _CHEMICAL_CACHE_MAX:
        _CHEMICAL_CACHE[name] = props
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


def _clean_rows(rows: list[dict]) -> list[dict]:
    cleaned = []
    for row in rows:
        fluid = str(row.get("component", "")).strip()
        percent = row.get("fraction_pct", 0.0)
        try:
            percent = float(percent)
        except (TypeError, ValueError):
            continue
        if not fluid:
            continue
        if percent < 0:
            raise ValueError("Yuzdeler negatif olamaz.")
        cleaned.append({"component": fluid, "fraction_pct": percent})
    if not cleaned:
        raise ValueError("En az bir bilesen girilmelidir.")
    return cleaned


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
) -> dict[str, float | None] | None:
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
        return {"z": z, "density_kg_m3": rho, "viscosity_pa_s": mu,
                "cp_j_kgk": cp, "cv_j_kgk": cv, "specific_heat_ratio": k}
    except Exception:
        return None


@lru_cache(maxsize=256)
def _evaluate_mixture_state_fallback(
    average_mw: float,
    pressure_bar_a: float,
    temperature_c: float,
) -> dict[str, float | None]:
    """Ideal gas mixture fallback. Uses air-like defaults (k=1.4, Z=1.0)."""
    t_k = temperature_c + 273.15
    p_pa = pressure_bar_a * 1e5
    r = 8314.0
    avg_rho = (p_pa * average_mw) / (r * t_k)
    return {"z": 1.0, "density_kg_m3": avg_rho, "viscosity_pa_s": _gas_viscosity_fallback(t_k),
            "cp_j_kgk": 1000.0, "cv_j_kgk": 714.0, "specific_heat_ratio": 1.4}


def evaluate_gas_mixture(
    rows: list[dict], basis: str, pressure_bar_a: float, temperature_c: float,
) -> CompositionSummary:
    """Return CompositionSummary with Z, k, density, viscosity.

    Cascade: CoolProp HEOS → ideal gas mixture.
    """
    summary = normalize_composition(rows, basis)
    ordered = list(summary.mole_fractions.items())
    mw = summary.average_molecular_weight

    props = _evaluate_mixture_state_heos(
        summary.mixture_string, tuple(ordered), pressure_bar_a, temperature_c,
    )
    if props is None:
        props = _evaluate_mixture_state_fallback(mw, pressure_bar_a, temperature_c)

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
    )


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
        return {
            "density_kg_m3": CP.PropsSI("D", "P", p_pa, "T", t_k, fluid),
            "vapor_pressure_bar_a": CP.PropsSI("P", "T", t_k, "Q", 0, fluid) / 1e5,
            "viscosity_pa_s": CP.PropsSI("V", "P", p_pa, "T", t_k, fluid),
            "cp_j_kgk": CP.PropsSI("C", "P", p_pa, "T", t_k, fluid),
            "cv_j_kgk": CP.PropsSI("O", "P", p_pa, "T", t_k, fluid),
            "z": CP.PropsSI("Z", "P", p_pa, "T", t_k, fluid),
            "molecular_weight": CP.PropsSI("M", fluid) * 1000.0,
            "critical_pressure_bar_a": CP.PropsSI("PCRIT", fluid) / 1e5,
            "specific_heat_ratio": (
                CP.PropsSI("C", "P", p_pa, "T", t_k, fluid)
                / CP.PropsSI("O", "P", p_pa, "T", t_k, fluid)
            ),
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

    if delta_t_sh > 2.0:
        phase = "superheated"
        phase_label = f"K\u0131zg\u0131n Buhar (\u0394T = +{delta_t_sh:.1f} \u00b0C)"
        if temperature_c > 400.0:
            warnings.append(
                f"Y\u00fcksek s\u0131cakl\u0131k ({temperature_c:.1f} \u00b0C): Ala\u015f\u0131ml\u0131 g\u00f6vde (WC6/WC9) "
                f"ve y\u00fcksek s\u0131cakl\u0131k grafit salmastra zorunludur."
            )
    elif delta_t_sh < -2.0:
        phase = "wet_steam"
        phase_label = f"\u0130slak Buhar / \u0130ki Fazl\u0131 (\u0394T = {delta_t_sh:.1f} \u00b0C)"
        warnings.append(
            f"\u0130slak buhar uyar\u0131s\u0131: S\u0131cakl\u0131k doyma de\u011ferinin ({t_sat:.1f} \u00b0C) alt\u0131nda. "
            f"Y\u00fcksek h\u0131zl\u0131 s\u0131v\u0131 damlac\u0131klar\u0131 vana triminde ve boruda a\u011f\u0131r erozyona yol a\u00e7ar!"
        )
    else:
        phase = "saturated"
        phase_label = f"Doymu\u015f Buhar (\u0394T = {delta_t_sh:+.1f} \u00b0C)"
        warnings.append(
            "Doymu\u015f buhar: Bas\u0131n\u00e7 d\u00fc\u015f\u00fc\u015f\u00fc k\u0131smi yo\u011fu\u015fmaya neden olabilir. "
            "Sertle\u015ftirilmi\u015f trim (Stellite / CoCr) kullan\u0131m\u0131 tavsiye edilir."
        )

    return {
        "phase": phase,
        "phase_label": phase_label,
        "t_sat_c": t_sat,
        "delta_t_superheat": delta_t_sh,
        "is_wet": phase == "wet_steam",
        "is_superheated": phase == "superheated",
        "warnings": warnings,
    }

