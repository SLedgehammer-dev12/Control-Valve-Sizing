"""Valve specification guidance (ANSI class, leakage class, fail-safe).

Provides recommendation helpers for ASME B16.34 pressure class (including
temperature derating for standard material groups WCB, CF8M, WC6), ASME
B16.104 / IEC 60534-4 leakage class and numeric allowable leakage rates,
and fail-safe action based on the sizing result and service.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

ANSI_CLASS_AMBIENT_BAR: dict[str, float] = {
    "CL150": 19.6,
    "CL300": 51.1,
    "CL600": 102.1,
    "CL900": 153.3,
    "CL1500": 255.3,
    "CL2500": 425.5,
}

PRESSURE_CLASS_ORDER = tuple(ANSI_CLASS_AMBIENT_BAR.keys())

LEAKAGE_CLASSES = ("II", "III", "IV", "V", "VI")

MATERIAL_GROUPS = ("WCB", "CF8M", "WC6")

MATERIAL_GROUP_LABELS: dict[str, str] = {
    "WCB": "Karbon Celik (A216 WCB / A105, Grup 1.1)",
    "CF8M": "Paslanmaz Celik (A351 CF8M / 316, Grup 2.2)",
    "WC6": "Krom-Molibden Celik (A217 WC6, Grup 1.9)",
}

ASME_B1634_TEMPS_C = (-29.0, 38.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 425.0, 450.0, 500.0, 538.0)

ASME_B1634_RATINGS_BAR: dict[str, dict[str, list[float]]] = {
    "WCB": {
        "CL150": [19.6, 19.6, 17.7, 15.8, 13.8, 12.1, 10.2, 8.4, 6.5, 5.5, 0.0, 0.0, 0.0],
        "CL300": [51.1, 51.1, 46.6, 45.1, 43.8, 41.9, 39.8, 37.6, 34.7, 28.8, 0.0, 0.0, 0.0],
        "CL600": [102.1, 102.1, 93.2, 90.2, 87.6, 83.9, 79.6, 75.1, 69.4, 57.5, 0.0, 0.0, 0.0],
        "CL900": [153.2, 153.2, 139.8, 135.2, 131.4, 125.8, 119.5, 112.7, 104.2, 86.3, 0.0, 0.0, 0.0],
        "CL1500": [255.3, 255.3, 233.0, 225.4, 219.0, 209.7, 199.1, 187.8, 173.6, 143.8, 0.0, 0.0, 0.0],
        "CL2500": [425.5, 425.5, 388.3, 375.6, 365.0, 349.5, 331.8, 313.0, 289.3, 239.7, 0.0, 0.0, 0.0],
    },
    "CF8M": {
        "CL150": [19.0, 19.0, 16.2, 14.8, 13.7, 12.1, 10.2, 8.4, 6.5, 5.5, 4.6, 2.8, 1.4],
        "CL300": [49.6, 49.6, 42.2, 38.5, 35.7, 33.4, 31.6, 30.3, 29.4, 29.1, 28.8, 28.2, 25.2],
        "CL600": [99.3, 99.3, 84.4, 77.0, 71.3, 66.8, 63.2, 60.7, 58.9, 58.3, 57.7, 56.5, 50.4],
        "CL900": [148.9, 148.9, 126.6, 115.5, 107.0, 100.1, 94.9, 91.0, 88.3, 87.4, 86.5, 84.7, 75.6],
        "CL1500": [248.2, 248.2, 211.0, 192.5, 178.3, 166.9, 158.1, 151.7, 147.2, 145.7, 144.2, 140.9, 126.0],
        "CL2500": [413.7, 413.7, 351.6, 320.8, 297.2, 278.1, 263.5, 252.8, 245.3, 242.8, 240.3, 235.0, 210.0],
    },
    "WC6": {
        "CL150": [19.8, 19.8, 19.0, 16.2, 13.8, 12.1, 10.2, 8.4, 6.5, 5.5, 4.6, 2.8, 1.4],
        "CL300": [51.7, 51.7, 51.5, 49.7, 47.6, 45.7, 43.6, 41.6, 39.3, 38.0, 36.6, 28.6, 16.2],
        "CL600": [103.4, 103.4, 103.0, 99.5, 95.2, 91.4, 87.2, 83.1, 78.6, 76.0, 73.1, 57.3, 32.4],
        "CL900": [155.1, 155.1, 154.4, 149.2, 142.8, 137.1, 130.8, 124.7, 117.9, 114.0, 109.7, 85.9, 48.6],
        "CL1500": [258.6, 258.6, 257.4, 248.7, 238.0, 228.5, 218.0, 207.8, 196.5, 190.0, 182.8, 143.2, 81.0],
        "CL2500": [430.9, 430.9, 429.0, 414.5, 396.6, 380.9, 363.3, 346.4, 327.5, 316.7, 304.7, 238.6, 135.0],
    },
}


def derated_mawp_bar(pressure_class: str, temperature_c: float, material_group: str = "WCB") -> float:
    """Return derated Maximum Allowable Working Pressure [bar(a)] per ASME B16.34."""
    mat = material_group.upper()
    if mat not in ASME_B1634_RATINGS_BAR:
        mat = "WCB"
    cls_ratings = ASME_B1634_RATINGS_BAR[mat].get(pressure_class)
    if not cls_ratings:
        return ANSI_CLASS_AMBIENT_BAR.get(pressure_class, 19.6)

    temps = ASME_B1634_TEMPS_C
    t = float(temperature_c)
    if t <= temps[1]:
        return cls_ratings[1]
    if t >= temps[-1]:
        return cls_ratings[-1]

    for i in range(1, len(temps) - 1):
        if temps[i] <= t <= temps[i + 1]:
            t_low, t_high = temps[i], temps[i + 1]
            p_low, p_high = cls_ratings[i], cls_ratings[i + 1]
            if t_high == t_low:
                return p_low
            fraction = (t - t_low) / (t_high - t_low)
            return p_low + fraction * (p_high - p_low)

    return cls_ratings[-1]


def recommend_pressure_class(
    inlet_pressure_bar: float,
    temperature_c: float = 20.0,
    material_group: str = "WCB",
) -> str:
    """Return minimum ASME B16.34 pressure class accounting for temperature derating."""
    if inlet_pressure_bar <= 0:
        return "CL150"

    for cls in PRESSURE_CLASS_ORDER:
        mawp = derated_mawp_bar(cls, temperature_c, material_group)
        if mawp >= inlet_pressure_bar:
            return cls
    return "CL2500"


def recommend_leakage_class(service: str, is_choked: bool = False) -> str:
    """Recommend an ASME B16.104 / IEC 60534-4 seat leakage class."""
    if service == "gas" or is_choked:
        return "VI"
    if service == "steam":
        return "V"
    return "IV"


def allowable_leakage_rate(
    rated_cv: float,
    leakage_class: str,
    port_diameter_mm: float = 50.0,
    delta_p_bar: float = 1.0,
) -> dict[str, Any]:
    """Calculate maximum allowable seat leakage rate per IEC 60534-4 / ANSI FCI 70-2."""
    cv = max(float(rated_cv), 0.0)
    dp_psi = max(float(delta_p_bar) * 14.5038, 1.0)
    d_inch = max(float(port_diameter_mm) / 25.4, 0.5)

    if leakage_class == "II":
        rate_gpm = 0.005 * cv * math.sqrt(dp_psi / 14.5038)
        return {"class": "II", "test_fluid": "water/air", "rate_unit": "L/min", "max_rate": rate_gpm * 3.785, "note": "Rated Cv x %0.5"}
    if leakage_class == "III":
        rate_gpm = 0.001 * cv * math.sqrt(dp_psi / 14.5038)
        return {"class": "III", "test_fluid": "water/air", "rate_unit": "L/min", "max_rate": rate_gpm * 3.785, "note": "Rated Cv x %0.1"}
    if leakage_class == "IV":
        rate_gpm = 0.0001 * cv * math.sqrt(dp_psi / 14.5038)
        return {
            "class": "IV",
            "test_fluid": "water",
            "rate_unit": "L/min",
            "max_rate": rate_gpm * 3.785,
            "note": "Rated Cv x %0.01 (standart metal-sit)",
        }
    if leakage_class == "V":
        rate_ml_min = 0.0005 * d_inch * dp_psi
        return {"class": "V", "test_fluid": "water", "rate_unit": "ml/min", "max_rate": rate_ml_min, "note": "0.0005 ml/dak/psi/inc sit"}
    if leakage_class == "VI":
        bubbles = max(1, int(d_inch * 4))
        rate_ml_min = bubbles * 0.15
        return {
            "class": "VI",
            "test_fluid": "air/nitrogen",
            "rate_unit": "kabarcik/dak (ml/dak)",
            "max_rate": rate_ml_min,
            "note": f"Yumusak sit, ~{bubbles} kabarcik/dak",
        }

    return {"class": leakage_class, "test_fluid": "water", "rate_unit": "L/min", "max_rate": 0.0, "note": "Belirtilmemis"}


def recommend_fail_safe(service: str, application: str = "") -> str:
    """Recommend a fail-safe action based on service and application hint."""
    app = application.strip().lower()
    if "cooling" in app or "sogutma" in app or "so\u011futma" in app:
        return "fail-open (acik kalarak sogutma korunur)"
    if "fuel" in app or "yakit" in app or "yak\u0131t" in app:
        return "fail-closed (kapali kalarak akis kesilir)"
    if service == "steam":
        return "fail-closed (standart buhar hatti guvenligi)"
    return "fail-in-position (FC/FO proses guvenlik analizine gore secilmeli)"


def build_valve_spec(
    service: str,
    inlet_pressure_bar: float,
    is_choked: bool = False,
    regime: str = "",
    application: str = "",
    vendor_pressure_class: str = "",
    vendor_leakage_class: str = "",
    temperature_c: float = 20.0,
    material_group: str = "WCB",
    rated_cv: float = 0.0,
    port_diameter_mm: float = 50.0,
    delta_p_bar: float = 1.0,
) -> dict[str, Any]:
    """Build a complete ASME B16.34 / IEC 60534-4 valve specification dictionary."""
    recommended_class = recommend_pressure_class(inlet_pressure_bar, temperature_c, material_group)
    derated_mawp = derated_mawp_bar(recommended_class, temperature_c, material_group)
    ambient_mawp = ANSI_CLASS_AMBIENT_BAR.get(recommended_class, 19.6)
    derating_pct = ((derated_mawp / ambient_mawp) - 1.0) * 100.0 if ambient_mawp > 0 else 0.0

    recommended_leakage = recommend_leakage_class(service, is_choked or regime == "flashing")
    leakage_info = allowable_leakage_rate(rated_cv, recommended_leakage, port_diameter_mm, delta_p_bar)

    note = (
        f"ASME B16.34 sinifi {temperature_c:.1f} °C calisma sicakligi ve {material_group} malzemesi bazinda "
        f"derate edilmistir (MAWP: {derated_mawp:.1f} bar). Fail-safe nihai karari HAZOP proses guvenlik analizine aittir."
    )
    return {
        "service": service,
        "inlet_pressure_bar": f"{inlet_pressure_bar:.2f}",
        "temperature_c": float(temperature_c),
        "material_group": material_group,
        "material_label": MATERIAL_GROUP_LABELS.get(material_group, material_group),
        "pressure_class_recommended": recommended_class,
        "derated_mawp_bar": round(derated_mawp, 2),
        "ambient_mawp_bar": round(ambient_mawp, 2),
        "temperature_derating_pct": round(derating_pct, 1),
        "vendor_pressure_class": vendor_pressure_class or "bilinmiyor (temsili)",
        "leakage_class_recommended": recommended_leakage,
        "allowable_leakage": leakage_info,
        "vendor_leakage_class": vendor_leakage_class or "bilinmiyor (temsili)",
        "fail_safe_recommended": recommend_fail_safe(service, application),
        "flow_regime": regime,
        "note": note,
    }


def recommend_bonnet_type(temperature_c: float, service: str = "liquid", fluid_name: str = "") -> str:
    """Recommend control valve bonnet design based on operating temperature and media."""
    t = float(temperature_c)
    fluid_lower = fluid_name.lower().strip()
    if t < -46.0 or any(k in fluid_lower for k in ("lng", "methane", "liquid nitrogen", "kriyojenik", "cryogenic", "oxygen")):
        return "Kriyojenik Uzatılmış Boyun (Cryogenic Extended Bonnet, SS316)"
    if t > 450.0:
        return "Yüksek Sıcaklık Uzatılmış Boyun (High-Temp Extension Bonnet, WC6/316H)"
    if t > 230.0 or (service == "steam" and t > 200.0):
        return "Radyatör Kanatlı Boyun (Radiation Finned Bonnet)"
    return "Standart Düz Boyun (Standard Plain Bonnet)"


@dataclass(frozen=True)
class MaterialRecommendation:
    """Body and trim material recommendation based on fluid and temperature."""

    body_material: str
    trim_material: str
    stem_material: str
    design_standard: str
    nace_compliant: bool
    temperature_limits_c: tuple[float, float]
    recommendations: list[str] = field(default_factory=list)


def recommend_alloy_material(
    service: str,
    fluid_name: str,
    temperature_c: float,
    is_sour: bool = False,
    is_h2: bool = False,
) -> MaterialRecommendation:
    """Recommend body, trim, and stem materials per ASME B31.3, NACE MR0175, and API 941."""
    f = fluid_name.lower().strip()
    t = float(temperature_c)
    sour = is_sour or any(k in f for k in ("h2s", "sour", "acid", "kükürt", "kukurt"))
    h2 = is_h2 or any(k in f for k in ("hydrogen", "hidrojen", "syngas", "sentez gaz"))

    recs: list[str] = []

    if sour:
        body = "ASTM A351 CF8M (316SS) veya A216 WCB + NACE Isıl İşlem"
        trim = "316SS + Stellite 6 Kaplama (Sit/Klape)"
        stem = "Inconel 718 (UNS N07718)"
        std = "NACE MR0175 / ISO 15156"
        nace = True
        limits = (-50.0, 400.0)
        recs.append("Ekşi gaz servisi: Islak yüzeylerde sertlik <= 22 HRC sınırına kesinlikle uyulmalıdır.")
        recs.append("Mil malzemesi gerilmeli korozyon çatlağına direnç için Inconel 718 seçilmiştir.")
    elif h2:
        if t > 230.0:
            body = "ASTM A217 WC6 (1.25Cr-0.5Mo) veya WC9 (2.25Cr-1Mo)"
            trim = "410SS Isıl İşlemli + Stellite 6"
            stem = "316SS veya 17-4PH (H1150M)"
            std = "API 941 (Nelson Curves) / ASME B31.3"
            nace = False
            limits = (-29.0, 550.0)
            recs.append("Yüksek sıcaklık H2: Yüksek Sıcaklık Hidrojen Hasarı (HTHA) ve dekarbürizasyona karşı Cr-Mo alaşımı zorunludur.")
        else:
            body = "ASTM A216 WCB (Karbon Çeliği)"
            trim = "316SS / CoCr"
            stem = "316SS"
            std = "ASME B31.3"
            nace = False
            limits = (-29.0, 230.0)
            recs.append("Düşük sıcaklık H2 servisi için WCB karbon çeliği kabul edilebilirdir.")
    elif t < -46.0 or "lng" in f:
        body = "ASTM A351 CF8M / CF3M (316L SS)"
        trim = "316SS + Kel-F / PCTFE Yumuşak Sit veya Stellite 6"
        stem = "316SS / XM-19 (Nitronic 50)"
        std = "ASME B31.3 Kriyojenik Şartname (-196 °C Charpy Darbe Testi)"
        nace = False
        limits = (-196.0, 200.0)
        recs.append("Kriyojenik servis: Ferritik çelikler gevrekleşir; östenitik paslanmaz çelik (CF8M/CF3M) zorunludur.")
    elif any(k in f for k in ("seawater", "deniz suyu", "brine", "tuzlu su", "chlorine", "klor")):
        body = "ASTM A890 Gr 4A (Duplex 2205) veya Monel 400"
        trim = "Duplex 2205 / Hastelloy C-276"
        stem = "Inconel 625 veya K-500 Monel"
        std = "Norsok M-630 / ASTM A890"
        nace = False
        limits = (-40.0, 250.0)
        recs.append("Klorür ve deniz suyu çukurcuk korozyonuna karşı Duplex / Süper Duplex alaşım seçilmiştir.")
    elif t > 425.0 or (service == "steam" and t > 400.0):
        body = "ASTM A217 WC6 (1.25Cr-0.5Mo) veya WC9"
        trim = "Stellite 6 Komple Masif / 410SS Sertleştirilmiş"
        stem = "316H Paslanmaz Çelik veya Inconel 718"
        std = "ASME B16.34 Yüksek Sıcaklık Grubu 1.9"
        nace = False
        limits = (-29.0, 538.0)
        recs.append("Yüksek sıcaklık buhar/gaz: Sünme (creep) mukavemeti için Krom-Molibden WC6 alaşımı seçilmiştir.")
    elif t > 250.0 or any(k in f for k in ("acid", "asit", "oil", "yağ", "yag")):
        body = "ASTM A351 CF8M (316SS)"
        trim = "316SS + Stellite 6 Kaplama"
        stem = "316SS"
        std = "ASME B16.34 Grup 2.2"
        nace = False
        limits = (-50.0, 450.0)
        recs.append("Korozif / yüksek sıcaklık proses servisi için 316 Paslanmaz Çelik önerilir.")
    else:
        body = "ASTM A216 WCB (Döküm Karbon Çeliği)"
        trim = "316SS / 410SS"
        stem = "316SS"
        std = "ASME B16.34 Grup 1.1"
        nace = False
        limits = (-29.0, 425.0)
        recs.append("Genel endüstriyel sıvı/gaz servisi için ekonomik standart karbon çeliği gövde uygundur.")

    return MaterialRecommendation(
        body_material=body,
        trim_material=trim,
        stem_material=stem,
        design_standard=std,
        nace_compliant=nace,
        temperature_limits_c=limits,
        recommendations=recs,
    )
