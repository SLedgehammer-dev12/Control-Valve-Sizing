"""Two-phase flow estimation for control valve flashing / cavitation analysis.

Provides simplified homogeneous equilibrium model (HEM) for two-phase
density estimation, flashing detection, and cavitation index calculation.
"""

from __future__ import annotations

import math


def flashing_check(
    _inlet_pressure_bar: float,
    outlet_pressure_bar: float,
    vapor_pressure_bar: float,
) -> bool:
    """Check if flashing is expected based on outlet vs vapor pressure.

    Flashing occurs when P2 < Psat.

    Parameters
    ----------
    inlet_pressure_bar : Inlet pressure [bar(a)]
    outlet_pressure_bar : Outlet pressure [bar(a)]
    vapor_pressure_bar : Fluid vapor pressure at inlet temperature [bar(a)]

    Returns
    -------
    True if outlet pressure is below vapor pressure (flashing expected).
    """
    return outlet_pressure_bar < vapor_pressure_bar


def cavitation_index(
    inlet_pressure_bar: float,
    outlet_pressure_bar: float,
    vapor_pressure_bar: float,
) -> float:
    """Classic incipient cavitation index (sigma).

    sigma = (P1 - Pv) / (P1 - P2)

    sigma > 1.0 : no cavitation
    0.5 < sigma < 1.0 : incipient cavitation
    sigma < 0.5 : full cavitation / flashing

    Note: IEC 60534-8-4 expresses the same quantity as xFz = 1/sigma;
    use `xfz_cavitation_factor` for the IEC notation.

    Parameters
    ----------
    inlet_pressure_bar : Inlet pressure [bar(a)]
    outlet_pressure_bar : Outlet pressure [bar(a)]
    vapor_pressure_bar : Fluid vapor pressure at inlet temperature [bar(a)]

    Returns
    -------
    Cavitation index [-]. Returns inf if DeltaP = 0.
    """
    delta_p = inlet_pressure_bar - outlet_pressure_bar
    if delta_p <= 0:
        return float("inf")
    return (inlet_pressure_bar - vapor_pressure_bar) / delta_p


def xfz_cavitation_factor(
    inlet_pressure_bar: float,
    outlet_pressure_bar: float,
    vapor_pressure_bar: float,
) -> float:
    """Cavitation factor xFz per IEC 60534-8-4.

    xFz = (P1 - P2) / (P1 - Pv) = 1 / sigma

    xFz < 1.0 indicates potential cavitation (values approaching 1.0 from
    below imply incipient cavitation; small xFz implies severe cavitation).

    Parameters
    ----------
    inlet_pressure_bar : Inlet pressure [bar(a)]
    outlet_pressure_bar : Outlet pressure [bar(a)]
    vapor_pressure_bar : Fluid vapor pressure at inlet temperature [bar(a)]

    Returns
    -------
    IEC cavitation factor [-]. Returns 0.0 if no pressure drop or at vapor
    pressure equilibrium.
    """
    numerator = inlet_pressure_bar - outlet_pressure_bar
    denominator = inlet_pressure_bar - vapor_pressure_bar
    if denominator <= 0 or numerator <= 0:
        return 0.0
    return numerator / denominator


def cavitation_severity(sigma: float) -> str:
    """Classify cavitation severity from cavitation index.

    Parameters
    ----------
    sigma : Cavitation index [-]

    Returns
    -------
    Severity label string (Turkish).
    """
    if sigma >= 1.0:
        return "Kavitasyon yok"
    if sigma >= 0.7:
        return "Hafif kavitasyon"
    if sigma >= 0.5:
        return "Orta kavitasyon"
    if sigma >= 0.3:
        return "Siddetli kavitasyon"
    return "Flashing / tam kavitasyon"


def two_phase_density_homogeneous(
    quality_x: float,
    rho_liquid_kg_m3: float,
    rho_gas_kg_m3: float,
) -> float:
    """Homogeneous equilibrium model (HEM) two-phase density.

    1/rho_tp = x/rho_g + (1-x)/rho_l

    Parameters
    ----------
    quality_x : Mass fraction of gas (vapor quality) [0-1]
    rho_liquid_kg_m3 : Liquid phase density [kg/m3]
    rho_gas_kg_m3 : Gas/vapor phase density [kg/m3]

    Returns
    -------
    Homogeneous two-phase density [kg/m3].
    """
    if quality_x <= 0.0:
        return rho_liquid_kg_m3
    if quality_x >= 1.0:
        return rho_gas_kg_m3
    return 1.0 / (quality_x / rho_gas_kg_m3 + (1.0 - quality_x) / rho_liquid_kg_m3)


def two_phase_viscosity_homogeneous(
    quality_x: float,
    mu_liquid_pa_s: float,
    mu_gas_pa_s: float,
) -> float:
    """Homogeneous two-phase viscosity (mass-weighted average).

    Parameters
    ----------
    quality_x : Mass fraction of gas (vapor quality) [0-1]
    mu_liquid_pa_s : Liquid dynamic viscosity [Pa*s]
    mu_gas_pa_s : Gas dynamic viscosity [Pa*s]

    Returns
    -------
    Homogeneous two-phase viscosity [Pa*s].
    """
    return quality_x * mu_gas_pa_s + (1.0 - quality_x) * mu_liquid_pa_s


def flash_fraction(
    inlet_pressure_bar: float,
    outlet_pressure_bar: float,
    inlet_temperature_c: float,
    liquid_cp_j_kgk: float,
    h_vap_j_kg: float,
    gas_constant_kj_kgk: float = 0.4615,
) -> float:
    """Estimate flashed vapor fraction for adiabatic flashing across a valve.

    Uses Clausius-Clapeyron to estimate saturation temperature drop,
    then energy balance: x = Cp_l * DeltaT_sat / h_fg.

    Parameters
    ----------
    inlet_pressure_bar : Inlet pressure [bar(a)]
    outlet_pressure_bar : Outlet pressure [bar(a)]
    inlet_temperature_c : Inlet liquid temperature [C]
    liquid_cp_j_kgk : Liquid specific heat [J/kgK]
    h_vap_j_kg : Latent heat of vaporization [J/kg]
    gas_constant_kj_kgk : Fluid-specific gas constant [kJ/(kg*K)].
        Default 0.4615 = water (R/M = 8.314/18.015).
        For hydrocarbons: ~0.143 kJ/(kg·K) (R/M = 8.314/58).

    Returns
    -------
    Flashed vapor fraction [0-1]. Returns 0.0 if no flashing expected.
    """
    if outlet_pressure_bar >= inlet_pressure_bar:
        return 0.0
    if h_vap_j_kg <= 0:
        return 0.0
    t_k = inlet_temperature_c + 273.15
    r_kj_kgk = max(gas_constant_kj_kgk, 0.01)
    p_avg_bar = max((inlet_pressure_bar + outlet_pressure_bar) / 2.0, 0.01)
    dtdp = (r_kj_kgk * t_k * t_k) / (p_avg_bar * 1e2 * h_vap_j_kg * 1e-3)
    delta_p_bar = inlet_pressure_bar - outlet_pressure_bar
    delta_t_sat = dtdp * delta_p_bar
    t_sat_out = inlet_temperature_c - delta_t_sat
    if t_sat_out >= inlet_temperature_c:
        return 0.0
    x = liquid_cp_j_kgk * delta_t_sat / h_vap_j_kg
    return max(0.0, min(x, 1.0))


def vapor_density_ideal_gas(
    pressure_bar: float,
    temperature_c: float,
    molecular_weight: float,
) -> float:
    """Ideal-gas vapor density [kg/m3] at the given state."""
    t_k = temperature_c + 273.15
    if t_k <= 0:
        return 0.0
    return (pressure_bar * 1e5 * molecular_weight * 0.001) / (8.314 * t_k)


def flashing_cv_estimate(
    liquid_cv: float,
    quality_x: float,
    rho_liquid_kg_m3: float,
    rho_gas_kg_m3: float,
) -> float:
    """Two-phase Cv estimate for flashing service.

    Mass flow is conserved; after flashing the volumetric flow grows by
    rho_l/rho_tp while the effective SG drops to rho_tp/rho_water, so the
    required Cv scales as sqrt(rho_l/rho_tp) relative to the single-phase
    liquid Cv (homogeneous equilibrium model).

    Parameters
    ----------
    liquid_cv : Single-phase liquid Cv for the same mass flow [-]
    quality_x : Flashed vapor fraction [0-1]
    rho_liquid_kg_m3 : Liquid density [kg/m3]
    rho_gas_kg_m3 : Vapor density at outlet conditions [kg/m3]

    Returns
    -------
    Estimated two-phase Cv (>= liquid Cv). Returns liquid_cv unchanged when
    the inputs are degenerate.
    """
    if liquid_cv <= 0:
        return 0.0
    rho_tp = two_phase_density_homogeneous(quality_x, rho_liquid_kg_m3, rho_gas_kg_m3)
    if rho_tp <= 0:
        return liquid_cv
    return liquid_cv * math.sqrt(rho_liquid_kg_m3 / rho_tp)
