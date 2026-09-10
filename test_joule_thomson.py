import pytest

from joule_thomson import calc_joule_thomson_drop, natural_gas_hydrate_temperature


def test_hydrate_temperature_values():
    t_10 = natural_gas_hydrate_temperature(10.0, 0.6)
    assert t_10 == pytest.approx(0.8, abs=0.5)

    t_50 = natural_gas_hydrate_temperature(50.0, 0.6)
    assert t_50 == pytest.approx(13.8, abs=1.5)

    t_100 = natural_gas_hydrate_temperature(100.0, 0.6)
    assert t_100 == pytest.approx(19.1, abs=1.5)


def test_methane_joule_thomson_drop():
    res = calc_joule_thomson_drop("Methane", 50.0, 10.0, 20.0)
    assert res.t1_c == 20.0
    assert res.t2_c == pytest.approx(1.5, abs=0.5)
    assert res.delta_t_c == pytest.approx(18.5, abs=0.5)
    assert res.mu_jt_c_per_bar == pytest.approx(0.46, abs=0.05)
    assert res.t_hydrate_c == pytest.approx(0.8, abs=0.5)
    assert res.t_preheat_min_c > res.t1_c


def test_hydrogen_joule_thomson_inversion():
    res = calc_joule_thomson_drop("Hydrogen", 50.0, 10.0, 20.0)
    assert res.delta_t_c < 0.0
    assert any("Ters J-T" in w for w in res.warnings)


def test_natural_gas_hydrate_risk_detected():
    res = calc_joule_thomson_drop("NaturalGas", 60.0, 20.0, 15.0)
    assert res.t2_c < res.t1_c
    assert res.hydrate_risk is True
    assert any("hidrat" in w.lower() for w in res.warnings)


def test_invalid_pressures_raise():
    with pytest.raises(ValueError, match="büyük olmalıdır"):
        calc_joule_thomson_drop("Methane", 10.0, 20.0, 20.0)

    with pytest.raises(ValueError, match="büyük olmalıdır"):
        calc_joule_thomson_drop("Methane", 10.0, 10.0, 20.0)

    with pytest.raises(ValueError, match="sıfırdan büyük"):
        calc_joule_thomson_drop("Methane", 10.0, 0.0, 20.0)
