"""Unit tests for multicomponent hydrocarbon VLE PT-flash (Peng-Robinson + Rachford-Rice)."""

from __future__ import annotations

import pytest

from fluid_properties import flash_multicomponent_mixture


def test_natural_gas_cryogenic_lng_subcooled() -> None:
    res = flash_multicomponent_mixture("Doğal Gaz", 6.0, -150.0)
    assert res.phase == "liquid"
    assert res.beta_vapor_mole_fraction == 0.0
    assert res.liquid_mole_fraction == 1.0
    assert res.liquid_mass_fraction == 1.0
    assert res.rho_liquid_kg_m3 is not None
    assert 415.0 <= res.rho_liquid_kg_m3 <= 445.0
    assert res.rho_tp_kg_m3 == pytest.approx(res.rho_liquid_kg_m3, rel=1e-3)


def test_natural_gas_two_phase_condensation() -> None:
    res = flash_multicomponent_mixture("Doğal Gaz", 6.0, -120.0)
    assert res.phase == "two_phase"
    assert 0.0 < res.beta_vapor_mole_fraction < 1.0
    assert 0.10 <= res.liquid_mole_fraction <= 0.25
    assert res.vapor_mass_fraction + res.liquid_mass_fraction == pytest.approx(1.0, rel=1e-5)
    assert res.rho_liquid_kg_m3 is not None and res.rho_liquid_kg_m3 > 400.0
    assert res.rho_vapor_kg_m3 is not None and res.rho_vapor_kg_m3 > 0.0
    assert res.rho_tp_kg_m3 > res.rho_vapor_kg_m3


def test_natural_gas_ambient_dry_gas() -> None:
    res = flash_multicomponent_mixture("Doğal Gaz", 6.0, 25.0)
    assert res.phase == "gas"
    assert res.beta_vapor_mole_fraction == 1.0
    assert res.liquid_mole_fraction == 0.0
    assert res.liquid_mass_fraction == 0.0
    assert res.rho_vapor_kg_m3 is not None
    assert 3.5 <= res.rho_vapor_kg_m3 <= 5.5


def test_custom_ternary_flash_mass_conservation() -> None:
    comp = [
        {"component": "Methane", "fraction_pct": 80.0},
        {"component": "Propane", "fraction_pct": 15.0},
        {"component": "CarbonDioxide", "fraction_pct": 5.0},
    ]
    res = flash_multicomponent_mixture(comp, 10.0, -80.0)
    assert res.liquid_mass_fraction + res.vapor_mass_fraction == pytest.approx(1.0, rel=1e-5)
    assert res.rho_tp_kg_m3 > 0.0
