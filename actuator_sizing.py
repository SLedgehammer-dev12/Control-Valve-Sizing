"""Pneumatic actuator sizing for control valves.

Calculates required thrust/force for globe and rotary valves
based on pressure class, seat diameter, shutoff requirement,
and actuator supply pressure.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Any


@dataclass(frozen=True)
class ActuatorDefinition:
    """Catalog definition for a pneumatic actuator."""
    manufacturer: str
    model: str
    piston_diameter_mm: float
    spring_range_bar: tuple[float, float]
    supply_bar: float
    thrust_open_n: float
    thrust_close_n: float
    stroke_mm: float


ACTUATOR_CATALOG: dict[str, ActuatorDefinition] = {
    "DA-100": ActuatorDefinition(
        manufacturer="Generic", model="DA-100",
        piston_diameter_mm=100.0, spring_range_bar=(0.2, 1.0),
        supply_bar=4.0, thrust_open_n=1800.0, thrust_close_n=1200.0,
        stroke_mm=20.0,
    ),
    "DA-150": ActuatorDefinition(
        manufacturer="Generic", model="DA-150",
        piston_diameter_mm=150.0, spring_range_bar=(0.2, 1.0),
        supply_bar=4.0, thrust_open_n=4500.0, thrust_close_n=3000.0,
        stroke_mm=30.0,
    ),
    "DA-200": ActuatorDefinition(
        manufacturer="Generic", model="DA-200",
        piston_diameter_mm=200.0, spring_range_bar=(0.2, 1.0),
        supply_bar=4.0, thrust_open_n=8000.0, thrust_close_n=5500.0,
        stroke_mm=40.0,
    ),
    "DA-250": ActuatorDefinition(
        manufacturer="Generic", model="DA-250",
        piston_diameter_mm=250.0, spring_range_bar=(0.2, 1.0),
        supply_bar=5.0, thrust_open_n=14000.0, thrust_close_n=9500.0,
        stroke_mm=50.0,
    ),
    "DA-350": ActuatorDefinition(
        manufacturer="Generic", model="DA-350",
        piston_diameter_mm=350.0, spring_range_bar=(0.2, 1.0),
        supply_bar=5.0, thrust_open_n=28000.0, thrust_close_n=19000.0,
        stroke_mm=75.0,
    ),
}


def get_actuator_options() -> list[str]:
    """Return sorted list of available actuator model keys."""
    return sorted(ACTUATOR_CATALOG.keys())


def get_actuator_definition(key: str) -> ActuatorDefinition:
    """Return ActuatorDefinition for a given model key."""
    if key not in ACTUATOR_CATALOG:
        raise KeyError(f"Aktorator bulunamadi: {key}")
    return ACTUATOR_CATALOG[key]


def estimate_valve_stroke_mm(valve_dn_mm: int) -> float:
    """Estimate typical control valve rated travel/stroke [mm] from nominal diameter."""
    if valve_dn_mm <= 25:
        return 19.0
    if valve_dn_mm <= 50:
        return 29.0
    if valve_dn_mm <= 100:
        return 38.0
    if valve_dn_mm <= 200:
        return 51.0
    return 76.0


def required_thrust_unbalance(
    port_diameter_mm: float,
    inlet_pressure_bar: float,
    outlet_pressure_bar: float,
    seat_diameter_mm: float | None = None,
) -> float:
    """Calculate static unbalance thrust from fluid pressure.

    For globe valves, the unbalanced force is the pressure drop
    acting on the seat area:
        F_unb = (P1 - P2) * A_seat

    Parameters
    ----------
    port_diameter_mm : Valve port diameter [mm]
    inlet_pressure_bar : Inlet pressure [bar(a)]
    outlet_pressure_bar : Outlet pressure [bar(a)]
    seat_diameter_mm : Seat diameter [mm] (defaults to port_diameter)

    Returns
    -------
    Required thrust to overcome static unbalance [N].
    """
    d_mm = seat_diameter_mm if seat_diameter_mm is not None else port_diameter_mm
    area_m2 = pi * (d_mm / 2000.0) ** 2
    delta_p_pa = (inlet_pressure_bar - outlet_pressure_bar) * 1e5
    return delta_p_pa * area_m2


def required_thrust_shutoff(
    port_diameter_mm: float,
    shutoff_pressure_bar: float,
    seat_diameter_mm: float | None = None,
) -> float:
    """Calculate thrust required to achieve shutoff against differential pressure.

    F_shut = DeltaP_shutoff * A_seat

    Parameters
    ----------
    port_diameter_mm : Valve port diameter [mm]
    shutoff_pressure_bar : Maximum shutoff differential pressure [bar]
    seat_diameter_mm : Seat diameter [mm] (defaults to port_diameter)

    Returns
    -------
    Required thrust for shutoff [N].
    """
    d_mm = seat_diameter_mm if seat_diameter_mm is not None else port_diameter_mm
    area_m2 = pi * (d_mm / 2000.0) ** 2
    p_pa = shutoff_pressure_bar * 1e5
    return p_pa * area_m2


def required_thrust_packing(
    stem_diameter_mm: float,
    packing_friction_n_m: float = 500.0,
) -> float:
    """Estimate stem packing friction thrust.

    Typical packing friction: 100-1000 N/m of stem circumference.

    Parameters
    ----------
    stem_diameter_mm : Stem diameter [mm]
    packing_friction_n_m : Friction per meter of stem circumference [N/m]

    Returns
    -------
    Estimated packing friction thrust [N].
    """
    circumference_m = pi * stem_diameter_mm / 1000.0
    return circumference_m * packing_friction_n_m


def total_required_thrust(
    port_diameter_mm: float,
    inlet_pressure_bar: float,
    outlet_pressure_bar: float,
    shutoff_pressure_bar: float | None = None,
    stem_diameter_mm: float = 12.0,
    seat_diameter_mm: float | None = None,
    packing_friction_n_m: float = 500.0,
) -> dict[str, float]:
    """Calculate total required thrust with all components.

    Returns
    -------
    dict with keys: unbalance_n, shutoff_n, packing_n, total_n.
    """
    unbalance = required_thrust_unbalance(port_diameter_mm, inlet_pressure_bar, outlet_pressure_bar, seat_diameter_mm)
    packing = required_thrust_packing(stem_diameter_mm, packing_friction_n_m)
    shutoff = required_thrust_shutoff(port_diameter_mm, shutoff_pressure_bar, seat_diameter_mm) if shutoff_pressure_bar else 0.0
    total = unbalance + packing + shutoff
    return {"unbalance_n": unbalance, "shutoff_n": shutoff, "packing_n": packing, "total_n": total}


def select_actuator(
    required_thrust_n: float,
    valve_stroke_mm: float,
    actuator_key: str | None = None,
) -> dict[str, Any]:
    """Select an actuator from the catalog that meets thrust and stroke requirements.

    Parameters
    ----------
    required_thrust_n : Total required thrust [N]
    valve_stroke_mm : Required valve stroke [mm]
    actuator_key : Specific actuator model to check (optional).
        If None, searches entire catalog for smallest adequate actuator.

    Returns
    -------
    dict with keys: selected (bool), model, thrust_margin_pct, stroke_ok, details.
    """
    candidates = [actuator_key] if actuator_key else list(ACTUATOR_CATALOG.keys())
    best = None

    for key in candidates:
        act = ACTUATOR_CATALOG[key]
        thrust_n = max(act.thrust_open_n, act.thrust_close_n)
        if thrust_n >= required_thrust_n and act.stroke_mm >= valve_stroke_mm:
            is_better = best is None or thrust_n < max(ACTUATOR_CATALOG[best].thrust_open_n, ACTUATOR_CATALOG[best].thrust_close_n)
            if is_better:
                best = key

    if best is None and actuator_key:
        act = ACTUATOR_CATALOG[actuator_key]
        thrust_n = max(act.thrust_open_n, act.thrust_close_n)
        margin_pct = (thrust_n / required_thrust_n - 1.0) * 100.0 if required_thrust_n > 0 else 0.0
        return {
            "selected": False,
            "model": actuator_key,
            "thrust_n": thrust_n,
            "required_n": required_thrust_n,
            "thrust_margin_pct": margin_pct,
            "stroke_ok": act.stroke_mm >= valve_stroke_mm,
            "details": act,
        }

    if best is None:
        return {
            "selected": False, "model": None, "thrust_n": 0.0,
            "required_n": required_thrust_n, "thrust_margin_pct": -100.0,
            "stroke_ok": False, "details": None,
        }

    act = ACTUATOR_CATALOG[best]
    thrust_n = max(act.thrust_open_n, act.thrust_close_n)
    margin_pct = (thrust_n / required_thrust_n - 1.0) * 100.0
    return {
        "selected": True,
        "model": best,
        "thrust_n": thrust_n,
        "required_n": required_thrust_n,
        "thrust_margin_pct": margin_pct,
        "stroke_ok": True,
        "details": act,
    }
