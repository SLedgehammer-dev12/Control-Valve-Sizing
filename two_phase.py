"""Two-phase flow estimation for control valve flashing / cavitation analysis.

Provides simplified homogeneous equilibrium model (HEM) for two-phase
density estimation, flashing detection, and cavitation index calculation.
"""

from __future__ import annotations


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
    """Cavitation index (sigma) per IEC 60534-8-4.

    sigma = (P1 - Pv) / (P1 - P2)

    sigma > 1.0 : no cavitation
    0.5 < sigma < 1.0 : incipient cavitation
    sigma < 0.5 : full cavitation / flashing

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


def cavitation_severity(sigma: float) -> str:
    """Classify cavitation severity from cavitation index.

    Parameters
    ----------
    sigma : Cavitation index [-]

    Returns
    -------
    Severity label string.
    """
    if sigma >= 1.0:
        return "No cavitation"
    if sigma >= 0.7:
        return "Incipient cavitation"
    if sigma >= 0.5:
        return "Moderate cavitation"
    if sigma >= 0.3:
        return "Severe cavitation"
    return "Flashing / fully developed cavitation"


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
) -> float:
    """Estimate flashed vapor fraction for adiabatic flashing across a valve.

    Simplified energy balance: x = Cp_l * (T_sat_in - T_sat_out) / h_fg

    Parameters
    ----------
    inlet_pressure_bar : Inlet pressure [bar(a)]
    outlet_pressure_bar : Outlet pressure [bar(a)]
    inlet_temperature_c : Inlet liquid temperature [C]
    liquid_cp_j_kgk : Liquid specific heat [J/kgK]
    h_vap_j_kg : Latent heat of vaporization [J/kg]

    Returns
    -------
    Flashed vapor fraction [0-1]. Returns 0.0 if no flashing expected.
    """
    if outlet_pressure_bar >= inlet_pressure_bar:
        return 0.0
    delta_p = inlet_pressure_bar - outlet_pressure_bar
    delta_t_sat = delta_p * 2.0
    t_sat_out = inlet_temperature_c - delta_t_sat
    if t_sat_out >= inlet_temperature_c:
        return 0.0
    if h_vap_j_kg <= 0:
        return 0.0
    x = liquid_cp_j_kgk * (inlet_temperature_c - t_sat_out) / h_vap_j_kg
    return max(0.0, min(x, 1.0))
