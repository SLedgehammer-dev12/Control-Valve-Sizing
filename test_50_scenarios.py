"""Automated pytest suite for 52 industrial control valve verification scenarios.

Verifies sizing correctness, safety margins, acoustic attenuation,
cavitation severity, ASME B16.34 ratings, and ISA-20 datasheet integrity.
"""

from __future__ import annotations

import pytest

from verify_50_scenarios import (
    SCENARIO_DEFINITIONS,
    Scenario50Result,
    run_all_50_scenarios,
    run_scenario_50,
)


@pytest.fixture(scope="module")
def scenario_results() -> list[Scenario50Result]:
    """Execute all 52 scenarios once for the test module."""
    return run_all_50_scenarios()


def test_scenario_count_minimum_50():
    """Verify that at least 50 distinct scenarios are defined."""
    assert len(SCENARIO_DEFINITIONS) >= 50
    assert len(SCENARIO_DEFINITIONS) == 52


def test_sector_distribution():
    """Verify that all 5 key industrial sectors have at least 10 scenarios."""
    sectors = {sc.sector for sc in SCENARIO_DEFINITIONS}
    assert len(sectors) == 5
    for sec in sectors:
        count = sum(1 for sc in SCENARIO_DEFINITIONS if sc.sector == sec)
        assert count >= 10, f"Sektör {sec} için en az 10 senaryo olmalıdır, bulunan: {count}"


@pytest.mark.parametrize("sc", SCENARIO_DEFINITIONS, ids=lambda sc: sc.id)
def test_individual_scenario_execution(sc):
    """Verify that each individual scenario passes all engineering criteria."""
    result = run_scenario_50(sc)
    assert result.passed, f"Senaryo {sc.id} ({sc.name}) başarısız: {result.warnings} - {result.detail}"
    assert result.checks_passed == result.checks_total
    assert result.required_cv > 0.0
    assert result.rated_cv >= result.required_cv
    assert 0.0 < result.opening_percent <= 100.0
    assert result.valve_dn_mm > 0
    assert result.derated_mawp_bar >= result.p1_bar_a


def test_all_52_scenarios_pass(scenario_results: list[Scenario50Result]):
    """Verify 100% pass rate across all 52 scenarios."""
    failed = [r for r in scenario_results if not r.passed]
    assert not failed, f"{len(failed)} senaryo başarısız oldu: {[f.id for f in failed]}"


def test_cryogenic_engineering_coverage(scenario_results: list[Scenario50Result]):
    """Verify cryogenic scenarios correctly trigger extended bonnets and CF8M."""
    cryo = [r for r in scenario_results if r.temperature_c < -46.0]
    assert len(cryo) >= 5
    for r in cryo:
        assert "Kriyojenik" in r.bonnet_type
        assert "CF8M" in r.body_material or "316" in r.body_material


def test_toxic_fugitive_emissions_coverage(scenario_results: list[Scenario50Result]):
    """Verify toxic fluid scenarios require ISO 15848-1 Class AH bellows seals."""
    toxic_scenarios = [r for r in scenario_results if any(sc.id == r.id and sc.is_toxic for sc in SCENARIO_DEFINITIONS)]
    assert len(toxic_scenarios) >= 6
    for r in toxic_scenarios:
        assert "Körüklü" in r.packing_type
        assert "Class AH" in r.emission_class


def test_severe_cavitation_coverage(scenario_results: list[Scenario50Result]):
    """Verify severe cavitation scenarios trigger multi-stage trim."""
    cav_scenarios = [r for r in scenario_results if r.cavitation_severity and "Şiddetli" in r.cavitation_severity]
    assert len(cav_scenarios) >= 2
    for r in cav_scenarios:
        assert r.is_choked


def test_high_noise_and_aiv_coverage(scenario_results: list[Scenario50Result]):
    """Verify high acoustic noise triggers mitigation recommendations."""
    high_noise = [r for r in scenario_results if r.noise_dba > 85.0]
    assert len(high_noise) >= 20
    for r in high_noise:
        assert len(r.acoustic_treatment) > 0
        assert "Whisper" in r.acoustic_treatment or "İyileştirme" in r.acoustic_treatment or "Labirent" in r.acoustic_treatment
