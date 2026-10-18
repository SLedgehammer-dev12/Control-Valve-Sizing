"""Unit tests for valve stem packing and fugitive emissions selection engine."""

from packing_emissions import recommend_packing_system


def test_packing_toxic_service_bellows_seal():
    phosgene = recommend_packing_system("gas", "Phosgene", 40.0, 5.0)
    assert "Bellows Seal" in phosgene.packing_type
    assert phosgene.leakage_tightness_ppmv <= 10.0
    assert "AH" in phosgene.emission_class

    co = recommend_packing_system("gas", "Carbon Monoxide (CO)", 30.0, 10.0)
    assert "Bellows Seal" in co.packing_type


def test_packing_non_toxic_co_substring_no_false_positive():
    cooling_water = recommend_packing_system("liquid", "Cooling Water", 35.0, 4.0)
    assert "Bellows Seal" not in cooling_water.packing_type
    assert "PTFE" in cooling_water.packing_type

    condensate = recommend_packing_system("liquid", "Condensate Return", 80.0, 6.0)
    assert "Bellows Seal" not in condensate.packing_type

    air = recommend_packing_system("gas", "Compressed Air", 25.0, 7.0)
    assert "Bellows Seal" not in air.packing_type

    co2 = recommend_packing_system("gas", "Carbon Dioxide", 30.0, 20.0)
    assert "Bellows Seal" not in co2.packing_type


def test_packing_high_temperature_graphite():
    steam_hot = recommend_packing_system("steam", "Superheated Steam", 350.0, 25.0)
    assert "Grafit" in ph_type if (ph_type := steam_hot.packing_type) else True
    assert "Graphite" in steam_hot.packing_type
    assert steam_hot.fire_safe is True
    assert steam_hot.temperature_range_c[1] >= 500.0


def test_packing_standard_ptfe_chevron():
    ambient_water = recommend_packing_system("liquid", "Demin Water", 25.0, 10.0)
    assert "PTFE" in ambient_water.packing_type
    assert ambient_water.leakage_tightness_ppmv <= 50.0


def test_packing_sour_gas_nace():
    sour = recommend_packing_system("gas", "Sour Natural Gas (H2S)", 60.0, 40.0, is_sour_gas=True)
    assert sour.nace_mr0175_compliant is True
    assert any("NACE" in rec for rec in sour.recommendations)
