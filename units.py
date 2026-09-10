"""Unit conversion constants and pint-based quantity helpers.

Centralizes all unit conversion factors used across the application.
Exposes bare constants for backward compatibility with valve_sizing.py,
and a pint UnitRegistry for type-safe conversion in new code. Also
provides sector-standard unit selectors and converters for the petroleum,
natural gas and energy industries (bar/psi gauge & absolute, gpm/bbl,
Nm3h/scfh/MMSCFD, etc.).
"""

from __future__ import annotations

import pint
from pint import UnitRegistry

# ---------------------------------------------------------------------------
# Backward-compatible bare constants (same names as original valve_sizing.py)
# ---------------------------------------------------------------------------
BAR_TO_PSI = 14.5037738
M3H_TO_GPM = 4.4028675
NM3H_TO_SCFH = 35.3146667
KGH_TO_LBH = 2.20462262
CV_TO_KV = 0.865
KV_TO_CV = 1.0 / CV_TO_KV
AIR_MW = 28.97
AIR_K = 1.4
FF_A = 0.96
FF_B = 0.28
CELSIUS_TO_RANKINE = 9.0 / 5.0
NORMAL_P_BAR = 1.01325
NORMAL_T_K = 273.15
ATMOSPHERIC_BAR = 1.01325

# ---------------------------------------------------------------------------
# Sector unit option maps: key -> display label
# ---------------------------------------------------------------------------
TEMPERATURE_UNITS: dict[str, str] = {
    "C": "°C",
    "F": "°F",
    "K": "K",
}

PRESSURE_UNITS: dict[str, str] = {
    "bar_a": "bar(a)",
    "bar_g": "bar(g)",
    "psi_a": "psi(a)",
    "psi_g": "psi(g)",
    "kPa_a": "kPa(a)",
    "MPa_a": "MPa(a)",
    "atm_a": "atm(a)",
}

LIQUID_FLOW_UNITS: dict[str, str] = {
    "m3h": "m³/h",
    "gpm": "US gpm",
    "lpm": "L/min",
    "m3d": "m³/d",
    "bbl_d": "US bbl/d",
    "kgh": "kg/h",
}

GAS_FLOW_UNITS: dict[str, str] = {
    "nm3h": "Nm³/h",
    "sm3h": "Sm³/h",
    "scfh": "scfh",
    "mmscfd": "MMSCFD",
    "m3h": "m³/h (actual)",
    "kgh": "kg/h",
}

STEAM_FLOW_UNITS: dict[str, str] = {
    "kgh": "kg/h",
    "th": "t/h",
    "lbh": "lb/h",
    "kgs": "kg/s",
}

DEFAULT_UNITS: dict[str, str] = {
    "temperature": "C",
    "pressure": "bar_a",
    "liquid_flow": "m3h",
    "gas_flow": "nm3h",
    "steam_flow": "kgh",
}

# ---------------------------------------------------------------------------
# Pint unit registry — for new code
# ---------------------------------------------------------------------------
ureg: UnitRegistry = pint.UnitRegistry()
Q_ = ureg.Quantity


def temperature_to_c(value: float, unit: str) -> float:
    """Convert a temperature to degrees Celsius."""
    if unit == "C":
        return float(value)
    if unit == "F":
        return (float(value) - 32.0) * 5.0 / 9.0
    if unit == "K":
        return float(value) - 273.15
    raise ValueError(f"Bilinmeyen sicaklik birimi: {unit}")


def temperature_from_c(value_c: float, unit: str) -> float:
    """Convert degrees Celsius to the requested unit."""
    if unit == "C":
        return float(value_c)
    if unit == "F":
        return float(value_c) * 9.0 / 5.0 + 32.0
    if unit == "K":
        return float(value_c) + 273.15
    raise ValueError(f"Bilinmeyen sicaklik birimi: {unit}")


def pressure_to_bar_a(value: float, unit: str) -> float:
    """Convert a pressure to bar absolute. Gauge units use 1.01325 bar atmosphere."""
    if unit == "bar_a":
        return float(value)
    if unit == "bar_g":
        return float(value) + ATMOSPHERIC_BAR
    if unit == "psi_a":
        return float(value) / BAR_TO_PSI
    if unit == "psi_g":
        return float(value) / BAR_TO_PSI + ATMOSPHERIC_BAR
    if unit == "kPa_a":
        return float(value) / 100.0
    if unit == "MPa_a":
        return float(value) * 10.0
    if unit == "atm_a":
        return float(value) * ATMOSPHERIC_BAR
    raise ValueError(f"Bilinmeyen basinc birimi: {unit}")


def pressure_from_bar_a(value_bar_a: float, unit: str) -> float:
    """Convert bar absolute to the requested unit."""
    if unit == "bar_a":
        return float(value_bar_a)
    if unit == "bar_g":
        return float(value_bar_a) - ATMOSPHERIC_BAR
    if unit == "psi_a":
        return float(value_bar_a) * BAR_TO_PSI
    if unit == "psi_g":
        return (float(value_bar_a) - ATMOSPHERIC_BAR) * BAR_TO_PSI
    if unit == "kPa_a":
        return float(value_bar_a) * 100.0
    if unit == "MPa_a":
        return float(value_bar_a) / 10.0
    if unit == "atm_a":
        return float(value_bar_a) / ATMOSPHERIC_BAR
    raise ValueError(f"Bilinmeyen basinc birimi: {unit}")


def liquid_flow_to_m3h(value: float, unit: str, density_kg_m3: float | None = None) -> float:
    """Convert a liquid volumetric/mass flow to m3/h."""
    if unit == "m3h":
        return float(value)
    if unit == "gpm":
        return float(value) / M3H_TO_GPM
    if unit == "lpm":
        return float(value) * 0.06
    if unit == "m3d":
        return float(value) / 24.0
    if unit == "bbl_d":
        return float(value) * 0.158987 / 24.0
    if unit == "kgh":
        if not density_kg_m3 or density_kg_m3 <= 0:
            raise ValueError("kgh birimi icin sivi yogunlugu gereklidir.")
        return float(value) / density_kg_m3
    raise ValueError(f"Bilinmeyen sivi debi birimi: {unit}")


def liquid_flow_from_m3h(value_m3h: float, unit: str, density_kg_m3: float | None = None) -> float:
    """Convert m3/h to the requested liquid flow unit."""
    if unit == "m3h":
        return float(value_m3h)
    if unit == "gpm":
        return float(value_m3h) * M3H_TO_GPM
    if unit == "lpm":
        return float(value_m3h) / 0.06
    if unit == "m3d":
        return float(value_m3h) * 24.0
    if unit == "bbl_d":
        return float(value_m3h) / 0.158987 * 24.0
    if unit == "kgh":
        if not density_kg_m3 or density_kg_m3 <= 0:
            raise ValueError("kgh birimi icin sivi yogunlugu gereklidir.")
        return float(value_m3h) * density_kg_m3
    raise ValueError(f"Bilinmeyen sivi debi birimi: {unit}")


def gas_flow_to_nm3h(
    value: float,
    unit: str,
    pressure_bar_a: float | None = None,
    temperature_c: float | None = None,
    z: float = 1.0,
    density_kg_m3: float | None = None,
) -> float:
    """Convert a gas flow to Nm3/h.

    Actual m3/h and kg/h conversions need process pressure/temperature
    (and density for kg/h); a standard 1.01325 bar / 15 C reference is
    used for Sm3h when no conditions are supplied.
    """
    if unit == "nm3h":
        return float(value)
    if unit == "sm3h":
        return float(value) * NORMAL_T_K / 288.15
    if unit == "scfh":
        return float(value) / NM3H_TO_SCFH
    if unit == "mmscfd":
        return float(value) * 1e6 / 24.0 / NM3H_TO_SCFH
    if unit == "m3h":
        p_bar = pressure_bar_a if pressure_bar_a is not None else 1.0
        t_c = temperature_c if temperature_c is not None else 15.0
        t_k = t_c + 273.15
        return float(value) * (p_bar / NORMAL_P_BAR) * (NORMAL_T_K / t_k) / max(z, 1e-6)
    if unit == "kgh":
        if not density_kg_m3 or density_kg_m3 <= 0:
            raise ValueError("kgh birimi icin gaz yogunlugu gereklidir.")
        p_bar = pressure_bar_a if pressure_bar_a is not None else 1.0
        t_c = temperature_c if temperature_c is not None else 15.0
        t_k = t_c + 273.15
        actual_m3h = float(value) / density_kg_m3
        return actual_m3h * (p_bar / NORMAL_P_BAR) * (NORMAL_T_K / t_k) / max(z, 1e-6)
    raise ValueError(f"Bilinmeyen gaz debi birimi: {unit}")


def gas_flow_from_nm3h(
    value_nm3h: float,
    unit: str,
    pressure_bar_a: float | None = None,
    temperature_c: float | None = None,
    z: float = 1.0,
    density_kg_m3: float | None = None,
) -> float:
    """Convert Nm3/h to the requested gas flow unit."""
    if unit == "nm3h":
        return float(value_nm3h)
    if unit == "sm3h":
        return float(value_nm3h) * 288.15 / NORMAL_T_K
    if unit == "scfh":
        return float(value_nm3h) * NM3H_TO_SCFH
    if unit == "mmscfd":
        return float(value_nm3h) * NM3H_TO_SCFH * 24.0 / 1e6
    if unit == "m3h":
        p_bar = pressure_bar_a if pressure_bar_a is not None else 1.0
        t_c = temperature_c if temperature_c is not None else 15.0
        t_k = t_c + 273.15
        return float(value_nm3h) * (NORMAL_P_BAR / p_bar) * (t_k / NORMAL_T_K) * z
    if unit == "kgh":
        if not density_kg_m3 or density_kg_m3 <= 0:
            raise ValueError("kgh birimi icin gaz yogunlugu gereklidir.")
        actual_m3h = gas_flow_from_nm3h(
            value_nm3h, "m3h", pressure_bar_a, temperature_c, z, density_kg_m3
        )
        return actual_m3h * density_kg_m3
    raise ValueError(f"Bilinmeyen gaz debi birimi: {unit}")


def steam_flow_to_kgh(value: float, unit: str) -> float:
    """Convert a steam/mass flow to kg/h."""
    if unit == "kgh":
        return float(value)
    if unit == "th":
        return float(value) * 1000.0
    if unit == "lbh":
        return float(value) / KGH_TO_LBH
    if unit == "kgs":
        return float(value) * 3600.0
    raise ValueError(f"Bilinmeyen buhar debi birimi: {unit}")


def steam_flow_from_kgh(value_kgh: float, unit: str) -> float:
    """Convert kg/h to the requested steam flow unit."""
    if unit == "kgh":
        return float(value_kgh)
    if unit == "th":
        return float(value_kgh) / 1000.0
    if unit == "lbh":
        return float(value_kgh) * KGH_TO_LBH
    if unit == "kgs":
        return float(value_kgh) / 3600.0
    raise ValueError(f"Bilinmeyen buhar debi birimi: {unit}")


def bar_to_pa(bar: float) -> float:
    return bar * 1e5


def pa_to_bar(pa: float) -> float:
    return pa / 1e5


def mm_to_m(mm: float) -> float:
    return mm / 1000.0


def celsius_to_k(c: float) -> float:
    return c + 273.15


def k_to_celsius(k: float) -> float:
    return k - 273.15


def nm3h_to_actual_m3h(
    flow_nm3h: float,
    p1_bar_a: float,
    t_k: float,
    z: float,
) -> float:
    return flow_nm3h * (NORMAL_P_BAR / p1_bar_a) * (t_k / NORMAL_T_K) * z
