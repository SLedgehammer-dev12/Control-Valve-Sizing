"""Unit conversion constants and pint-based quantity helpers.

Centralizes all unit conversion factors used across the application.
Exposes bare constants for backward compatibility with valve_sizing.py,
and a pint UnitRegistry for type-safe conversion in new code.
"""

from __future__ import annotations

import pint

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

# ---------------------------------------------------------------------------
# Pint unit registry — for new code
# ---------------------------------------------------------------------------
ureg = pint.UnitRegistry()
Q_ = ureg.Quantity


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
