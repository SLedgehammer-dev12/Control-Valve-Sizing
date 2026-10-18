"""Unit tests for valve_curve.py flow characteristics and controllability."""

import pytest

from valve_curve import (
    CharacteristicPoint,
    cv_at_opening,
    evaluate_operating_point,
    gain_at_opening,
    generate_characteristic_curve,
    opening_at_cv,
)


class TestValveCurveFormulas:
    def test_cv_at_opening_equal_percentage(self):
        rated = 100.0
        assert cv_at_opening(0.0, rated, "equal_percentage") == 0.0
        assert cv_at_opening(100.0, rated, "equal_percentage") == pytest.approx(100.0)
        cv_50 = cv_at_opening(50.0, rated, "equal_percentage", rangeability=50.0)
        assert 10.0 < cv_50 < 20.0

    def test_cv_at_opening_linear(self):
        rated = 100.0
        assert cv_at_opening(0.0, rated, "linear") == 0.0
        assert cv_at_opening(50.0, rated, "linear") == pytest.approx(50.0)
        assert cv_at_opening(100.0, rated, "linear") == pytest.approx(100.0)

    def test_cv_at_opening_quick_opening(self):
        rated = 100.0
        assert cv_at_opening(0.0, rated, "quick_opening") == 0.0
        assert cv_at_opening(25.0, rated, "quick_opening") == pytest.approx(50.0)
        assert cv_at_opening(100.0, rated, "quick_opening") == pytest.approx(100.0)

    def test_cv_at_opening_zero_or_negative_rated(self):
        assert cv_at_opening(50.0, 0.0) == 0.0
        assert cv_at_opening(50.0, -10.0) == 0.0

    def test_gain_at_opening(self):
        rated = 100.0
        # Equal percentage gain
        g_eq = gain_at_opening(50.0, rated, "equal_percentage")
        assert g_eq > 0.0

        # Linear gain is constant rated_cv
        assert gain_at_opening(25.0, rated, "linear") == pytest.approx(100.0)
        assert gain_at_opening(75.0, rated, "linear") == pytest.approx(100.0)

        # Quick opening gain
        assert gain_at_opening(25.0, rated, "quick_opening") == pytest.approx(100.0)
        assert gain_at_opening(0.0, rated, "quick_opening") > 0.0
        assert gain_at_opening(50.0, 0.0) == 0.0

    def test_opening_at_cv(self):
        rated = 100.0
        # Zero checks
        assert opening_at_cv(0.0, rated) == 0.0
        assert opening_at_cv(50.0, 0.0) == 0.0

        # Linear
        assert opening_at_cv(50.0, rated, "linear") == pytest.approx(50.0)
        assert opening_at_cv(100.0, rated, "linear") == pytest.approx(100.0)

        # Quick opening
        assert opening_at_cv(50.0, rated, "quick_opening") == pytest.approx(25.0)

        # Equal percentage
        assert opening_at_cv(100.0, rated, "equal_percentage") == pytest.approx(100.0)
        assert opening_at_cv(1.0, rated, "equal_percentage", rangeability=50.0) == 0.0
        op_eq = opening_at_cv(25.0, rated, "equal_percentage")
        assert 60.0 < op_eq < 70.0


class TestOperatingPointAnalysis:
    def test_critical_low_zone(self):
        res = evaluate_operating_point(required_cv=0.1, rated_cv=100.0, characteristic="linear")
        assert res.opening_pct < 10.0
        assert "Kritik Düşük" in res.controllability_zone
        assert res.is_controllable is False
        assert any("sit yüzeyine çok yakın" in w for w in res.warnings)

    def test_low_zone(self):
        res = evaluate_operating_point(required_cv=15.0, rated_cv=100.0, characteristic="linear")
        assert 10.0 <= res.opening_pct < 20.0
        assert "Düşük" in res.controllability_zone
        assert res.is_controllable is True
        assert any("dar kontrol aralığı" in w for w in res.warnings)

    def test_ideal_zone(self):
        res = evaluate_operating_point(required_cv=50.0, rated_cv=100.0, characteristic="linear")
        assert 20.0 <= res.opening_pct <= 80.0
        assert "İdeal" in res.controllability_zone
        assert res.is_controllable is True
        assert len(res.warnings) == 0

    def test_high_zone(self):
        res = evaluate_operating_point(required_cv=82.0, rated_cv=100.0, characteristic="linear")
        assert 80.0 < res.opening_pct <= 85.0
        assert "Yüksek" in res.controllability_zone
        assert res.is_controllable is True
        assert any("rezervi sınırlıdır" in w for w in res.warnings)

    def test_excessive_zone_and_overflow(self):
        res_high = evaluate_operating_point(required_cv=90.0, rated_cv=100.0, characteristic="linear")
        assert res_high.opening_pct > 85.0
        assert "Aşırı Yüksek" in res_high.controllability_zone
        assert res_high.is_controllable is False

        res_over = evaluate_operating_point(required_cv=120.0, rated_cv=100.0, characteristic="linear")
        assert res_over.is_controllable is False
        assert any("kapasite asimi" in w for w in res_over.warnings)


class TestCurveGenerationAndDictSerialization:
    def test_generate_characteristic_curve(self):
        curve = generate_characteristic_curve(rated_cv=120.0, required_cv=45.0, characteristic="equal_percentage", num_points=21)
        assert len(curve.points) == 21
        assert curve.points[0].opening_pct == 0.0
        assert curve.points[0].cv == 0.0
        assert curve.points[-1].opening_pct == 100.0
        assert curve.points[-1].cv == pytest.approx(120.0)
        assert curve.operating_point.required_cv == 45.0
        assert curve.operating_point.rated_cv == 120.0

        d = curve.to_dict()
        assert d["characteristic"] == "equal_percentage"
        assert len(d["points"]) == 21
        assert "operating_point" in d
        assert d["operating_point"]["required_cv"] == 45.0

    def test_characteristic_point_to_dict(self):
        pt = CharacteristicPoint(opening_pct=50.0, cv=25.0, kv=21.625, gain=57.5)
        d = pt.to_dict()
        assert d["opening_pct"] == 50.0
        assert d["cv"] == 25.0
        assert d["kv"] == 21.625
        assert d["gain"] == 57.5
