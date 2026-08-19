"""Scenario verification tests wrapping the verify_scenarios runners.

Each scenario is cross-checked against an independent reference in
verify_scenarios.py; this module pins those checks as permanent CI tests.
"""

from __future__ import annotations

import pytest

from verify_scenarios import (
    run_scenario_verification,
    verify_design_margin,
    verify_gas_choked_analytic,
    verify_gas_energy_blend,
    verify_gas_iec_anchor,
    verify_liquid_choked,
    verify_liquid_flashing,
    verify_liquid_subcritical,
    verify_liquid_velocity,
    verify_steam_near_saturated,
    verify_steam_superheated,
    verify_unit_equivalence,
    verify_vendor_catalog,
)

SCENARIO_FUNCTIONS = [
    verify_liquid_subcritical,
    verify_liquid_choked,
    verify_liquid_flashing,
    verify_liquid_velocity,
    verify_gas_iec_anchor,
    verify_gas_choked_analytic,
    verify_gas_energy_blend,
    verify_steam_superheated,
    verify_steam_near_saturated,
    verify_unit_equivalence,
    verify_design_margin,
    verify_vendor_catalog,
]


@pytest.mark.parametrize("runner", SCENARIO_FUNCTIONS, ids=lambda fn: fn.__name__)
def test_scenario_verification(runner):
    result = runner()
    assert result.passed, result.detail


def test_all_scenarios_pass():
    results = run_scenario_verification()
    failed = [r for r in results if not r.passed]
    assert not failed, "\n".join(f"{r.name}: {r.detail}" for r in failed)
