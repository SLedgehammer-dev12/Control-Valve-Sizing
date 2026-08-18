"""Valve specification guidance (ANSI class, leakage class, fail-safe).

Provides recommendation helpers for ASME B16.34 pressure class, ASME
B16.104 / IEC 60534-4 leakage class, and fail-safe action based on the
sizing result and service. These are engineering guidelines; the final
specification must be confirmed against the line class and the process
safety / HAZOP analysis.
"""

from __future__ import annotations

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


def recommend_pressure_class(inlet_pressure_bar: float) -> str:
    """Return the minimum ANSI/ASME B16.34 pressure class for the inlet pressure.

    Uses ambient-temperature carbon-steel class ratings; temperature
    derating and material selection must be confirmed separately.
    """
    if inlet_pressure_bar <= 0:
        return "CL150"
    for cls in PRESSURE_CLASS_ORDER:
        if inlet_pressure_bar <= ANSI_CLASS_AMBIENT_BAR[cls]:
            return cls
    return "CL2500"


def recommend_leakage_class(service: str, is_choked: bool = False) -> str:
    """Recommend an ASME B16.104 / IEC 60534-4 seat leakage class.

    Severe or compressible service benefits from tighter shutoff.
    """
    if service == "gas" or is_choked:
        return "VI"
    if service == "steam":
        return "V"
    return "IV"


def recommend_fail_safe(service: str, application: str = "") -> str:
    """Recommend a fail-safe action based on service and application hint.

    This is a guideline only; the final action must come from the process
    safety analysis (HAZOP) and the plant's functional safety requirements.
    """
    app = application.strip().lower()
    if "cooling" in app or "so\u011futma" in app:
        return "fail-open (acik kalarak sogutma korunur)"
    if "fuel" in app or "yak\u0131t" in app:
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
) -> dict[str, str]:
    """Build a valve specification guidance dictionary.

    Parameters
    ----------
    service : "liquid", "gas", or "steam"
    inlet_pressure_bar : Inlet pressure [bar(a)]
    is_choked : Choked-flow flag from the sizing result
    regime : Flow regime label (liquid services)
    application : Optional application hint (e.g. "cooling water")
    vendor_pressure_class : Vendor body class if known, else ""
    vendor_leakage_class : Vendor seat leakage class if known, else ""
    """
    recommended_class = recommend_pressure_class(inlet_pressure_bar)
    recommended_leakage = recommend_leakage_class(service, is_choked or regime == "flashing")
    note = (
        "ASME B16.34 sinifi girise gore ambiyant onerisidir; sicaklik deratingi, "
        "boru hat sinifi ve malzeme secimi ayrica dogrulanmalidir. Fail-safe nihai "
        "karari HAZOP / proses guvenlik analizine aittir."
    )
    return {
        "service": service,
        "inlet_pressure_bar": f"{inlet_pressure_bar:.2f}",
        "pressure_class_recommended": recommended_class,
        "vendor_pressure_class": vendor_pressure_class or "bilinmiyor (temsili)",
        "leakage_class_recommended": recommended_leakage,
        "vendor_leakage_class": vendor_leakage_class or "bilinmiyor (temsili)",
        "fail_safe_recommended": recommend_fail_safe(service, application),
        "flow_regime": regime,
        "note": note,
    }
