"""Vendor catalog definitions for control valve selection.

Contains Emerson Fisher, Metso/Neles (Valmet), SAMSON, and ARCA
representative sizing coefficients (Fl, Xt, Fd, Cv series) for multiple
valve styles.  Exposes get_vendor_definition, get_vendor_options, and
the ValveSize dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass

from valve_sizing import ValveSize


@dataclass(frozen=True)
class VendorValveDefinition:
    key: str
    vendor: str
    family: str
    style: str
    service: str
    source_note: str
    source_url: str
    fl: float | None
    xt: float | None
    fd: float | None
    opening_desc: str
    sizes: tuple[ValveSize, ...]
    pressure_class: str = "CL300"
    leakage_class: str = "IV"


FISHER_VENDOR_CATALOG: dict[str, VendorValveDefinition] = {
    "fisher_globe_eqpct": VendorValveDefinition(
        key="fisher_globe_eqpct",
        vendor="Emerson Fisher",
        family="Representative Globe",
        style="Cage-Guided Equal-Percentage",
        service="liquid_gas_steam",
        source_note="Representative sizing coefficients from Fisher Control Valve Handbook Chapter 5.10.1.",
        source_url="https://www.emerson.com/documents/automation/control-valve-handbook-en-3661206.pdf",
        fl=0.85,
        xt=0.69,
        fd=0.31,
        opening_desc="Rated travel representative values",
        sizes=(
            ValveSize(25, '1"', 17.2),
            ValveSize(40, '1 1/2"', 35.8),
            ValveSize(50, '2"', 59.7),
            ValveSize(80, '3"', 136.0),
            ValveSize(100, '4"', 224.0),
            ValveSize(150, '6"', 394.0),
            ValveSize(200, '8"', 818.0),
        ),
    ),
    "fisher_globe_linear": VendorValveDefinition(
        key="fisher_globe_linear",
        vendor="Emerson Fisher",
        family="Representative Globe",
        style="Cage-Guided Linear",
        service="liquid_gas_steam",
        source_note="Representative sizing coefficients from Fisher Control Valve Handbook Chapter 5.10.1.",
        source_url="https://www.emerson.com/documents/automation/control-valve-handbook-en-3661206.pdf",
        fl=0.82,
        xt=0.64,
        fd=0.30,
        opening_desc="Rated travel representative values",
        sizes=(
            ValveSize(25, '1"', 20.6),
            ValveSize(40, '1 1/2"', 39.2),
            ValveSize(50, '2"', 72.9),
            ValveSize(80, '3"', 148.0),
            ValveSize(100, '4"', 236.0),
            ValveSize(150, '6"', 433.0),
            ValveSize(200, '8"', 846.0),
        ),
    ),
    "fisher_vnotch_90": VendorValveDefinition(
        key="fisher_vnotch_90",
        vendor="Emerson Fisher",
        family="Representative Rotary",
        style="V-Notch Ball Valve",
        service="liquid_gas_steam",
        source_note="Representative sizing coefficients from Fisher Control Valve Handbook Chapter 5.10.2 at 90 degrees opening. "
                     "Metal-seal Cv reference: Fisher Vee-Ball Design V150/V200/V300 Bulletin D101363X012 and capacity MOC D352710X012 "
                     "(1 in=33.1, 1-1/2 in=70.8, 2 in=122).",
        source_url="https://www.emerson.com/is/content/emerson/en/final-control/flow-controls/documents/d101363x012.pdf",
        fl=0.74,
        xt=0.27,
        fd=0.99,
        opening_desc="90 degree opening representative values",
        sizes=(
            ValveSize(25, '1"', 34.0),
            ValveSize(40, '1 1/2"', 77.3),
            ValveSize(50, '2"', 132.0),
            ValveSize(80, '3"', 321.0),
            ValveSize(100, '4"', 596.0),
            ValveSize(150, '6"', 1100.0),
            ValveSize(200, '8"', 1820.0),
            ValveSize(250, '10"', 3000.0),
        ),
    ),
    "fisher_bfly_90": VendorValveDefinition(
        key="fisher_bfly_90",
        vendor="Emerson Fisher",
        family="Representative Rotary",
        style="High-Performance Butterfly Valve",
        service="liquid_gas_steam",
        source_note="Representative sizing coefficients from Fisher Control Valve Handbook Chapter 5.10.2 at 90 degrees opening.",
        source_url="https://www.emerson.com/documents/automation/control-valve-handbook-en-3661206.pdf",
        fl=0.55,
        xt=0.20,
        fd=0.70,
        opening_desc="90 degree opening representative values",
        sizes=(
            ValveSize(50, '2"', 80.2),
            ValveSize(80, '3"', 237.0),
            ValveSize(100, '4"', 499.0),
            ValveSize(150, '6"', 1260.0),
            ValveSize(200, '8"', 2180.0),
            ValveSize(250, '10"', 3600.0),
            ValveSize(300, '12"', 5400.0),
        ),
    ),
}

METSO_VENDOR_CATALOG: dict[str, VendorValveDefinition] = {
    "metso_globe_eqpct": VendorValveDefinition(
        key="metso_globe_eqpct",
        vendor="Metso (Valmet)",
        family="Representative Globe",
        style="Finetrol Globe Equal-Percentage",
        service="liquid_gas_steam",
        source_note="Representative coefficients based on Metso/Valmet control valve sizing catalog; "
                     "typical globe valve with equal-percentage characterized cage.",
        source_url="https://www.valmet.com/flowcontrol/products/control-valves/",
        fl=0.85,
        xt=0.65,
        fd=0.30,
        opening_desc="Rated travel representative values",
        sizes=(
            ValveSize(25, '1"', 15.0),
            ValveSize(40, '1 1/2"', 30.0),
            ValveSize(50, '2"', 55.0),
            ValveSize(80, '3"', 125.0),
            ValveSize(100, '4"', 210.0),
            ValveSize(150, '6"', 380.0),
            ValveSize(200, '8"', 750.0),
        ),
    ),
    "metso_vport": VendorValveDefinition(
        key="metso_vport",
        vendor="Metso (Valmet)",
        family="Representative Rotary",
        style="V-Port Segment Ball Valve",
        service="liquid_gas_steam",
        source_note="Representative coefficients based on Metso/Valmet Neldisc segment valve catalog; typical V-port ball valve at 90 degrees.",
        source_url="https://www.valmet.com/flowcontrol/products/control-valves/segment-valves/",
        fl=0.70,
        xt=0.35,
        fd=0.98,
        opening_desc="90 degree opening representative values",
        sizes=(
            ValveSize(25, '1"', 28.0),
            ValveSize(40, '1 1/2"', 65.0),
            ValveSize(50, '2"', 115.0),
            ValveSize(80, '3"', 280.0),
            ValveSize(100, '4"', 510.0),
            ValveSize(150, '6"', 950.0),
            ValveSize(200, '8"', 1550.0),
        ),
    ),
    "metso_bfly_disc": VendorValveDefinition(
        key="metso_bfly_disc",
        vendor="Metso (Valmet)",
        family="Representative Rotary",
        style="Disc Butterfly Valve",
        service="liquid_gas_steam",
        source_note="Representative coefficients based on Metso/Valmet butterfly valve catalog; typical disc butterfly at 90 degrees.",
        source_url="https://www.valmet.com/flowcontrol/products/control-valves/butterfly-valves/",
        fl=0.65,
        xt=0.25,
        fd=0.75,
        opening_desc="90 degree opening representative values",
        sizes=(
            ValveSize(50, '2"', 75.0),
            ValveSize(80, '3"', 220.0),
            ValveSize(100, '4"', 450.0),
            ValveSize(150, '6"', 1100.0),
            ValveSize(200, '8"', 1900.0),
            ValveSize(250, '10"', 3200.0),
            ValveSize(300, '12"', 5000.0),
        ),
    ),
}

SAMSON_VENDOR_CATALOG: dict[str, VendorValveDefinition] = {
    "samson_globe_eqpct": VendorValveDefinition(
        key="samson_globe_eqpct",
        vendor="SAMSON",
        family="Representative Globe",
        style="Type 324x Globe Equal-Percentage",
        service="liquid_gas_steam",
        source_note="Representative coefficients based on SAMSON Type 3241/3244 series control valve sizing data sheet.",
        source_url="https://www.samsongroup.com/en/products-solutions/control-valves/",
        fl=0.90,
        xt=0.70,
        fd=0.35,
        opening_desc="Rated travel representative values",
        sizes=(
            ValveSize(25, '1"', 18.0),
            ValveSize(40, '1 1/2"', 38.0),
            ValveSize(50, '2"', 62.0),
            ValveSize(80, '3"', 140.0),
            ValveSize(100, '4"', 230.0),
            ValveSize(150, '6"', 410.0),
            ValveSize(200, '8"', 830.0),
        ),
    ),
    "samson_rotary_plug": VendorValveDefinition(
        key="samson_rotary_plug",
        vendor="SAMSON",
        family="Representative Rotary",
        style="Type 3335 Rotary Plug Valve",
        service="liquid_gas_steam",
        source_note="Representative coefficients based on SAMSON Type 3335 rotary plug valve catalog; 90 degree opening.",
        source_url="https://www.samsongroup.com/en/products-solutions/control-valves/rotary-plug-valves/",
        fl=0.75,
        xt=0.30,
        fd=0.95,
        opening_desc="90 degree opening representative values",
        sizes=(
            ValveSize(25, '1"', 35.0),
            ValveSize(40, '1 1/2"', 80.0),
            ValveSize(50, '2"', 135.0),
            ValveSize(80, '3"', 320.0),
            ValveSize(100, '4"', 600.0),
            ValveSize(150, '6"', 1150.0),
            ValveSize(200, '8"', 1850.0),
        ),
    ),
    "samson_triple_offset": VendorValveDefinition(
        key="samson_triple_offset",
        vendor="SAMSON",
        family="Representative Rotary",
        style="Type 33x Triple-Offset Butterfly Valve",
        service="liquid_gas_steam",
        source_note="Representative coefficients based on SAMSON Type 33x triple-offset butterfly valve series; 90 degree opening.",
        source_url="https://www.samsongroup.com/en/products-solutions/control-valves/high-performance-butterfly-valves/",
        fl=0.60,
        xt=0.22,
        fd=0.65,
        opening_desc="90 degree opening representative values",
        sizes=(
            ValveSize(50, '2"', 85.0),
            ValveSize(80, '3"', 250.0),
            ValveSize(100, '4"', 520.0),
            ValveSize(150, '6"', 1300.0),
            ValveSize(200, '8"', 2250.0),
            ValveSize(250, '10"', 3700.0),
            ValveSize(300, '12"', 5600.0),
        ),
    ),
}

ARCA_VENDOR_CATALOG: dict[str, VendorValveDefinition] = {
    "arca_globe_eqpct": VendorValveDefinition(
        key="arca_globe_eqpct",
        vendor="ARCA",
        family="Representative Globe",
        style="Globe Valve Equal-Percentage",
        service="liquid_gas_steam",
        source_note="Representative coefficients based on ARCA control valve catalog; globe valve with characterized cage.",
        source_url="https://www.arca-valves.com/products/control-valves/globe-valves/",
        fl=0.88,
        xt=0.68,
        fd=0.32,
        opening_desc="Rated travel representative values",
        sizes=(
            ValveSize(25, '1"', 16.0),
            ValveSize(40, '1 1/2"', 33.0),
            ValveSize(50, '2"', 57.0),
            ValveSize(80, '3"', 130.0),
            ValveSize(100, '4"', 215.0),
            ValveSize(150, '6"', 395.0),
            ValveSize(200, '8"', 780.0),
        ),
    ),
    "arca_rotary_plug": VendorValveDefinition(
        key="arca_rotary_plug",
        vendor="ARCA",
        family="Representative Rotary",
        style="Rotary Plug Valve",
        service="liquid_gas_steam",
        source_note="Representative coefficients based on ARCA rotary plug valve catalog; typical 90 degree opening values.",
        source_url="https://www.arca-valves.com/products/control-valves/rotary-valves/",
        fl=0.73,
        xt=0.32,
        fd=0.97,
        opening_desc="90 degree opening representative values",
        sizes=(
            ValveSize(25, '1"', 32.0),
            ValveSize(40, '1 1/2"', 72.0),
            ValveSize(50, '2"', 125.0),
            ValveSize(80, '3"', 300.0),
            ValveSize(100, '4"', 560.0),
            ValveSize(150, '6"', 1050.0),
            ValveSize(200, '8"', 1700.0),
        ),
    ),
}

VENDOR_CATALOG: dict[str, VendorValveDefinition] = {}
for _cat in (FISHER_VENDOR_CATALOG, METSO_VENDOR_CATALOG, SAMSON_VENDOR_CATALOG, ARCA_VENDOR_CATALOG):
    VENDOR_CATALOG.update(_cat)


def get_vendor_options() -> list[str]:
    return list(VENDOR_CATALOG.keys())


def get_vendor_definition(key: str) -> VendorValveDefinition:
    if key not in VENDOR_CATALOG:
        raise ValueError(f"Bilinmeyen vendor anahtari: {key}")
    return VENDOR_CATALOG[key]
