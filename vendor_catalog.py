"""Vendor catalog definitions for control valve selection.

Contains Emerson Fisher, Metso/Neles (Valmet), SAMSON, and ARCA
representative sizing coefficients (Fl, Xt, Fd, Cv series) for multiple
valve styles.  Exposes get_vendor_definition, get_vendor_options, and
the ValveSize dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    region: str = "Global"


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

MASONEILAN_VENDOR_CATALOG: dict[str, VendorValveDefinition] = {
    "masoneilan_camflex_eqpct": VendorValveDefinition(
        key="masoneilan_camflex_eqpct",
        vendor="Baker Hughes Masoneilan",
        family="Camflex II",
        style="Rotary Eccentric Plug (Equal-Percentage)",
        service="liquid_gas_steam",
        source_note="Baker Hughes Masoneilan Camflex II 35002 Series technical specifications.",
        source_url="https://www.bakerhughes.com/valves/control-valves/rotary-control-valves/camflex-ii",
        fl=0.82,
        xt=0.58,
        fd=0.50,
        opening_desc="Rated 50-degree rotation values",
        region="USA",
        sizes=(
            ValveSize(25, '1"', 28.0),
            ValveSize(40, '1 1/2"', 60.0),
            ValveSize(50, '2"', 110.0),
            ValveSize(80, '3"', 235.0),
            ValveSize(100, '4"', 380.0),
            ValveSize(150, '6"', 780.0),
            ValveSize(200, '8"', 1300.0),
        ),
    ),
    "masoneilan_globe_21000": VendorValveDefinition(
        key="masoneilan_globe_21000",
        vendor="Baker Hughes Masoneilan",
        family="21000 Series",
        style="Top-Guided Single-Seated Globe",
        service="liquid_gas_steam",
        source_note="Baker Hughes Masoneilan 21000 Series heavy-duty globe specification.",
        source_url="https://www.bakerhughes.com/valves/control-valves/reciprocating-control-valves/21000-series",
        fl=0.86,
        xt=0.70,
        fd=0.35,
        opening_desc="Rated travel representative values",
        region="USA",
        sizes=(
            ValveSize(20, '3/4"', 7.5),
            ValveSize(25, '1"', 17.5),
            ValveSize(40, '1 1/2"', 36.0),
            ValveSize(50, '2"', 62.0),
            ValveSize(80, '3"', 140.0),
            ValveSize(100, '4"', 230.0),
            ValveSize(150, '6"', 420.0),
            ValveSize(200, '8"', 800.0),
        ),
    ),
}

FLOWSERVE_VENDOR_CATALOG: dict[str, VendorValveDefinition] = {
    "flowserve_valtek_mark_one": VendorValveDefinition(
        key="flowserve_valtek_mark_one",
        vendor="Flowserve Valtek",
        family="Mark One",
        style="High-Performance Top-Guided Globe",
        service="liquid_gas_steam",
        source_note="Flowserve Valtek Mark One control valve technical bulletin VLAXBR0001.",
        source_url="https://www.flowserve.com/en/products/catalogs/control-valves/globe-control-valves/valtek-mark-one-globe-control-valve/",
        fl=0.85,
        xt=0.72,
        fd=0.40,
        opening_desc="Rated stroke representative values",
        region="USA",
        sizes=(
            ValveSize(15, '1/2"', 4.2),
            ValveSize(20, '3/4"', 7.8),
            ValveSize(25, '1"', 18.0),
            ValveSize(40, '1 1/2"', 38.0),
            ValveSize(50, '2"', 65.0),
            ValveSize(80, '3"', 145.0),
            ValveSize(100, '4"', 240.0),
            ValveSize(150, '6"', 450.0),
            ValveSize(200, '8"', 820.0),
        ),
    ),
    "flowserve_maxflo_rotary": VendorValveDefinition(
        key="flowserve_maxflo_rotary",
        vendor="Flowserve Valtek",
        family="MaxFlo 4",
        style="Eccentric Rotary Plug Valve",
        service="liquid_gas_steam",
        source_note="Flowserve MaxFlo 4 technical bulletin for rotary control applications.",
        source_url="https://www.flowserve.com/en/products/catalogs/control-valves/rotary-control-valves/maxflo-4-eccentric-rotary-plug-control-valve/",
        fl=0.78,
        xt=0.45,
        fd=0.60,
        opening_desc="90-degree opening representative values",
        region="USA",
        sizes=(
            ValveSize(25, '1"', 30.0),
            ValveSize(40, '1 1/2"', 68.0),
            ValveSize(50, '2"', 120.0),
            ValveSize(80, '3"', 290.0),
            ValveSize(100, '4"', 540.0),
            ValveSize(150, '6"', 1020.0),
            ValveSize(200, '8"', 1750.0),
        ),
    ),
}

IMI_VENDOR_CATALOG: dict[str, VendorValveDefinition] = {
    "imi_cci_severe_globe": VendorValveDefinition(
        key="imi_cci_severe_globe",
        vendor="IMI Critical (CCI)",
        family="100D / 300D Series",
        style="Severe Service & Power Letdown Globe",
        service="liquid_gas_steam",
        source_note="IMI Critical Engineering (CCI / Bopp & Reuther) high-pressure severe service valve catalog.",
        source_url="https://www.imi-critical.com/products/control-valves/",
        fl=0.90,
        xt=0.75,
        fd=0.30,
        opening_desc="Rated stroke representative values",
        region="Europe",
        pressure_class="CL600",
        leakage_class="V",
        sizes=(
            ValveSize(25, '1"', 16.0),
            ValveSize(40, '1 1/2"', 34.0),
            ValveSize(50, '2"', 58.0),
            ValveSize(80, '3"', 130.0),
            ValveSize(100, '4"', 215.0),
            ValveSize(150, '6"', 390.0),
            ValveSize(200, '8"', 760.0),
        ),
    ),
    "imi_cci_drag_disk": VendorValveDefinition(
        key="imi_cci_drag_disk",
        vendor="IMI Critical (CCI)",
        family="DRAG Disk Stack",
        style="Multi-Stage Cavitation & Noise Elimination Globe",
        service="liquid_gas_steam",
        source_note="IMI CCI DRAG multi-path multi-stage pressure letdown disk stack technology.",
        source_url="https://www.imi-critical.com/products/drag-control-valves/",
        fl=0.98,
        xt=0.82,
        fd=0.15,
        opening_desc="Rated stroke representative values",
        region="Europe",
        pressure_class="CL1500",
        leakage_class="V",
        sizes=(
            ValveSize(25, '1"', 12.0),
            ValveSize(40, '1 1/2"', 25.0),
            ValveSize(50, '2"', 42.0),
            ValveSize(80, '3"', 95.0),
            ValveSize(100, '4"', 165.0),
            ValveSize(150, '6"', 310.0),
            ValveSize(200, '8"', 580.0),
        ),
    ),
}

WUZHONG_VENDOR_CATALOG: dict[str, VendorValveDefinition] = {
    "wuzhong_globe_300": VendorValveDefinition(
        key="wuzhong_globe_300",
        vendor="WuZhong Instrument (WZI)",
        family="Series 300",
        style="Cage-Guided Pressure-Balanced Globe",
        service="liquid_gas_steam",
        source_note="WuZhong Instrument Co., Ltd. (China) Series 300 cage-guided control valve specification.",
        source_url="https://www.wzi.com.cn/",
        fl=0.85,
        xt=0.68,
        fd=0.32,
        opening_desc="Rated travel representative values",
        region="Asia (China)",
        sizes=(
            ValveSize(25, '1"', 16.5),
            ValveSize(40, '1 1/2"', 35.0),
            ValveSize(50, '2"', 58.5),
            ValveSize(80, '3"', 132.0),
            ValveSize(100, '4"', 220.0),
            ValveSize(150, '6"', 390.0),
            ValveSize(200, '8"', 800.0),
        ),
    ),
    "wuzhong_rotary_200": VendorValveDefinition(
        key="wuzhong_rotary_200",
        vendor="WuZhong Instrument (WZI)",
        family="Series 200",
        style="Eccentric Rotary Control Valve",
        service="liquid_gas_steam",
        source_note="WuZhong Instrument Co., Ltd. (China) Series 200 rotary plug valve specification.",
        source_url="https://www.wzi.com.cn/",
        fl=0.80,
        xt=0.52,
        fd=0.55,
        opening_desc="90-degree opening representative values",
        region="Asia (China)",
        sizes=(
            ValveSize(25, '1"', 29.0),
            ValveSize(40, '1 1/2"', 65.0),
            ValveSize(50, '2"', 115.0),
            ValveSize(80, '3"', 280.0),
            ValveSize(100, '4"', 520.0),
            ValveSize(150, '6"', 980.0),
            ValveSize(200, '8"', 1680.0),
        ),
    ),
}

AZBIL_VENDOR_CATALOG: dict[str, VendorValveDefinition] = {
    "azbil_globe_ag9000": VendorValveDefinition(
        key="azbil_globe_ag9000",
        vendor="Azbil (Yamatake)",
        family="AG9000 Series",
        style="Top-Guided Single-Seated Globe",
        service="liquid_gas_steam",
        source_note="Azbil Corporation (Japan) AG9000 / AG9100 Series control valve technical document.",
        source_url="https://www.azbil.com/products/bi/valves/control-valves/globe.html",
        fl=0.86,
        xt=0.70,
        fd=0.33,
        opening_desc="Rated stroke representative values",
        region="Asia (Japan)",
        sizes=(
            ValveSize(20, '3/4"', 7.2),
            ValveSize(25, '1"', 16.8),
            ValveSize(40, '1 1/2"', 35.2),
            ValveSize(50, '2"', 60.0),
            ValveSize(80, '3"', 135.0),
            ValveSize(100, '4"', 225.0),
            ValveSize(150, '6"', 400.0),
            ValveSize(200, '8"', 810.0),
        ),
    ),
    "azbil_rotary_act": VendorValveDefinition(
        key="azbil_rotary_act",
        vendor="Azbil (Yamatake)",
        family="ACT Series",
        style="Eccentric Rotary Control Valve",
        service="liquid_gas_steam",
        source_note="Azbil Corporation ACT Series rotary control valve technical documentation.",
        source_url="https://www.azbil.com/products/bi/valves/control-valves/rotary.html",
        fl=0.78,
        xt=0.48,
        fd=0.58,
        opening_desc="90-degree opening representative values",
        region="Asia (Japan)",
        sizes=(
            ValveSize(25, '1"', 31.0),
            ValveSize(40, '1 1/2"', 68.0),
            ValveSize(50, '2"', 118.0),
            ValveSize(80, '3"', 285.0),
            ValveSize(100, '4"', 530.0),
            ValveSize(150, '6"', 1000.0),
            ValveSize(200, '8"', 1720.0),
        ),
    ),
}

VENDOR_CATALOG: dict[str, VendorValveDefinition] = {}
for _cat in (
    FISHER_VENDOR_CATALOG,
    MASONEILAN_VENDOR_CATALOG,
    FLOWSERVE_VENDOR_CATALOG,
    METSO_VENDOR_CATALOG,
    SAMSON_VENDOR_CATALOG,
    ARCA_VENDOR_CATALOG,
    IMI_VENDOR_CATALOG,
    WUZHONG_VENDOR_CATALOG,
    AZBIL_VENDOR_CATALOG,
):
    VENDOR_CATALOG.update(_cat)


def get_vendor_options() -> list[str]:
    return list(VENDOR_CATALOG.keys())


def get_vendor_definition(key: str) -> VendorValveDefinition:
    if key not in VENDOR_CATALOG:
        raise ValueError(f"Bilinmeyen vendor anahtari: {key}")
    return VENDOR_CATALOG[key]


@dataclass(frozen=True)
class CatalogValveMatch:
    vendor_key: str
    vendor_name: str
    region: str
    family: str
    style: str
    dn_mm: int
    dn_inch: str
    rated_cv: float
    required_cv: float
    opening_pct: float
    status: str
    status_label: str
    pressure_class: str
    leakage_class: str
    fl: float
    xt: float

    def __getitem__(self, key: str) -> Any:
        aliases = {
            "manufacturer": "vendor_name",
            "model_name": "family",
            "valve_type": "style",
            "inch": "dn_inch",
            "cv_rated": "rated_cv",
            "opening_percent": "opening_pct",
        }
        return getattr(self, aliases.get(key, key))


def find_catalog_matches(
    required_cv: float,
    design_margin_pct: float = 10.0,
    flow_characteristic: str = "equal_percentage",
    rangeability: float = 50.0,
    region_filter: str | None = None,
    vendor_filter: str | None = None,
) -> list[CatalogValveMatch]:
    """Search global vendor catalog and find suitable valve candidates matching required Cv."""
    import math

    if required_cv <= 0:
        return []

    target_cv = required_cv * (1.0 + max(design_margin_pct, 0.0) / 100.0)
    matches: list[CatalogValveMatch] = []

    for v_def in VENDOR_CATALOG.values():
        if region_filter and region_filter.lower() not in v_def.region.lower():
            continue
        if vendor_filter and vendor_filter.lower() not in v_def.vendor.lower():
            continue
        for valve in v_def.sizes:
            if valve.cv_rated < target_cv * 0.90:
                continue
            ratio = min(max(target_cv / valve.cv_rated, 1e-4), 1.0)
            if flow_characteristic == "linear":
                opening = ratio * 100.0
            elif flow_characteristic == "quick_opening":
                opening = math.sqrt(ratio) * 100.0
            else:
                r = max(rangeability, 10.0)
                opening = (1.0 + math.log(ratio) / math.log(r)) * 100.0
                opening = max(0.0, min(opening, 100.0))

            if opening < 5.0 or opening > 98.0:
                continue

            if 20.0 <= opening <= 80.0:
                status = "ideal"
                status_label = "✅ İdeal (%20-%80)"
            elif (10.0 <= opening < 20.0) or (80.0 < opening <= 90.0):
                status = "warning"
                status_label = "⚠️ Sınırda (%10-%20 veya %80-%90)"
            else:
                status = "critical"
                status_label = "❌ Aşırı Açık/Kapalı"

            matches.append(
                CatalogValveMatch(
                    vendor_key=v_def.key,
                    vendor_name=v_def.vendor,
                    region=v_def.region,
                    family=v_def.family,
                    style=v_def.style,
                    dn_mm=valve.dn_mm,
                    dn_inch=valve.inch,
                    rated_cv=valve.cv_rated,
                    required_cv=round(required_cv, 2),
                    opening_pct=round(opening, 1),
                    status=status,
                    status_label=status_label,
                    pressure_class=v_def.pressure_class,
                    leakage_class=v_def.leakage_class,
                    fl=v_def.fl or 0.85,
                    xt=v_def.xt or 0.70,
                )
            )

    matches.sort(
        key=lambda m: (
            0 if m.status == "ideal" else 1 if m.status == "warning" else 2,
            abs(m.opening_pct - 65.0),
        )
    )
    return matches
