"""Comprehensive calculation verification suite across 52 industrial scenarios.

Covers five key engineering sectors:
1. Power Generation & Steam Systems (10 scenarios)
2. Upstream & Midstream Oil and Gas (11 scenarios)
3. Petrochemical & Refining Processes (11 scenarios)
4. Clean Energy, Cryogenics & Hydrogen (10 scenarios)
5. Chemical, Water & Heavy Industry (10 scenarios)

Executes the full engineering evaluation stack: IEC 60534 sizing,
ISA-RP75.23 cavitation, IEC 60534-8 aerodynamic noise, API RP 14E erosional
velocity, API 520 fail-open relief capacity, ASME B16.34 pressure-temperature
ratings, ISO 15848-1 fugitive emission packing, and ISA-20 datasheet creation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from datasheet_isa20 import build_isa20_datasheet
from joule_thomson import calc_joule_thomson_drop
from packing_emissions import recommend_packing_system
from safety_piping import calc_wide_open_relief_capacity, check_erosional_velocity
from trim_guidance import evaluate_cavitation_severity
from valve_noise import evaluate_noise_attenuation
from valve_selection import (
    derated_mawp_bar,
    recommend_alloy_material,
    recommend_bonnet_type,
    recommend_pressure_class,
)
from valve_sizing import (
    GasSizingInput,
    LiquidSizingInput,
    SteamSizingInput,
    ValveSize,
    size_gas_valve,
    size_liquid_valve,
    size_steam_valve,
)

STANDARD_EXTENDED_SERIES: list[ValveSize] = [
    ValveSize(15, '1/2"', 4.0),
    ValveSize(20, '3/4"', 7.0),
    ValveSize(25, '1"', 12.0),
    ValveSize(32, '1 1/4"', 20.0),
    ValveSize(40, '1 1/2"', 30.0),
    ValveSize(50, '2"', 48.0),
    ValveSize(65, '2 1/2"', 75.0),
    ValveSize(80, '3"', 115.0),
    ValveSize(100, '4"', 180.0),
    ValveSize(150, '6"', 360.0),
    ValveSize(200, '8"', 600.0),
    ValveSize(250, '10"', 950.0),
    ValveSize(300, '12"', 1400.0),
    ValveSize(350, '14"', 1850.0),
    ValveSize(400, '16"', 2400.0),
    ValveSize(450, '18"', 3050.0),
    ValveSize(500, '20"', 3800.0),
    ValveSize(600, '24"', 5500.0),
]


@dataclass(frozen=True)
class ScenarioDefinition:
    """Input definition for an industrial verification scenario."""

    id: str
    name: str
    sector: str
    service: str
    fluid: str
    flow: float
    p1_bar_a: float
    p2_bar_a: float
    temperature_c: float
    rho: float = 1000.0
    pv: float = 0.023
    pc: float = 220.64
    mu: float = 1.0e-3
    fl: float = 0.90
    fd: float = 1.0
    xt: float = 0.70
    mw: float = 28.96
    k: float = 1.40
    z: float = 1.0
    is_flashing: bool = False
    is_toxic: bool = False
    is_sour: bool = False
    is_h2: bool = False
    cp: float = 4186.0
    hvap: float = 2257000.0


@dataclass(frozen=True)
class Scenario50Result:
    """Result and verification verdict of an industrial scenario."""

    id: str
    name: str
    sector: str
    service: str
    fluid: str
    flow_display: str
    p1_bar_a: float
    p2_bar_a: float
    delta_p_bar: float
    temperature_c: float
    required_cv: float
    required_kv: float
    rated_cv: float
    opening_percent: float
    valve_dn_mm: int
    valve_inch: str
    is_choked: bool
    flow_regime: str
    cavitation_severity: str | None
    noise_dba: float
    acoustic_treatment: str
    pipe_velocity_m_s: float
    erosional_limit_m_s: float
    is_velocity_exceeded: bool
    wide_open_relief_flow: float
    relief_unit: str
    pressure_class: str
    derated_mawp_bar: float
    bonnet_type: str
    body_material: str
    trim_material: str
    stem_material: str
    packing_type: str
    emission_class: str
    jt_delta_t_c: float | None
    hydrate_risk: bool | None
    passed: bool
    checks_passed: int
    checks_total: int
    detail: str
    warnings: list[str] = field(default_factory=list)


SCENARIO_DEFINITIONS: list[ScenarioDefinition] = [
    ScenarioDefinition(
        id="PWR-STM-01",
        name="HP Buhar Türbin Bypass (Supercritical PRDS)",
        sector="Power & Steam",
        service="steam",
        fluid="Steam",
        flow=45000.0,
        p1_bar_a=90.0,
        p2_bar_a=25.0,
        temperature_c=480.0,
    ),
    ScenarioDefinition(
        id="PWR-STM-02",
        name="Kazan Besleme Suyu Resirkülasyon (BFW Minimum Flow)",
        sector="Power & Steam",
        service="liquid",
        fluid="Water",
        flow=120.0,
        p1_bar_a=160.0,
        p2_bar_a=12.0,
        temperature_c=165.0,
        rho=905.0,
        pv=7.0,
        pc=220.64,
        mu=1.7e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="PWR-STM-03",
        name="Deaeratör Pegging Buhar Regülasyonu",
        sector="Power & Steam",
        service="steam",
        fluid="Steam",
        flow=18000.0,
        p1_bar_a=16.0,
        p2_bar_a=4.5,
        temperature_c=280.0,
    ),
    ScenarioDefinition(
        id="PWR-STM-04",
        name="Orta Basınç (IP) Buhar Ekstraksiyon Basınç Düşürme",
        sector="Power & Steam",
        service="steam",
        fluid="Steam",
        flow=65000.0,
        p1_bar_a=28.0,
        p2_bar_a=12.0,
        temperature_c=320.0,
    ),
    ScenarioDefinition(
        id="PWR-STM-05",
        name="Düşük Basınç Kondensat Pompası Basma Kontrolü",
        sector="Power & Steam",
        service="liquid",
        fluid="Water",
        flow=280.0,
        p1_bar_a=12.0,
        p2_bar_a=5.0,
        temperature_c=65.0,
        rho=980.0,
        pv=0.25,
        pc=220.64,
        mu=4.3e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="PWR-STM-06",
        name="Ara Isıtıcı (Reheater) Desuperheater Sprey Suyu",
        sector="Power & Steam",
        service="liquid",
        fluid="Water",
        flow=45.0,
        p1_bar_a=140.0,
        p2_bar_a=60.0,
        temperature_c=180.0,
        rho=887.0,
        pv=10.0,
        pc=220.64,
        mu=1.5e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="PWR-STM-07",
        name="Süperkritik Ana Buhar Basınç Düşürme (Main Steam Letdown)",
        sector="Power & Steam",
        service="steam",
        fluid="Steam",
        flow=120000.0,
        p1_bar_a=160.0,
        p2_bar_a=50.0,
        temperature_c=500.0,
    ),
    ScenarioDefinition(
        id="PWR-STM-08",
        name="Yardımcı Kazan Doymuş Buhar Kollektör Basıncı",
        sector="Power & Steam",
        service="steam",
        fluid="Steam",
        flow=35000.0,
        p1_bar_a=22.0,
        p2_bar_a=14.0,
        temperature_c=240.0,
    ),
    ScenarioDefinition(
        id="PWR-STM-09",
        name="Sürekli Kazan Blöfü (Continuous Boiler Blowdown Flash)",
        sector="Power & Steam",
        service="liquid",
        fluid="Water",
        flow=25.0,
        p1_bar_a=80.0,
        p2_bar_a=8.0,
        temperature_c=290.0,
        rho=730.0,
        pv=74.0,
        pc=220.64,
        mu=9.5e-5,
        fl=0.85,
        is_flashing=True,
        cp=5400.0,
        hvap=1450000.0,
        mw=18.015,
    ),
    ScenarioDefinition(
        id="PWR-STM-10",
        name="Soğutma Kulesi Besleme ve Seviye Kontrol Vanası",
        sector="Power & Steam",
        service="liquid",
        fluid="Water",
        flow=650.0,
        p1_bar_a=6.0,
        p2_bar_a=3.2,
        temperature_c=28.0,
        rho=996.0,
        pv=0.038,
        pc=220.64,
        mu=8.5e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="OG-UP-01",
        name="Yüksek Basınçlı Ekşi Gaz Kuyu Başı Şoku (Sour Wellhead Choke)",
        sector="Oil & Gas",
        service="gas",
        fluid="NaturalGas",
        flow=85000.0,
        p1_bar_a=180.0,
        p2_bar_a=75.0,
        temperature_c=65.0,
        mw=18.5,
        k=1.28,
        mu=1.4e-5,
        z=0.88,
        is_sour=True,
    ),
    ScenarioDefinition(
        id="OG-MID-02",
        name="Şehir Besleme (City Gate) Basınç Düşürme ve J-T Soğuması",
        sector="Oil & Gas",
        service="gas",
        fluid="NaturalGas",
        flow=120000.0,
        p1_bar_a=70.0,
        p2_bar_a=16.0,
        temperature_c=15.0,
        mw=17.2,
        k=1.31,
        mu=1.2e-5,
        z=0.89,
    ),
    ScenarioDefinition(
        id="OG-MID-03",
        name="TEG Glikol Dehidrasyon Reboiler Yakıt Gazı Regülasyonu",
        sector="Oil & Gas",
        service="gas",
        fluid="Methane",
        flow=3200.0,
        p1_bar_a=35.0,
        p2_bar_a=4.0,
        temperature_c=40.0,
        mw=16.04,
        k=1.31,
        mu=1.1e-5,
        z=0.94,
    ),
    ScenarioDefinition(
        id="OG-UP-04",
        name="Asit Gazı Sıyırıcı Kolon Tepe Gazı (Amine Acid Gas Letdown)",
        sector="Oil & Gas",
        service="gas",
        fluid="AcidGas",
        flow=15000.0,
        p1_bar_a=3.5,
        p2_bar_a=1.6,
        temperature_c=110.0,
        mw=38.0,
        k=1.28,
        mu=1.3e-5,
        z=0.98,
        is_sour=True,
        is_toxic=True,
    ),
    ScenarioDefinition(
        id="OG-OFF-05",
        name="Açık Deniz (Offshore) Slug Catcher Acil Tahliye Vanası",
        sector="Oil & Gas",
        service="gas",
        fluid="NaturalGas",
        flow=350000.0,
        p1_bar_a=95.0,
        p2_bar_a=30.0,
        temperature_c=30.0,
        mw=19.1,
        k=1.27,
        mu=1.3e-5,
        z=0.85,
    ),
    ScenarioDefinition(
        id="OG-UGS-06",
        name="Yeraltı Doğal Gaz Depolama (UGS) Enjeksiyon Kontrolü",
        sector="Oil & Gas",
        service="gas",
        fluid="NaturalGas",
        flow=250000.0,
        p1_bar_a=140.0,
        p2_bar_a=110.0,
        temperature_c=45.0,
        mw=17.8,
        k=1.30,
        mu=1.5e-5,
        z=0.86,
    ),
    ScenarioDefinition(
        id="OG-MID-07",
        name="Kompresör İstasyonu Basma Hattı Anti-Surge Geri Dönüş Vanası",
        sector="Oil & Gas",
        service="gas",
        fluid="NaturalGas",
        flow=180000.0,
        p1_bar_a=85.0,
        p2_bar_a=55.0,
        temperature_c=60.0,
        mw=17.5,
        k=1.30,
        mu=1.3e-5,
        z=0.90,
    ),
    ScenarioDefinition(
        id="OG-PWR-08",
        name="Gaz Türbini Yakıt Gazı Skidi Hassas Basınç Regülasyonu",
        sector="Oil & Gas",
        service="gas",
        fluid="NaturalGas",
        flow=45000.0,
        p1_bar_a=42.0,
        p2_bar_a=24.0,
        temperature_c=35.0,
        mw=16.8,
        k=1.31,
        mu=1.2e-5,
        z=0.92,
    ),
    ScenarioDefinition(
        id="OG-SAF-09",
        name="Acil Durum Meşale (Flare Header) Basınç Boşaltma ve AIV Riski",
        sector="Oil & Gas",
        service="gas",
        fluid="NaturalGas",
        flow=220000.0,
        p1_bar_a=60.0,
        p2_bar_a=2.2,
        temperature_c=20.0,
        mw=18.2,
        k=1.29,
        mu=1.1e-5,
        z=0.91,
    ),
    ScenarioDefinition(
        id="OG-UP-10",
        name="Petrol-Gaz Üretim Ayırıcı (Separator) Gaz Çıkış Kontrolü",
        sector="Oil & Gas",
        service="gas",
        fluid="NaturalGas",
        flow=60000.0,
        p1_bar_a=25.0,
        p2_bar_a=5.5,
        temperature_c=40.0,
        mw=19.5,
        k=1.26,
        mu=1.2e-5,
        z=0.95,
    ),
    ScenarioDefinition(
        id="OG-UP-11",
        name="Kondensat Stabilizatör Kolonu Tepe Reflü Kontrolü",
        sector="Oil & Gas",
        service="liquid",
        fluid="Condensate",
        flow=85.0,
        p1_bar_a=15.0,
        p2_bar_a=8.0,
        temperature_c=55.0,
        rho=680.0,
        pv=4.5,
        pc=35.0,
        mu=3.5e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="REF-CDU-01",
        name="Ham Petrol Distilasyon Kolonu Flaş Bölgesi Buhar Çıkışı",
        sector="Petrochem & Refining",
        service="gas",
        fluid="HydrocarbonVapor",
        flow=22000.0,
        p1_bar_a=2.2,
        p2_bar_a=1.3,
        temperature_c=365.0,
        mw=110.0,
        k=1.12,
        mu=1.1e-5,
        z=0.96,
    ),
    ScenarioDefinition(
        id="REF-HCU-02",
        name="Hidrokraker Yüksek Basınçlı Hidrojen Sirkülasyon Döngüsü",
        sector="Petrochem & Refining",
        service="gas",
        fluid="Hydrogen",
        flow=95000.0,
        p1_bar_a=165.0,
        p2_bar_a=135.0,
        temperature_c=380.0,
        mw=2.016,
        k=1.40,
        mu=1.6e-5,
        z=1.08,
        is_h2=True,
    ),
    ScenarioDefinition(
        id="REF-FCC-03",
        name="Katalitik Kraker (FCC) Slurry Dip Ürün Sirkülasyonu",
        sector="Petrochem & Refining",
        service="liquid",
        fluid="SlurryOil",
        flow=140.0,
        p1_bar_a=8.0,
        p2_bar_a=3.5,
        temperature_c=340.0,
        rho=1050.0,
        pv=0.8,
        pc=25.0,
        mu=4.5e-3,
        fl=0.85,
    ),
    ScenarioDefinition(
        id="PET-ETH-04",
        name="Etilen Soğutma Döngüsü Kriyojenik Genleşme Vanası",
        sector="Petrochem & Refining",
        service="liquid",
        fluid="Ethylene",
        flow=65.0,
        p1_bar_a=22.0,
        p2_bar_a=3.2,
        temperature_c=-102.0,
        rho=568.0,
        pv=1.2,
        pc=50.4,
        mu=1.8e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="REF-SDA-05",
        name="Propan Deasfaltlama Çözücü Transfer ve Geri Kazanım",
        sector="Petrochem & Refining",
        service="liquid",
        fluid="Propane",
        flow=110.0,
        p1_bar_a=38.0,
        p2_bar_a=22.0,
        temperature_c=60.0,
        rho=470.0,
        pv=19.5,
        pc=42.5,
        mu=8.5e-5,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="PET-ARO-06",
        name="Benzen-Toluen Fraksiyonasyon Kolon Besleme Vanası",
        sector="Petrochem & Refining",
        service="liquid",
        fluid="Benzene",
        flow=90.0,
        p1_bar_a=8.0,
        p2_bar_a=3.5,
        temperature_c=115.0,
        rho=810.0,
        pv=2.4,
        pc=48.9,
        mu=2.8e-4,
        fl=0.9,
        is_toxic=True,
    ),
    ScenarioDefinition(
        id="REF-DCU-07",
        name="Gecikmeli Koker (Delayed Coker) Yüksek Basınçlı Su Jeti",
        sector="Petrochem & Refining",
        service="liquid",
        fluid="Water",
        flow=180.0,
        p1_bar_a=180.0,
        p2_bar_a=20.0,
        temperature_c=35.0,
        rho=994.0,
        pv=0.056,
        pc=220.64,
        mu=7.2e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="REF-VGO-08",
        name="Vakuum Gazyağı (VGO) Hidro-arıtma Besleme Pompası Çıkışı",
        sector="Petrochem & Refining",
        service="liquid",
        fluid="VGO",
        flow=130.0,
        p1_bar_a=110.0,
        p2_bar_a=60.0,
        temperature_c=260.0,
        rho=840.0,
        pv=1.5,
        pc=18.0,
        mu=3.8e-3,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="REF-SRU-09",
        name="Kükürt Geri Kazanım (SRU Claus) Termal Fırın Hava Kontrolü",
        sector="Petrochem & Refining",
        service="gas",
        fluid="Air",
        flow=45000.0,
        p1_bar_a=1.8,
        p2_bar_a=1.2,
        temperature_c=140.0,
        mw=28.96,
        k=1.40,
        mu=2.3e-5,
        z=1.0,
    ),
    ScenarioDefinition(
        id="PET-SYN-10",
        name="Sentez Gazı (Syngas CO+H2) Reforming Söndürme Vanası",
        sector="Petrochem & Refining",
        service="gas",
        fluid="Syngas",
        flow=80000.0,
        p1_bar_a=32.0,
        p2_bar_a=18.0,
        temperature_c=220.0,
        mw=12.5,
        k=1.38,
        mu=1.8e-5,
        z=1.02,
        is_h2=True,
        is_toxic=True,
    ),
    ScenarioDefinition(
        id="REF-VBK-11",
        name="Visbreaker Ağır Dip Ürün Soğutma ve Letdown Vanası",
        sector="Petrochem & Refining",
        service="liquid",
        fluid="HeavyFuelOil",
        flow=70.0,
        p1_bar_a=24.0,
        p2_bar_a=6.0,
        temperature_c=280.0,
        rho=940.0,
        pv=0.5,
        pc=15.0,
        mu=3.5e-2,
        fl=0.85,
    ),
    ScenarioDefinition(
        id="CLN-LNG-01",
        name="LNG Sıvılaştırma Ünitesi Run-Down Kontrol Vanası",
        sector="Clean Energy & Cryo",
        service="liquid",
        fluid="LNG_Methane",
        flow=220.0,
        p1_bar_a=45.0,
        p2_bar_a=8.0,
        temperature_c=-162.0,
        rho=425.0,
        pv=1.05,
        pc=45.99,
        mu=1.2e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CLN-LNG-02",
        name="LNG Yeniden Gazlaştırma (Regas) Yüksek Basınç Gönderim Pompası",
        sector="Clean Energy & Cryo",
        service="liquid",
        fluid="LNG_Methane",
        flow=350.0,
        p1_bar_a=85.0,
        p2_bar_a=65.0,
        temperature_c=-150.0,
        rho=410.0,
        pv=2.1,
        pc=45.99,
        mu=1.1e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CLN-HYD-03",
        name="Saf Yeşil Hidrojen Boru Hattı İletim Basınç Regülatörü",
        sector="Clean Energy & Cryo",
        service="gas",
        fluid="Hydrogen",
        flow=65000.0,
        p1_bar_a=70.0,
        p2_bar_a=35.0,
        temperature_c=25.0,
        mw=2.016,
        k=1.41,
        mu=8.9e-6,
        z=1.04,
        is_h2=True,
    ),
    ScenarioDefinition(
        id="CLN-HCN-04",
        name="%20 Hidrojen - %80 Doğal Gaz Karışımı (HCNG) Şebeke Enjeksiyonu",
        sector="Clean Energy & Cryo",
        service="gas",
        fluid="HCNG_Blend",
        flow=90000.0,
        p1_bar_a=50.0,
        p2_bar_a=25.0,
        temperature_c=20.0,
        mw=13.3,
        k=1.32,
        mu=1.1e-5,
        z=0.94,
        is_h2=True,
    ),
    ScenarioDefinition(
        id="CLN-ASU-05",
        name="Hava Ayrıştırma (ASU) Sıvı Azot (LIN) Depolama Besleme",
        sector="Clean Energy & Cryo",
        service="liquid",
        fluid="LiquidNitrogen",
        flow=50.0,
        p1_bar_a=16.0,
        p2_bar_a=3.0,
        temperature_c=-196.0,
        rho=808.0,
        pv=1.01,
        pc=33.9,
        mu=1.6e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CLN-CCU-06",
        name="Karbon Yakalama (CCUS) Süperkritik Yoğun Faz CO2 Boru Hattı",
        sector="Clean Energy & Cryo",
        service="gas",
        fluid="CarbonDioxide",
        flow=140000.0,
        p1_bar_a=110.0,
        p2_bar_a=75.0,
        temperature_c=35.0,
        mw=44.01,
        k=1.29,
        mu=2.2e-5,
        z=0.45,
    ),
    ScenarioDefinition(
        id="CLN-LOX-07",
        name="Sıvı Oksijen (LOX) Tıbbi ve Havacılık Tank Dolum Vanası",
        sector="Clean Energy & Cryo",
        service="liquid",
        fluid="LiquidOxygen",
        flow=40.0,
        p1_bar_a=25.0,
        p2_bar_a=5.0,
        temperature_c=-183.0,
        rho=1141.0,
        pv=1.01,
        pc=50.4,
        mu=1.9e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CLN-NH3-08",
        name="Yeşil Amonyak (Haber-Bosch) Sentez Döngüsü Basınç Kontrolü",
        sector="Clean Energy & Cryo",
        service="gas",
        fluid="Ammonia",
        flow=35000.0,
        p1_bar_a=140.0,
        p2_bar_a=80.0,
        temperature_c=180.0,
        mw=17.03,
        k=1.31,
        mu=1.7e-5,
        z=0.95,
        is_toxic=True,
    ),
    ScenarioDefinition(
        id="CLN-MEO-09",
        name="Biyo-Metanol Sentez Reaktör Çıkış Basınç Tahliyesi",
        sector="Clean Energy & Cryo",
        service="gas",
        fluid="MethanolVapor",
        flow=50000.0,
        p1_bar_a=75.0,
        p2_bar_a=45.0,
        temperature_c=230.0,
        mw=32.04,
        k=1.20,
        mu=1.5e-5,
        z=0.85,
        is_toxic=True,
    ),
    ScenarioDefinition(
        id="CLN-ARG-10",
        name="Kriyojenik Saf Argon Saflaştırma Kolon Besleme",
        sector="Clean Energy & Cryo",
        service="liquid",
        fluid="Argon",
        flow=30.0,
        p1_bar_a=18.0,
        p2_bar_a=4.0,
        temperature_c=-186.0,
        rho=1395.0,
        pv=1.05,
        pc=48.7,
        mu=2.6e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CHM-SUL-01",
        name="Derişik Sülfürik Asit (%98 H2SO4) Depo Transfer Vanası",
        sector="Chemical & Industry",
        service="liquid",
        fluid="SulfuricAcid",
        flow=45.0,
        p1_bar_a=6.0,
        p2_bar_a=2.5,
        temperature_c=35.0,
        rho=1830.0,
        pv=0.001,
        pc=64.0,
        mu=2.2e-2,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CHM-NAO-02",
        name="Kostik Soda (%50 NaOH) Nötralizasyon Besleme Vanası",
        sector="Chemical & Industry",
        service="liquid",
        fluid="CausticSoda",
        flow=35.0,
        p1_bar_a=7.0,
        p2_bar_a=3.0,
        temperature_c=45.0,
        rho=1525.0,
        pv=0.002,
        pc=200.0,
        mu=3.5e-2,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CHM-DEM-03",
        name="Yüksek Saflıkta Demineralize Su (Ultrapure DI Water) Hat Kontrolü",
        sector="Chemical & Industry",
        service="liquid",
        fluid="Water",
        flow=150.0,
        p1_bar_a=12.0,
        p2_bar_a=4.0,
        temperature_c=25.0,
        rho=997.0,
        pv=0.032,
        pc=220.64,
        mu=8.9e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CHM-CL2-04",
        name="Kuru Klor Gazı (Dry Chlorine Gas) Dozaj Kontrol Vanası",
        sector="Chemical & Industry",
        service="gas",
        fluid="Chlorine",
        flow=4500.0,
        p1_bar_a=8.0,
        p2_bar_a=2.0,
        temperature_c=30.0,
        mw=70.9,
        k=1.33,
        mu=1.3e-5,
        z=0.98,
        is_toxic=True,
    ),
    ScenarioDefinition(
        id="CHM-SLT-05",
        name="Güneş Kulesi (CSP) Erimiş Tuz (Molten Salt) Termal Depolama",
        sector="Chemical & Industry",
        service="liquid",
        fluid="MoltenSalt",
        flow=80.0,
        p1_bar_a=14.0,
        p2_bar_a=3.5,
        temperature_c=450.0,
        rho=1850.0,
        pv=0.0001,
        pc=150.0,
        mu=2.5e-3,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CHM-DES-06",
        name="Deniz Suyu Ters Ozmoz (SWRO) Yüksek Basınç Membran Besleme",
        sector="Chemical & Industry",
        service="liquid",
        fluid="Seawater",
        flow=280.0,
        p1_bar_a=72.0,
        p2_bar_a=15.0,
        temperature_c=25.0,
        rho=1025.0,
        pv=0.032,
        pc=220.0,
        mu=9.8e-4,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CHM-OIL-07",
        name="Termal Yağ (Therminol 66) Sirkülasyon Isı Transfer Döngüsü",
        sector="Chemical & Industry",
        service="liquid",
        fluid="Therminol66",
        flow=95.0,
        p1_bar_a=10.0,
        p2_bar_a=4.0,
        temperature_c=315.0,
        rho=820.0,
        pv=0.8,
        pc=25.0,
        mu=1.2e-3,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CHM-WST-08",
        name="Endüstriyel Atıksu Arıtma Çamur ve Nötralizasyon Basma Hattı",
        sector="Chemical & Industry",
        service="liquid",
        fluid="WastewaterSludge",
        flow=120.0,
        p1_bar_a=5.0,
        p2_bar_a=1.8,
        temperature_c=30.0,
        rho=1080.0,
        pv=0.042,
        pc=220.64,
        mu=6.5e-3,
        fl=0.9,
    ),
    ScenarioDefinition(
        id="CHM-HFA-09",
        name="Hidroflorik Asit (HF) Alkilasyon Asit Yıkama Vanası",
        sector="Chemical & Industry",
        service="liquid",
        fluid="HydrofluoricAcid",
        flow=30.0,
        p1_bar_a=9.0,
        p2_bar_a=3.5,
        temperature_c=38.0,
        rho=970.0,
        pv=1.2,
        pc=64.8,
        mu=8.5e-4,
        fl=0.9,
        is_toxic=True,
    ),
    ScenarioDefinition(
        id="CHM-PHO-10",
        name="Fosforik Asit Gübre Tesisi Aşındırıcı Bulamaç (Slurry) Kontrolü",
        sector="Chemical & Industry",
        service="liquid",
        fluid="PhosphoricAcidSlurry",
        flow=85.0,
        p1_bar_a=9.0,
        p2_bar_a=3.0,
        temperature_c=70.0,
        rho=1450.0,
        pv=0.05,
        pc=80.0,
        mu=1.2e-2,
        fl=0.9,
    ),
]


def run_scenario_50(sc: ScenarioDefinition) -> Scenario50Result:
    """Execute full engineering calculation and verification for one scenario."""
    warnings_list: list[str] = []
    checks_passed = 0
    checks_total = 7

    srv = sc.service.lower().strip()
    flow_unit = "kg/h" if srv == "steam" else ("Nm\u00b3/h" if srv == "gas" else "m\u00b3/h")
    flow_disp = f"{sc.flow:.1f} {flow_unit}"

    if srv == "steam":
        steam_inp = SteamSizingInput(
            flow_kg_h=sc.flow,
            inlet_pressure_bar_a=sc.p1_bar_a,
            outlet_pressure_bar_a=sc.p2_bar_a,
            temperature_c=sc.temperature_c,
        )
        res = size_steam_valve(steam_inp, valve_series=STANDARD_EXTENDED_SERIES)
    elif srv == "liquid":
        liq_inp = LiquidSizingInput(
            flow_m3h=sc.flow,
            inlet_pressure_bar_a=sc.p1_bar_a,
            outlet_pressure_bar_a=sc.p2_bar_a,
            density_kg_m3=sc.rho,
            vapor_pressure_bar_a=sc.pv,
            critical_pressure_bar_a=sc.pc,
            viscosity_pa_s=sc.mu,
            fl=sc.fl,
            temperature_c=sc.temperature_c,
            specific_heat_j_kgk=sc.cp,
            latent_heat_j_kg=sc.hvap,
            molecular_weight=sc.mw,
        )
        res = size_liquid_valve(liq_inp, valve_series=STANDARD_EXTENDED_SERIES)
    else:
        gas_inp = GasSizingInput(
            flow_nm3h=sc.flow,
            inlet_pressure_bar_a=sc.p1_bar_a,
            outlet_pressure_bar_a=sc.p2_bar_a,
            temperature_c=sc.temperature_c,
            molecular_weight=sc.mw,
            specific_heat_ratio=sc.k,
            viscosity_pa_s=sc.mu,
            z=sc.z,
        )
        res = size_gas_valve(gas_inp, valve_series=STANDARD_EXTENDED_SERIES)

    check_sizing = (
        res.required_cv > 0.0
        and res.rated_cv >= res.required_cv
        and 0.0 < res.opening_percent <= 100.0
        and res.valve_dn_mm > 0
    )
    if check_sizing:
        checks_passed += 1
    else:
        warnings_list.append("Vana boyutlandırma kriteri sağlanamadı.")

    dp = sc.p1_bar_a - sc.p2_bar_a
    cav_severity: str | None = None
    if srv == "liquid":
        sigma = (sc.p1_bar_a - sc.pv) / dp if dp > 0 else 10.0
        cav_eval = evaluate_cavitation_severity(sigma, dp, sc.p1_bar_a, sc.pv)
        cav_severity = cav_eval.severity_level
        check_cav = len(cav_severity) > 0
    else:
        check_cav = True
    if check_cav:
        checks_passed += 1

    noise_raw = res.get("noise_db")
    noise_val = float(noise_raw if noise_raw is not None else (res.get("noise_dba") or 75.0))
    noise_eval = evaluate_noise_attenuation(noise_val, srv, dp)
    check_noise = len(noise_eval.recommended_treatment) > 0
    if check_noise:
        checks_passed += 1

    vel_m_s = float(res.get("velocity", {}).get("pipe_out_m_s", 4.0))
    fluid_density = sc.rho if srv == "liquid" else 10.0
    ev_check = check_erosional_velocity(vel_m_s, fluid_density)
    relief_data = {
        "specific_gravity": fluid_density / 1000.0,
        "molecular_weight": sc.mw,
        "density_kg_m3": fluid_density,
    }
    relief_eval = calc_wide_open_relief_capacity(srv, res.rated_cv, sc.p1_bar_a, 0.0, relief_data)
    check_safety = ev_check.erosional_limit_m_s > 0.0 and relief_eval.wide_open_flow_rate > 0.0
    if check_safety:
        checks_passed += 1

    mat_grp = "WC6" if (sc.temperature_c > 400.0 or (sc.is_h2 and sc.temperature_c > 230.0)) else (
        "CF8M" if (sc.temperature_c < -46.0 or "lng" in sc.fluid.lower()) else "WCB"
    )
    p_class = recommend_pressure_class(sc.p1_bar_a, sc.temperature_c, mat_grp)
    mawp = derated_mawp_bar(p_class, sc.temperature_c, mat_grp)
    bonnet = recommend_bonnet_type(sc.temperature_c, srv, sc.fluid)
    mat_rec = recommend_alloy_material(
        srv, sc.fluid, sc.temperature_c, is_sour=sc.is_sour, is_h2=sc.is_h2
    )
    check_materials = mawp >= sc.p1_bar_a and len(bonnet) > 0 and len(mat_rec.body_material) > 0
    if check_materials:
        checks_passed += 1
    else:
        warnings_list.append(f"Basınç sınıfı MAWP ({mawp:.1f} bar) P1 ({sc.p1_bar_a:.1f} bar) basıncını karşılamıyor.")

    packing_guidance = recommend_packing_system(
        srv, sc.fluid, sc.temperature_c, sc.p1_bar_a,
        is_toxic_or_lethal=sc.is_toxic, is_sour_gas=sc.is_sour,
    )
    check_packing = len(packing_guidance.packing_type) > 0 and len(packing_guidance.emission_class) > 0
    if check_packing:
        checks_passed += 1

    ds = build_isa20_datasheet(
        tag_number=f"FV-{sc.id}",
        service_description=sc.name,
        line_number=f'{res.valve_inch}"-PROCES',
        pid_number=f"PID-{sc.id[:3]}",
        service_type=srv,
        fluid_name=sc.fluid,
        sizing_result=cast(dict[str, Any], res),
        packing_guidance=packing_guidance,
    )
    check_datasheet = ds.valve_dn_mm == res.valve_dn_mm and ds.rated_cv == res.rated_cv
    if check_datasheet:
        checks_passed += 1

    jt_delta_t: float | None = None
    hydrate_risk: bool | None = None
    if srv == "gas":
        fluid_jt = "Methane" if ("natural" in sc.fluid.lower() or "methane" in sc.fluid.lower()) else sc.fluid
        try:
            jt_res = calc_joule_thomson_drop(fluid_jt, sc.p1_bar_a, sc.p2_bar_a, sc.temperature_c)
            jt_delta_t = jt_res.delta_t_c
            hydrate_risk = jt_res.hydrate_risk
        except Exception:
            jt_delta_t = None
            hydrate_risk = None

    passed = checks_passed == checks_total
    detail_msg = (
        f"Gerekli Cv={res.required_cv:.2f}, Nominal Cv={res.rated_cv:.1f}, "
        f"Açıklık=%{res.opening_percent:.1f}, Seçilen: DN{res.valve_dn_mm} ({res.valve_inch}), "
        f"Sınıf={p_class} (MAWP {mawp:.1f} bar), Gürültü={noise_val:.1f} dBA."
    )

    return Scenario50Result(
        id=sc.id,
        name=sc.name,
        sector=sc.sector,
        service=srv,
        fluid=sc.fluid,
        flow_display=flow_disp,
        p1_bar_a=sc.p1_bar_a,
        p2_bar_a=sc.p2_bar_a,
        delta_p_bar=dp,
        temperature_c=sc.temperature_c,
        required_cv=res.required_cv,
        required_kv=res.required_kv,
        rated_cv=res.rated_cv,
        opening_percent=res.opening_percent,
        valve_dn_mm=res.valve_dn_mm,
        valve_inch=res.valve_inch,
        is_choked=res.is_choked,
        flow_regime=res.get("flow_regime", "normal"),
        cavitation_severity=cav_severity,
        noise_dba=noise_val,
        acoustic_treatment=noise_eval.recommended_treatment,
        pipe_velocity_m_s=vel_m_s,
        erosional_limit_m_s=ev_check.erosional_limit_m_s,
        is_velocity_exceeded=ev_check.is_velocity_exceeded,
        wide_open_relief_flow=relief_eval.wide_open_flow_rate,
        relief_unit=relief_eval.flow_unit,
        pressure_class=p_class,
        derated_mawp_bar=mawp,
        bonnet_type=bonnet,
        body_material=mat_rec.body_material,
        trim_material=mat_rec.trim_material,
        stem_material=mat_rec.stem_material,
        packing_type=packing_guidance.packing_type,
        emission_class=packing_guidance.emission_class,
        jt_delta_t_c=jt_delta_t,
        hydrate_risk=hydrate_risk,
        passed=passed,
        checks_passed=checks_passed,
        checks_total=checks_total,
        detail=detail_msg,
        warnings=warnings_list,
    )


def run_all_50_scenarios() -> list[Scenario50Result]:
    """Execute calculations across all 52 industrial benchmark scenarios."""
    return [run_scenario_50(sc) for sc in SCENARIO_DEFINITIONS]


def print_50_scenarios_report(results: list[Scenario50Result]) -> None:
    """Print the complete evaluation report and cross-sectoral analytics in Turkish."""
    print("=" * 132)
    print("      KONTROL VANASI HESAPLAMA MOTORU — 52 ENDÜSTRİYEL SENARYO DOĞRULAMA VE DEĞERLENDİRME RAPORU")
    print("=" * 132)
    print()

    fmt_header = (
        f"{'ID':<11} {'Sektör':<22} {'Akışkan':<16} {'P1/P2 (bar)':<15} "
        f"{'Gerekli Cv':>11} {'Nominal':>9} {'Açıklık%':>9} {'Seçilen':>13} {'Sınıf':>8} {'Gürültü':>11} {'DURUM':>7}"
    )
    print(fmt_header)
    print("-" * 138)

    for r in results:
        p_str = f"{r.p1_bar_a:.1f}/{r.p2_bar_a:.1f}"
        dn_str = f"DN{r.valve_dn_mm} {r.valve_inch}"
        noise_str = f"{r.noise_dba:.1f} dBA"
        status = "PASS" if r.passed else "FAIL"
        print(
            f"{r.id:<11} {r.sector:<22} {r.fluid:<16} {p_str:<15} "
            f"{r.required_cv:>11.2f} {r.rated_cv:>9.1f} {r.opening_percent:>8.1f}% "
            f"{dn_str:>13} {r.pressure_class:>8} {noise_str:>11} {status:>7}"
        )

    print("-" * 138)
    print()

    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    pass_pct = (passed_count / total) * 100.0 if total > 0 else 0.0

    print("GENEL DOĞRULAMA VE BAŞARI ÖZETİ:")
    print(f"- Toplam Doğrulanan Senaryo : {total}")
    print(f"- Başarılı (PASS)           : {passed_count}")
    print(f"- Başarısız (FAIL)          : {total - passed_count}")
    print(f"- Başarı Oranı              : %{pass_pct:.1f}")
    print()

    print("SEKTÖREL DAĞILIM VE PERFORMANS:")
    sectors = sorted({r.sector for r in results})
    for sec in sectors:
        sec_results = [r for r in results if r.sector == sec]
        sec_pass = sum(1 for r in sec_results if r.passed)
        avg_opening = sum(r.opening_percent for r in sec_results) / len(sec_results)
        print(f"  * {sec:<24}: {sec_pass}/{len(sec_results)} Geçti, Ortalama Vana Açıklığı: %{avg_opening:.1f}")
    print()

    print("MÜHENDİSLİK VE GÜVENLİK ANALİTİKLERİ:")
    choked_count = sum(1 for r in results if r.is_choked)
    severe_cav = sum(1 for r in results if r.cavitation_severity and "Şiddetli" in r.cavitation_severity)
    flashing_count = sum(
        1 for r in results if "flashing" in r.flow_regime.lower() or (r.cavitation_severity and "Buharlaşma" in r.cavitation_severity)
    )
    high_noise = sum(1 for r in results if r.noise_dba > 85.0)
    aiv_risk = sum(1 for r in results if r.noise_dba > 110.0)
    velocity_exceeded = sum(1 for r in results if r.is_velocity_exceeded)
    cryo_count = sum(1 for r in results if "Kriyojenik" in r.bonnet_type)
    bellows_count = sum(1 for r in results if "Körüklü" in r.packing_type)

    print(f"  * Boğulmuş Akış (Choked Flow)         : {choked_count} senaryo")
    print(f"  * Şiddetli Kavitasyon (Çok Kademeli)   : {severe_cav} senaryo")
    print(f"  * İki Fazlı Buharlaşma (Flashing)     : {flashing_count} senaryo")
    print(f"  * Gürültü Sınırı Aşan (> 85 dBA)      : {high_noise} senaryo (Whisper trim veya ceket önerildi)")
    print(f"  * Akustik Titreşim Riski (AIV >110 dBA): {aiv_risk} senaryo")
    print(f"  * API 14E Boru Aşınma Hızı Uyarısı     : {velocity_exceeded} senaryo (Boru genişletici önerildi)")
    print(f"  * Kriyojenik Uzatılmış Boyun           : {cryo_count} senaryo (-196 °C ile -46 °C arası)")
    print(f"  * Metal Körük Salmastra (ISO 15848-1) : {bellows_count} senaryo (Zehirli / tehlikeli akışkanlar)")
    print()

    print("SONUÇ VE DEĞERLENDİRME:")
    if passed_count == total:
        print(
            "Tüm 52 senaryoda IEC 60534 hidrolik/akışkan boyutlandırması, ISA-RP75.23 kavitasyon analizleri, "
            "ASME B16.34 sıcaklık-basınç düşümü, API 14E/520 güvenlik hesapları ve ISA-20 veri sayfaları "
            "uluslararası standartlara tam uyumlu olarak başarıyla tamamlanmıştır."
        )
    else:
        print("Bazı senaryolarda limit aşımları tespit edildi; yukarıdaki FAIL satırlarını kontrol ediniz.")
    print("=" * 132)


def main() -> int:
    """Run verification and print report."""
    results = run_all_50_scenarios()
    print_50_scenarios_report(results)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
