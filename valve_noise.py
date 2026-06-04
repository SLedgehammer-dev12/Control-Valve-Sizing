"""Control valve noise prediction — IEC 60534-8-4:2015 (liquid) and IEC 60534-8-3:2011 (gas/steam).

Wraps fluids.control_valve.control_valve_noise_l_2015 and
fluids.control_valve.control_valve_noise_g_2011 for the project's
SizingResult + input dataclass interface.
"""

from __future__ import annotations

import logging

from fluids.control_valve import control_valve_noise_g_2011, control_valve_noise_l_2015

logger = logging.getLogger(__name__)


def predict_noise_liquid(
    flow_kg_s: float,
    inlet_pressure_pa: float,
    outlet_pressure_pa: float,
    vapor_pressure_pa: float | None,
    density_kg_m3: float,
    speed_of_sound_m_s: float | None,
    kv: float,
    valve_diameter_m: float,
    pipe_diameter_m: float,
    fl: float,
    fd: float,
    pipe_wall_thickness_m: float = 0.006,
    xfz: float | None = None,
) -> float:
    """Predict liquid valve noise per IEC 60534-8-4:2015.

    Parameters
    ----------
    flow_kg_s : Mass flow rate [kg/s]
    inlet_pressure_pa : Inlet pressure [Pa]
    outlet_pressure_pa : Outlet pressure [Pa]
    vapor_pressure_pa : Saturation (vapor) pressure at inlet temperature [Pa].
        Set to 0.0 if unknown (non-flashing service).
    density_kg_m3 : Liquid density [kg/m3]
    speed_of_sound_m_s : Speed of sound in liquid [m/s].
        If None, uses 1400 m/s as typical for water.
    kv : Valve flow coefficient Kv [m3/h]
    valve_diameter_m : Valve diameter [m]
    pipe_diameter_m : Pipe internal diameter [m]
    fl : Liquid pressure recovery factor [-]
    fd : Valve style modifier [-]
    pipe_wall_thickness_m : Pipe wall thickness [m] (default 6 mm)
    xfz : Cavitation factor (optional, per IEC)

    Returns
    -------
    Sound pressure level [dB(A)] at 1 m downstream.
    """
    pv = vapor_pressure_pa if vapor_pressure_pa is not None else 0.0
    c = speed_of_sound_m_s if speed_of_sound_m_s is not None else 1400.0

    return control_valve_noise_l_2015(
        m=flow_kg_s,
        P1=inlet_pressure_pa,
        P2=outlet_pressure_pa,
        Psat=pv,
        rho=density_kg_m3,
        c=c,
        Kv=kv,
        d=valve_diameter_m,
        Di=pipe_diameter_m,
        FL=fl,
        Fd=fd,
        t_pipe=pipe_wall_thickness_m,
        xFz=xfz,
    )


def predict_noise_gas(
    flow_kg_s: float,
    inlet_pressure_pa: float,
    outlet_pressure_pa: float,
    inlet_temperature_k: float,
    density_kg_m3: float,
    specific_heat_ratio: float,
    molecular_weight: float,
    kv: float,
    valve_diameter_m: float,
    pipe_diameter_m: float,
    fd: float,
    fl: float,
    pipe_wall_thickness_m: float = 0.006,
    flp: float | None = None,
    fp: float | None = None,
) -> float:
    """Predict gas/steam valve noise per IEC 60534-8-3:2011.

    Parameters
    ----------
    flow_kg_s : Mass flow rate [kg/s]
    inlet_pressure_pa : Inlet pressure [Pa]
    outlet_pressure_pa : Outlet pressure [Pa]
    inlet_temperature_k : Inlet temperature [K]
    density_kg_m3 : Gas density at inlet [kg/m3]
    specific_heat_ratio : Cp/Cv [-]
    molecular_weight : Molecular weight [g/mol]
    kv : Valve flow coefficient Kv [m3/h]
    valve_diameter_m : Valve diameter [m]
    pipe_diameter_m : Pipe internal diameter [m]
    fd : Valve style modifier [-]
    fl : Liquid pressure recovery factor [-]
    pipe_wall_thickness_m : Pipe wall thickness [m] (default 6 mm)
    flp : FL with piping factors (optional)
    fp : Piping geometry factor (optional)

    Returns
    -------
    Sound pressure level [dB(A)] at 1 m downstream.
    """
    return control_valve_noise_g_2011(
        m=flow_kg_s,
        P1=inlet_pressure_pa,
        P2=outlet_pressure_pa,
        T1=inlet_temperature_k,
        rho=density_kg_m3,
        gamma=specific_heat_ratio,
        MW=molecular_weight,
        Kv=kv,
        d=valve_diameter_m,
        Di=pipe_diameter_m,
        t_pipe=pipe_wall_thickness_m,
        Fd=fd,
        FL=fl,
        FLP=flp,
        FP=fp,
    )
