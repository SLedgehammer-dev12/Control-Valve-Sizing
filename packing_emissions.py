"""Valve stem packing and fugitive emissions selection engine.

Provides engineering guidance on packing systems per ISO 15848-1,
API 641, TA-Luft (VDI 2440), and NACE MR0175 / ISO 15156.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PackingGuidance:
    """Stem packing specification and fugitive emissions assessment."""

    packing_type: str
    emission_class: str
    temperature_range_c: tuple[float, float]
    fire_safe: bool
    nace_mr0175_compliant: bool
    leakage_tightness_ppmv: float
    description: str
    recommendations: list[str] = field(default_factory=list)


def recommend_packing_system(
    service: str,
    fluid_name: str,
    temperature_c: float,
    pressure_bar_a: float,
    is_toxic_or_lethal: bool = False,
    is_sour_gas: bool = False,
) -> PackingGuidance:
    """Recommend control valve packing system based on temperature, media toxicity, and fugitive emission standards."""
    fluid_lower = fluid_name.lower().strip()
    is_sour = is_sour_gas or any(k in fluid_lower for k in ("h2s", "sour", "acid", "kükürt", "kukurt"))
    is_toxic = is_toxic_or_lethal or any(
        k in fluid_lower for k in ("chlorine", "klor", "benzene", "benzen", "phosgene", "fosgen", "ammonia", "amonyak", "co", "karbonmonoksit")
    )

    recs: list[str] = []

    if is_toxic:
        packing_type = "Metal Körüklü Salmastra (Bellows Seal) + Yedek Canlı Yüklemeli Grafit"
        emission_class = "ISO 15848-1 Class AH / TA-Luft (< 50 ppmv, Sıfır Kaçak)"
        temp_range = (-196.0, 400.0)
        fire_safe = True
        leak_ppmv = 10.0
        desc = (
            "Zehirli, kanserojen veya tehlikeli gaz servisi: Atmosfere sıfır emisyon sağlamak üzere "
            "metal körük (bellows seal) ve körük yırtılmasına karşı yedek emniyet salmastrası seçildi."
        )
        recs.append("Körük ile yedek salmastra arasına kaçak izleme bağlantısı (sniff/sensor port) eklenmelidir.")
    elif temperature_c > 220.0 or service == "steam" or "oil" in fluid_lower or "yağ" in fluid_lower or "yag" in fluid_lower:
        packing_type = "Kalıplanmış Saf Grafit Halkalar (Die-Formed Flexible Graphite) + Karbon Anti-Ekstrüzyon"
        emission_class = "ISO 15848-1 Class BH / API 641 / TA-Luft (< 100 ppmv)"
        temp_range = (-50.0, 550.0)
        fire_safe = True
        leak_ppmv = 50.0
        desc = (
            "Yüksek sıcaklık ve yangın güvenli (Fire-Safe API 607) servis: "
            "Termal genleşme ve yüksek sıcaklık bozunmasına dirençli yüksek saflıkta kalıplanmış grafit."
        )
        recs.append("Termal döngülerde salmastra gevşemesini önlemek için disk yaylı canlı yükleme (live loading) zorunludur.")
    else:
        packing_type = "Canlı Yüklemeli Yay Destekli PTFE V-Halka Salmastra (Live-Loaded PTFE Chevron)"
        emission_class = "ISO 15848-1 Class BH / API 641 (< 100 ppmv)"
        temp_range = (-40.0, 220.0)
        fire_safe = False
        leak_ppmv = 25.0
        desc = (
            "Standart ve düşük emisyonlu proses servisi: Çok düşük mil sürtünmesi, yüksek kontrol hassasiyeti, "
            "histerezissiz çalışma ve 100.000+ çevrim mükemmel kaçak emisyon sızdırmazlığı."
        )
        recs.append("PTFE düşük sürtünmesi sayesinde aktüatör tepki süresini ve ölü bölgeyi (deadband) minimize eder.")

    if is_sour:
        recs.append(
            "Ek\u015fi gaz (Sour Gas) servisi: Vana mili, g\u00f6vdesi ve c\u0131vatalar\u0131 NACE MR0175 / ISO 15156 "
            "uyar\u0131nca sertlik <= 22 HRC (Inconel 718 veya \u00f6zel \u0131s\u0131l i\u015flemli 316SS) olmal\u0131d\u0131r."
        )

    if pressure_bar_a > 100.0:
        recs.append(
            f"Y\u00fcksek bas\u0131n\u00e7 ({pressure_bar_a:.1f} bar): Salmastra bo\u011faz\u0131nda ekstr\u00fczyon \u00f6nleyici "
            "sert karbon/metal halkalar (anti-extrusion rings) kullan\u0131lmal\u0131d\u0131r."
        )

    return PackingGuidance(
        packing_type=packing_type,
        emission_class=emission_class,
        temperature_range_c=temp_range,
        fire_safe=fire_safe,
        nace_mr0175_compliant=is_sour,
        leakage_tightness_ppmv=leak_ppmv,
        description=desc,
        recommendations=recs,
    )
