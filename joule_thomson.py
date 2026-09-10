"""Joule-Thomson isenthalpic expansion and hydrate formation analysis.

Calculates downstream temperature T2, Joule-Thomson coefficient mu_JT,
natural gas hydrate equilibrium temperature via Towler-Mokhatab (2005),
and minimum preheater temperature requirements to prevent freezing/clathrate formation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from CoolProp.CoolProp import PropsSI


@dataclass(frozen=True)
class JouleThomsonResult:
    """Result of Joule-Thomson expansion and hydrate risk evaluation."""

    fluid: str
    p1_bar_a: float
    p2_bar_a: float
    t1_c: float
    t2_c: float
    delta_t_c: float
    mu_jt_c_per_bar: float
    t_hydrate_c: float
    hydrate_risk: bool
    freezing_risk: bool
    t_preheat_min_c: float
    warnings: list[str]
    summary: str


def natural_gas_hydrate_temperature(pressure_bar_a: float, specific_gravity: float = 0.60) -> float:
    """Estimate hydrate equilibrium temperature in Celsius per Towler & Mokhatab (2005).

    Applicable for natural gas streams (0.55 <= SG <= 0.75) up to 150 bar.
    """
    p_psia = max(float(pressure_bar_a) * 14.50377, 14.696)
    sg = max(float(specific_gravity), 0.55)
    ln_p = math.log(p_psia)
    ln_sg = math.log(sg)
    t_f = 13.47 * ln_p + 34.27 * ln_sg - 1.675 * (ln_p * ln_sg) - 20.35
    return (t_f - 32.0) * 5.0 / 9.0


def _resolve_coolprop_fluid_name(fluid: str) -> str:
    f_clean = fluid.strip()
    mapping = {
        "Methane": "Methane",
        "NaturalGas": "Methane",
        "Dogalgaz": "Methane",
        "Doğalgaz": "Methane",
        "Nitrogen": "Nitrogen",
        "Azot": "Nitrogen",
        "Oxygen": "Oxygen",
        "Oksijen": "Oxygen",
        "Hydrogen": "Hydrogen",
        "Hidrojen": "Hydrogen",
        "CarbonDioxide": "CarbonDioxide",
        "CO2": "CarbonDioxide",
        "Air": "Air",
        "Hava": "Air",
        "Argon": "Argon",
        "Helium": "Helium",
        "Propane": "Propane",
        "Propan": "Propane",
        "Ethane": "Ethane",
        "Etan": "Ethane",
        "Butane": "Butane",
        "Bütan": "Butane",
    }
    return mapping.get(f_clean, f_clean)


def _calc_isenthalpic_t2(cp_fluid: str, p1_pa: float, p2_pa: float, t1_k: float) -> float:
    try:
        h1 = PropsSI("H", "P", p1_pa, "T", t1_k, cp_fluid)
        t2_k = PropsSI("T", "P", p2_pa, "H", h1, cp_fluid)
        return float(t2_k)
    except Exception:
        dp_bar = (p1_pa - p2_pa) / 1e5
        mu_approx = 0.45 if cp_fluid.lower() in ("methane", "naturalgas") else 0.20
        return t1_k - (mu_approx * dp_bar)


def calc_joule_thomson_drop(
    fluid: str,
    p1_bar_a: float,
    p2_bar_a: float,
    t1_c: float,
    specific_gravity: float = 0.60,
) -> JouleThomsonResult:
    """Calculate Joule-Thomson expansion temperature change and hydrate risk."""
    if p1_bar_a <= p2_bar_a:
        raise ValueError(f"Giriş basıncı ({p1_bar_a} bar) çıkış basıncından ({p2_bar_a} bar) büyük olmalıdır.")
    if p2_bar_a <= 0.0:
        raise ValueError(f"Çıkış basıncı ({p2_bar_a} bar) sıfırdan büyük olmalıdır.")

    p1_pa = float(p1_bar_a) * 1e5
    p2_pa = float(p2_bar_a) * 1e5
    t1_k = float(t1_c) + 273.15
    dp_bar = float(p1_bar_a - p2_bar_a)

    cp_fluid = _resolve_coolprop_fluid_name(fluid)
    t2_k = _calc_isenthalpic_t2(cp_fluid, p1_pa, p2_pa, t1_k)
    t2_c = t2_k - 273.15
    delta_t_c = t1_c - t2_c
    mu_jt = delta_t_c / dp_bar if dp_bar > 0 else 0.0

    t_hyd = natural_gas_hydrate_temperature(p2_bar_a, specific_gravity)

    is_hydrocarbon = cp_fluid.lower() in ("methane", "naturalgas", "ethane", "propane", "butane")
    hydrate_risk = is_hydrocarbon and (t2_c <= (t_hyd + 3.0))
    freezing_risk = t2_c <= 0.0

    warnings: list[str] = []
    if delta_t_c < -0.1:
        warnings.append(
            f"Ters J-T etkisi: Gaz genle\u015fme s\u0131ras\u0131nda {abs(delta_t_c):.1f} \u00b0C \u0131s\u0131nd\u0131 (inversiyon b\u00f6lgesi)."
        )
    elif delta_t_c > 30.0:
        warnings.append(
            f"A\u015f\u0131r\u0131 so\u011fuma: \u0394T_JT = {delta_t_c:.1f} \u00b0C. Malzeme gevrekle\u015fmesi riski!"
        )

    if hydrate_risk:
        warnings.append(
            f"Gaz hidrat (kristalle\u015fme) riski! \u00c7\u0131k\u0131\u015f s\u0131cakl\u0131\u011f\u0131 ({t2_c:.1f} \u00b0C) "
            f"hidrat s\u0131cakl\u0131\u011f\u0131na ({t_hyd:.1f} \u00b0C) \u00e7ok yak\u0131n veya alt\u0131nda."
        )

    if freezing_risk:
        warnings.append(
            f"Donma riski: Vana \u00e7\u0131k\u0131\u015f s\u0131cakl\u0131\u011f\u0131 {t2_c:.1f} \u00b0C <= 0 \u00b0C. "
            f"Boru hatt\u0131nda buzlanma ve t\u0131kanma tehlikesi!"
        )

    target_t2 = max(t_hyd + 5.0, 5.0) if is_hydrocarbon else 5.0
    t_preheat_min = target_t2 + delta_t_c if (hydrate_risk or freezing_risk) else t1_c

    summary_parts = [
        f"Giri\u015f: {t1_c:.1f} \u00b0C, \u00c7\u0131k\u0131\u015f: {t2_c:.1f} \u00b0C "
        f"(\u0394T_JT: -{delta_t_c:.1f} \u00b0C, \u03bc_JT: {mu_jt:.3f} \u00b0C/bar)."
    ]
    if hydrate_risk or freezing_risk:
        summary_parts.append(f"Ön ısıtıcı tavsiyesi: Giriş sıcaklığı en az {t_preheat_min:.1f} °C olmalıdır.")

    return JouleThomsonResult(
        fluid=fluid,
        p1_bar_a=p1_bar_a,
        p2_bar_a=p2_bar_a,
        t1_c=t1_c,
        t2_c=t2_c,
        delta_t_c=delta_t_c,
        mu_jt_c_per_bar=mu_jt,
        t_hydrate_c=t_hyd,
        hydrate_risk=hydrate_risk,
        freezing_risk=freezing_risk,
        t_preheat_min_c=t_preheat_min,
        warnings=warnings,
        summary=" ".join(summary_parts),
    )
