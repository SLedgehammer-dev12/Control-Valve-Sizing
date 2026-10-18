"""Inherent flow characteristic curve and operating point controllability analysis.

Provides calculation of Equal Percentage, Linear, and Quick Opening characteristic
curves per IEC 60534-2-4 / ISA standards, along with operating point controllability
evaluations and gain analytics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from valve_sizing import cv_to_kv

DEFAULT_RANGEABILITY = 50.0


@dataclass(frozen=True)
class CharacteristicPoint:
    """Discrete coordinate along the valve flow characteristic curve."""

    opening_pct: float
    cv: float
    kv: float
    gain: float

    def to_dict(self) -> dict[str, float]:
        return {
            "opening_pct": self.opening_pct,
            "cv": self.cv,
            "kv": self.kv,
            "gain": self.gain,
        }


@dataclass(frozen=True)
class OperatingPointAnalysis:
    """Controllability evaluation at the active design operating point."""

    characteristic: str
    rated_cv: float
    required_cv: float
    opening_pct: float
    controllability_zone: str
    is_controllable: bool
    point_gain: float
    relative_cv_pct: float
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "characteristic": self.characteristic,
            "rated_cv": self.rated_cv,
            "required_cv": self.required_cv,
            "opening_pct": self.opening_pct,
            "controllability_zone": self.controllability_zone,
            "is_controllable": self.is_controllable,
            "point_gain": self.point_gain,
            "relative_cv_pct": self.relative_cv_pct,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class CharacteristicCurve:
    """Full discrete characteristic curve with operating point assessment."""

    characteristic: str
    rated_cv: float
    rangeability: float
    points: tuple[CharacteristicPoint, ...]
    operating_point: OperatingPointAnalysis

    def to_dict(self) -> dict[str, Any]:
        return {
            "characteristic": self.characteristic,
            "rated_cv": self.rated_cv,
            "rangeability": self.rangeability,
            "points": [p.to_dict() for p in self.points],
            "operating_point": self.operating_point.to_dict(),
        }


@dataclass(frozen=True)
class InstalledPoint:
    """Discrete point along the installed flow characteristic curve."""

    opening_pct: float
    inherent_cv: float
    installed_flow_pct: float
    installed_gain: float
    valve_dp_ratio: float

    def to_dict(self) -> dict[str, float]:
        return {
            "opening_pct": self.opening_pct,
            "inherent_cv": self.inherent_cv,
            "installed_flow_pct": self.installed_flow_pct,
            "installed_gain": self.installed_gain,
            "valve_dp_ratio": self.valve_dp_ratio,
        }


@dataclass(frozen=True)
class InstalledCharacteristicAnalysis:
    """Installed flow response and loop controllability analysis for a valve authority PR."""

    characteristic: str
    rated_cv: float
    valve_authority_pr: float
    gain_min: float
    gain_max: float
    gain_ratio: float
    is_gain_linear: bool
    operating_installed_flow_pct: float
    operating_installed_gain: float
    authority_assessment: str
    distortion_trend: str
    points: tuple[InstalledPoint, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "characteristic": self.characteristic,
            "rated_cv": self.rated_cv,
            "valve_authority_pr": self.valve_authority_pr,
            "gain_min": self.gain_min,
            "gain_max": self.gain_max,
            "gain_ratio": self.gain_ratio,
            "is_gain_linear": self.is_gain_linear,
            "operating_installed_flow_pct": self.operating_installed_flow_pct,
            "operating_installed_gain": self.operating_installed_gain,
            "authority_assessment": self.authority_assessment,
            "distortion_trend": self.distortion_trend,
            "points": [p.to_dict() for p in self.points],
            "warnings": list(self.warnings),
        }


def _evaluate_controllability_zone(opening_pct: float) -> tuple[str, bool, list[str]]:
    warnings: list[str] = []
    if opening_pct < 10.0:
        zone = "Kritik Düşük (< %10)"
        controllable = False
        warnings.append("Açıklık %10 altında: Klape sit yüzeyine çok yakın, kavitasyon/erozyon ve kontrol kararsızlığı riski yüksek.")
    elif opening_pct < 20.0:
        zone = "Düşük (%10 - %20)"
        controllable = True
        warnings.append("Açıklık %10-%20 aralığında: Hassas kontrol zorlaşabilir, dar kontrol aralığı.")
    elif opening_pct <= 80.0:
        zone = "İdeal (%20 - %80)"
        controllable = True
    elif opening_pct <= 85.0:
        zone = "Yüksek (%80 - %85)"
        controllable = True
        warnings.append("Açıklık %80-%85 aralığında: Tepe debi artış rezervi sınırlıdır.")
    else:
        zone = "Aşırı Yüksek (> %85)"
        controllable = False
        warnings.append("Açıklık %85 üzerinde: Vana tam açık sınırına çok yakın; bir üst vana gövdesi önerilir.")
    return zone, controllable, warnings


def cv_at_opening(
    opening_pct: float,
    rated_cv: float,
    characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
) -> float:
    """Calculate flow coefficient Cv at given opening percent (0 - 100%)."""
    if rated_cv <= 0:
        return 0.0
    h = max(0.0, min(100.0, float(opening_pct))) / 100.0
    char = characteristic.lower()

    if h == 0.0:
        return 0.0

    if char in ("equal_percentage", "eqpct", "eq_pct"):
        r = max(rangeability, 1.01)
        return float(rated_cv * (r ** (h - 1.0)))
    elif char in ("quick_opening", "quick", "qo"):
        return float(rated_cv * math.sqrt(h))
    else:
        return float(rated_cv * h)


def gain_at_opening(
    opening_pct: float,
    rated_cv: float,
    characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
) -> float:
    """Calculate valve flow gain d(Cv)/d(h_fraction) at given opening percent."""
    if rated_cv <= 0:
        return 0.0
    h = max(0.0, min(100.0, float(opening_pct))) / 100.0
    char = characteristic.lower()

    if char in ("equal_percentage", "eqpct", "eq_pct"):
        r = max(rangeability, 1.01)
        cv_val = rated_cv * (r ** (h - 1.0))
        return float(cv_val * math.log(r))
    elif char in ("quick_opening", "quick", "qo"):
        if h <= 0.001:
            return float(rated_cv * 0.5 / math.sqrt(0.001))
        return float(rated_cv * 0.5 / math.sqrt(h))
    else:
        return float(rated_cv)


def opening_at_cv(
    required_cv: float,
    rated_cv: float,
    characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
) -> float:
    """Estimate stem opening percentage [0 - 100%] for given required Cv."""
    if rated_cv <= 0 or required_cv <= 0:
        return 0.0
    ratio = min(required_cv / rated_cv, 1.0)
    char = characteristic.lower()

    if char in ("equal_percentage", "eqpct", "eq_pct"):
        r = max(rangeability, 1.01)
        min_controllable_ratio = 1.0 / r
        if ratio <= min_controllable_ratio:
            return 0.0
        h = 1.0 + (math.log(ratio) / math.log(r))
        return float(max(0.0, min(100.0, h * 100.0)))
    elif char in ("quick_opening", "quick", "qo"):
        h = ratio ** 2
        return float(max(0.0, min(100.0, h * 100.0)))
    else:
        return float(max(0.0, min(100.0, ratio * 100.0)))


def evaluate_operating_point(
    required_cv: float,
    rated_cv: float,
    characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
) -> OperatingPointAnalysis:
    """Analyze valve controllability at the required operating point."""
    opening_pct = opening_at_cv(required_cv, rated_cv, characteristic, rangeability)
    rel_cv = (required_cv / rated_cv * 100.0) if rated_cv > 0 else 0.0
    pt_gain = gain_at_opening(opening_pct, rated_cv, characteristic, rangeability)
    zone, controllable, warnings = _evaluate_controllability_zone(opening_pct)

    if required_cv > rated_cv:
        warnings.append(
            f"Gereken Cv ({required_cv:.2f}) anma kapasitesini ({rated_cv:.2f}) asiyor; "
            "kapasite asimi (overflow) durumu mevcuttur."
        )
        controllable = False

    return OperatingPointAnalysis(
        characteristic=characteristic,
        rated_cv=float(rated_cv),
        required_cv=float(required_cv),
        opening_pct=round(opening_pct, 2),
        controllability_zone=zone,
        is_controllable=controllable,
        point_gain=round(pt_gain, 2),
        relative_cv_pct=round(rel_cv, 2),
        warnings=tuple(warnings),
    )


def generate_characteristic_curve(
    rated_cv: float,
    required_cv: float,
    characteristic: str = "equal_percentage",
    rangeability: float = DEFAULT_RANGEABILITY,
    num_points: int = 51,
) -> CharacteristicCurve:
    """Generate discrete characteristic curve data points with operating point analysis."""
    step = 100.0 / max(num_points - 1, 1)
    pts: list[CharacteristicPoint] = []

    for i in range(num_points):
        pct = round(i * step, 2)
        if i == num_points - 1:
            pct = 100.0
        cv_val = cv_at_opening(pct, rated_cv, characteristic, rangeability)
        kv_val = cv_to_kv(cv_val)
        gain_val = gain_at_opening(pct, rated_cv, characteristic, rangeability)
        pts.append(
            CharacteristicPoint(
                opening_pct=pct,
                cv=round(cv_val, 3),
                kv=round(kv_val, 3),
                gain=round(gain_val, 3),
            )
        )

    op_analysis = evaluate_operating_point(required_cv, rated_cv, characteristic, rangeability)

    return CharacteristicCurve(
        characteristic=characteristic,
        rated_cv=float(rated_cv),
        rangeability=float(rangeability),
        points=tuple(pts),
        operating_point=op_analysis,
    )


def calc_installed_flow_ratio(cv_ratio: float, valve_authority_pr: float) -> float:
    """Calculate normalized installed flow Q/Qmax for given Cv/Cv100 and valve authority PR."""
    if cv_ratio <= 0.0 or valve_authority_pr <= 0.0:
        return 0.0
    if cv_ratio >= 1.0:
        return 1.0
    pr = max(1e-4, min(1.0, float(valve_authority_pr)))
    phi_sq = cv_ratio ** 2
    denom = pr + (1.0 - pr) * phi_sq
    return float(cv_ratio / math.sqrt(denom))


def calc_installed_gain(inherent_gain_ratio: float, cv_ratio: float, valve_authority_pr: float) -> float:
    """Calculate installed valve gain d(Q/Qmax)/dh for given inherent gain ratio, cv_ratio, and PR."""
    if valve_authority_pr <= 0.0 or cv_ratio < 0.0:
        return 0.0
    pr = max(1e-4, min(1.0, float(valve_authority_pr)))
    phi_sq = cv_ratio ** 2
    denom = pr + (1.0 - pr) * phi_sq
    return float((inherent_gain_ratio * math.sqrt(pr)) / (denom ** 1.5))


def generate_installed_characteristic(
    rated_cv: float,
    required_cv: float,
    characteristic: str = "equal_percentage",
    valve_authority_pr: float = 0.50,
    rangeability: float = DEFAULT_RANGEABILITY,
    num_points: int = 51,
) -> InstalledCharacteristicAnalysis:
    """Evaluate installed flow characteristic and loop gain distortion for a given valve authority PR."""
    pr = max(0.01, min(1.0, float(valve_authority_pr)))
    step = 100.0 / max(num_points - 1, 1)
    pts: list[InstalledPoint] = []
    gains_control_range: list[float] = []

    for i in range(num_points):
        pct = round(i * step, 2)
        if i == num_points - 1:
            pct = 100.0
        cv_val = cv_at_opening(pct, rated_cv, characteristic, rangeability)
        cv_rat = min(cv_val / rated_cv, 1.0) if rated_cv > 0 else 0.0
        flow_pct = calc_installed_flow_ratio(cv_rat, pr) * 100.0

        inh_gain = gain_at_opening(pct, rated_cv, characteristic, rangeability)
        inh_gain_ratio = inh_gain / rated_cv if rated_cv > 0 else 0.0
        inst_gain = calc_installed_gain(inh_gain_ratio, cv_rat, pr)

        flow_ratio = flow_pct / 100.0
        dp_ratio = max(0.0, 1.0 - (1.0 - pr) * (flow_ratio ** 2))

        if 20.0 <= pct <= 80.0:
            gains_control_range.append(inst_gain)

        pts.append(
            InstalledPoint(
                opening_pct=pct,
                inherent_cv=round(cv_val, 3),
                installed_flow_pct=round(flow_pct, 2),
                installed_gain=round(inst_gain, 3),
                valve_dp_ratio=round(dp_ratio, 3),
            )
        )

    g_min = min(gains_control_range) if gains_control_range else 1.0
    g_max = max(gains_control_range) if gains_control_range else 1.0
    g_ratio = round(g_max / max(g_min, 1e-4), 2)
    is_linear = g_ratio <= 4.0

    op = evaluate_operating_point(required_cv, rated_cv, characteristic, rangeability)
    op_cv_ratio = min(op.required_cv / rated_cv, 1.0) if rated_cv > 0 else 0.0
    op_flow_pct = round(calc_installed_flow_ratio(op_cv_ratio, pr) * 100.0, 2)
    op_inh_gain_ratio = op.point_gain / rated_cv if rated_cv > 0 else 0.0
    op_inst_gain = round(calc_installed_gain(op_inh_gain_ratio, op_cv_ratio, pr), 3)

    if pr >= 0.50:
        auth_str = "İdeal Vana Otoritesi (PR >= 0.50)"
    elif pr >= 0.25:
        auth_str = "Kabul Edilebilir Vana Otoritesi (0.25 <= PR < 0.50)"
    else:
        auth_str = "Zayıf Vana Otoritesi (PR < 0.25)"

    char_l = characteristic.lower()
    if char_l in ("equal_percentage", "eqpct", "eq_pct"):
        if 0.25 <= pr <= 0.55:
            trend = "Eşit Yüzdeli -> Doğrusallaşma Eğilimi (İdeal Proses Kontrolü)"
        elif pr < 0.25:
            trend = "Eşit Yüzdeli -> Aşırı Bozulma (Zayıf Otorite / Doygunluk)"
        else:
            trend = "Eşit Yüzdeli Karakteristik Korunuyor"
    elif char_l in ("linear",):
        trend = "Doğrusal -> Çabuk Açılana Yakınlaşma (Hassasiyet Kaybı)" if pr < 0.50 else "Doğrusal Karakteristik Korunuyor"
    else:
        trend = "Çabuk Açılan (On/Off veya Emniyet Tahliye Amaçlı)"

    warnings: list[str] = []
    if pr < 0.25:
        warnings.append(
            f"Vana otoritesi (PR = {pr:.2f} < 0.25) çok düşüktür; boru hattı sürtünme kaybı vanaya kıyasla baskındır. "
            "Vana yüksek açılmada akışı kontrol edemez (doygunluk) ve kontrol döngüsü salınıma girebilir."
        )
    if not is_linear:
        warnings.append(
            f"Kontrol aralığında (%20 - %80) dinamik kazanç oranı ({g_ratio:.1f}:1) ISA-75.11 / EnTech "
            "önerilen 4:1 sınırını aşıyor; tek bir sabit PID ayarıyla tüm aralıkta kararlı kontrol güçleşir."
        )

    return InstalledCharacteristicAnalysis(
        characteristic=characteristic,
        rated_cv=float(rated_cv),
        valve_authority_pr=round(pr, 3),
        gain_min=round(g_min, 3),
        gain_max=round(g_max, 3),
        gain_ratio=g_ratio,
        is_gain_linear=is_linear,
        operating_installed_flow_pct=op_flow_pct,
        operating_installed_gain=op_inst_gain,
        authority_assessment=auth_str,
        distortion_trend=trend,
        points=tuple(pts),
        warnings=tuple(warnings),
    )

