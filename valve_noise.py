"""Control valve noise prediction — IEC 60534-8-4:2015 (liquid) and IEC 60534-8-3:2011 (gas/steam).

Wraps fluids.control_valve.control_valve_noise_l_2015 and
fluids.control_valve.control_valve_noise_g_2011 for the project's
SizingResult + input dataclass interface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fluids.control_valve import control_valve_noise_g_2011, control_valve_noise_l_2015

logger = logging.getLogger(__name__)


def predict_noise_liquid(
    flow_kg_s: float,
    inlet_pressure_pa: float,
    outlet_pressure_pa: float,
    vapor_pressure_pa: float | None,
    density_kg_m3: float,
    speed_of_sound_m_s: float | None,
    kv: float,
    valve_diameter_m: float,
    pipe_diameter_m: float,
    fl: float,
    fd: float,
    pipe_wall_thickness_m: float = 0.006,
    xfz: float | None = None,
) -> float:
    """Predict liquid valve noise per IEC 60534-8-4:2015.

    Parameters
    ----------
    flow_kg_s : Mass flow rate [kg/s]
    inlet_pressure_pa : Inlet pressure [Pa]
    outlet_pressure_pa : Outlet pressure [Pa]
    vapor_pressure_pa : Saturation (vapor) pressure at inlet temperature [Pa].
        Set to 0.0 if unknown (non-flashing service).
    density_kg_m3 : Liquid density [kg/m3]
    speed_of_sound_m_s : Speed of sound in liquid [m/s].
        If None, uses 1400 m/s as typical for water.
    kv : Valve flow coefficient Kv [m3/h]
    valve_diameter_m : Valve diameter [m]
    pipe_diameter_m : Pipe internal diameter [m]
    fl : Liquid pressure recovery factor [-]
    fd : Valve style modifier [-]
    pipe_wall_thickness_m : Pipe wall thickness [m] (default 6 mm)
    xfz : Cavitation factor (optional, per IEC)

    Returns
    -------
    Sound pressure level [dB(A)] at 1 m downstream.
    """
    pv = vapor_pressure_pa if vapor_pressure_pa is not None else 0.0
    c = speed_of_sound_m_s if speed_of_sound_m_s is not None else 1400.0

    return control_valve_noise_l_2015(
        m=flow_kg_s,  # type: ignore[arg-type]
        P1=inlet_pressure_pa,
        P2=outlet_pressure_pa,
        Psat=pv,
        rho=density_kg_m3,
        c=c,
        Kv=kv,
        d=valve_diameter_m,
        Di=pipe_diameter_m,
        FL=fl,
        Fd=fd,
        t_pipe=pipe_wall_thickness_m,
        xFz=xfz,
    )


def predict_noise_gas(
    flow_kg_s: float,
    inlet_pressure_pa: float,
    outlet_pressure_pa: float,
    inlet_temperature_k: float,
    density_kg_m3: float,
    specific_heat_ratio: float,
    molecular_weight: float,
    kv: float,
    valve_diameter_m: float,
    pipe_diameter_m: float,
    fd: float,
    fl: float,
    pipe_wall_thickness_m: float = 0.006,
    flp: float | None = None,
    fp: float | None = None,
) -> float:
    """Predict gas/steam valve noise per IEC 60534-8-3:2011.

    Parameters
    ----------
    flow_kg_s : Mass flow rate [kg/s]
    inlet_pressure_pa : Inlet pressure [Pa]
    outlet_pressure_pa : Outlet pressure [Pa]
    inlet_temperature_k : Inlet temperature [K]
    density_kg_m3 : Gas density at inlet [kg/m3]
    specific_heat_ratio : Cp/Cv [-]
    molecular_weight : Molecular weight [g/mol]
    kv : Valve flow coefficient Kv [m3/h]
    valve_diameter_m : Valve diameter [m]
    pipe_diameter_m : Pipe internal diameter [m]
    fd : Valve style modifier [-]
    fl : Liquid pressure recovery factor [-]
    pipe_wall_thickness_m : Pipe wall thickness [m] (default 6 mm)
    flp : FL with piping factors (optional)
    fp : Piping geometry factor (optional)

    Returns
    -------
    Sound pressure level [dB(A)] at 1 m downstream.
    """
    return control_valve_noise_g_2011(
        m=flow_kg_s,
        P1=inlet_pressure_pa,
        P2=outlet_pressure_pa,
        T1=inlet_temperature_k,
        rho=density_kg_m3,
        gamma=specific_heat_ratio,
        MW=molecular_weight,
        Kv=kv,
        d=valve_diameter_m,
        Di=pipe_diameter_m,
        t_pipe=pipe_wall_thickness_m,
        Fd=fd,
        FL=fl,
        FLP=flp,
        FP=fp,
    )


@dataclass(frozen=True)
class NoiseAttenuationOption:
    """Acoustic attenuation evaluation per IEC 60534-8-3 and OSHA limits."""

    predicted_noise_dba: float
    whisper_trim_dba: float
    diffuser_plate_dba: float
    acoustic_insulation_dba: float
    whisper_plus_insulation_dba: float
    is_attenuation_required: bool
    recommended_treatment: str
    engineering_notes: list[str] = field(default_factory=list)


def evaluate_noise_attenuation(
    noise_dba: float,
    service: str = "gas",
    delta_p_bar: float = 1.0,
) -> NoiseAttenuationOption:
    """Evaluate acoustic treatment options when control valve noise exceeds 85 dBA."""
    n = max(float(noise_dba), 0.0)
    required = n > 85.0
    whisper = max(n - 18.0, 45.0)
    diffuser = max(n - 14.0, 45.0)
    insulation = max(n - 10.0, 45.0)
    combo = max(n - 26.0, 45.0)

    notes: list[str] = []

    if not required:
        treatment = "Akustik İyileştirme Gerekmez (<= 85 dBA güvenli limit)"
        notes.append(f"Tahmin edilen gürültü ({n:.1f} dBA) OSHA/ISO 85 dBA sınırının altındadır.")
    elif n <= 100.0:
        treatment = "Düşük Gürültülü Kafes (Whisper Trim / Drilled Cage)"
        notes.append(f"Gürültü ({n:.1f} dBA) 85 dBA iş sağlığı sınırını aşıyor.")
        notes.append("Delikli kafes (Whisper Trim) ile ses basınç seviyesi ~18 dBA düşürülerek güvenli sınıra çekilebilir.")
        notes.append("Alternatif olarak boru hattına 50 mm mineral yün akustik izolasyon ceketi (-10 dBA) uygulanabilir.")
    elif n <= 110.0:
        treatment = "Kombine İyileştirme: Whisper Trim + Boru Akustik İzolasyonu"
        notes.append(f"Yüksek aerodinamik gürültü ({n:.1f} dBA): Tek başına kafes veya ceket yeterli olmayabilir.")
        notes.append("Whisper Trim ve akustik ceket birlikte uygulanarak ses seviyesi 85 dBA altına indirilebilir.")
        notes.append("Boru çıkışına difüzör (baffle plate / susturucu orifis) eklenmesi basınç düşüşünü kademelendirir.")
    else:
        treatment = "Kritik Akustik Tehlike: Çok Kademeli Labirent Trim + Hat Susturucusu"
        notes.append(f"Aşırı gürültü ({n:.1f} dBA > 110 dBA): Akustik Uyarılmış Titreşim (AIV) riski mevcuttur!")
        notes.append("Energy Institute standartlarına göre boru kaynaklarında yorulma ve yırtılma riski bulunur.")
        notes.append("Basınç düşüşü çok kademeli tortuous-path disk-stack trim ve downstream susturucu ile paylaşılmalıdır.")

    if service.lower() == "liquid" and required:
        notes.append("Sıvı servisinde yüksek ses genelde kavitasyondan kaynaklanır; anti-kavitasyon kafesi önceliklidir.")
    if delta_p_bar > 20.0 and required:
        notes.append(f"Yüksek basınç farkı ({delta_p_bar:.1f} bar): Kademeli basınç düşürücü orifis plakaları önerilir.")

    return NoiseAttenuationOption(
        predicted_noise_dba=n,
        whisper_trim_dba=whisper,
        diffuser_plate_dba=diffuser,
        acoustic_insulation_dba=insulation,
        whisper_plus_insulation_dba=combo,
        is_attenuation_required=required,
        recommended_treatment=treatment,
        engineering_notes=notes,
    )
