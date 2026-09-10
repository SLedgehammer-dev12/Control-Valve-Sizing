"""Rule-based trim selection and severe service cavitation guidance for control valves.

Provides engineering guidance on trim style (anti-cavitation, low-noise,
anti-flash, multi-stage) aligned with ISA-RP75.23 and IEC 60534-8-2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CavitationAnalysis:
    """Detailed liquid cavitation severity and multi-stage trim evaluation."""

    sigma: float
    severity_level: str
    stages_recommended: int
    trim_recommendation: str
    max_allowable_dp_per_stage_bar: float
    warnings: list[str]
    engineering_notes: list[str]


def evaluate_cavitation_severity(
    sigma: float,
    delta_p_bar: float,
    p1_bar_a: float,
    pv_bar_a: float,
) -> CavitationAnalysis:
    """Evaluate liquid cavitation severity and determine required trim stages per ISA-RP75.23."""
    dp = max(float(delta_p_bar), 0.001)
    p1 = max(float(p1_bar_a), 0.001)
    pv = max(float(pv_bar_a), 0.0)

    warnings: list[str] = []
    notes: list[str] = []

    if p1 <= pv:
        severity = "Buharlaşma (Flashing)"
        stages = 1
        trim = "Anti-Flash genişleme gövdesi (Angle Body) + Stellite kaplama"
        max_dp_stage = dp
        warnings.append("Akışkan girişte kaynıyor (P1 <= Pv). Kavitasyon değil iki fazlı flashing rejimindedir.")
        notes.append("Yüksek hızlı sıvı damlacık erozyonuna karşı gövde genişletilmeli ve sertleştirilmiş yüzey seçilmelidir.")
    elif sigma > 2.0:
        severity = "Güvenli (Kavitasyonsuz)"
        stages = 1
        trim = "Standart Trim"
        max_dp_stage = dp
        notes.append("Kavitasyon indeksi sigma > 2.0: Kavitasyon hasarı veya gürültü riski bulunmamaktadır.")
    elif sigma > 1.5:
        severity = "Başlangıç Kavitasyonu (Incipient Cavitation)"
        stages = 1
        trim = "Sertleştirilmiş Trim (Stellite 6 / CoCr veya 410SS)"
        max_dp_stage = (p1 - pv) / 1.5
        warnings.append("Düşük düzeyde kavitasyon başlangıcı tespit edildi. Uzun dönemli sit aşınması mümkündür.")
        notes.append("Tek kademeli sertleştirilmiş trim (Stellite sit/klape) yüzey ömrünü korur.")
    elif sigma > 1.1:
        severity = "Yoğun Kavitasyon (Constant Cavitation)"
        stages = 2
        trim = "2-Kademeli Anti-Kavitasyon Kafesi (Cavitrol II / Q-Trim benzeri)"
        max_dp_stage = dp / 2.0
        warnings.append("Yoğun kavitasyon: Standart trim hızlıca tahrip olur; yüksek titreşim ve gürültü beklenir.")
        notes.append("Toplam basınç düşümü 2 kademeye bölünerek basıncın buharlaşma basıncının altına inmesi engellenir.")
    else:
        severity = "Şiddetli / Boğulmuş Kavitasyon (Choking Cavitation)"
        calc_stages = max(3, min(6, math.ceil(dp / 15.0)))
        stages = calc_stages
        trim = f"{stages}-Kademeli Labirent / Çok Yollu Disk-Stack Trim (Cavitrol III / Tortuous Path)"
        max_dp_stage = dp / stages
        warnings.append("Şiddetli kavitasyon ve boğulma: Akış maksimum kapasitededir. Acil ağır hizmet trimi zorunludur.")
        notes.append(
            f"Basınç düşümü {stages} ayrı direnç kademesinde dağıtılarak kavitasyon enerjisi akışkan içinde sönümlendirilir."
        )

    return CavitationAnalysis(
        sigma=sigma,
        severity_level=severity,
        stages_recommended=stages,
        trim_recommendation=trim,
        max_allowable_dp_per_stage_bar=max_dp_stage,
        warnings=warnings,
        engineering_notes=notes,
    )


def recommend_trim(
    service: str,
    flow_regime: str = "",
    is_choked: bool = False,
    noise_db: float | None = None,
    opening_percent: float = 50.0,
    cavitation_index: float | None = None,
    pressure_drop_ratio_x: float = 0.0,
    temperature_c: float = 25.0,
    delta_p_bar: float = 1.0,
    p1_bar_a: float = 5.0,
    pv_bar_a: float = 0.023,
) -> list[str]:
    """Return a list of trim recommendations based on operating conditions."""
    recs: list[str] = []

    if service == "liquid" and cavitation_index is not None:
        analysis = evaluate_cavitation_severity(cavitation_index, delta_p_bar, p1_bar_a, pv_bar_a)
        if analysis.stages_recommended > 1 or analysis.severity_level != "Güvenli (Kavitasyonsuz)":
            recs.append(f"Kavitasyon: {analysis.severity_level} -> {analysis.trim_recommendation}.")
    elif service == "liquid" and flow_regime == "flashing":
        recs.append(
            "Anti-flash trim: genlesme hacimli govde (angle body tercih edilebilir) ve "
            "sertlestirilmis trim (or. Stellite 6 kaplama) onerilir."
        )
    elif service == "liquid" and flow_regime == "choked-cavitating":
        recs.append(
            "Anti-kavitasyon trimi (cok kademeli, or. Cavitrol III benzeri) veya daha yuksek FL'li "
            "vana secimi; kavitasyon enerjisi trim icinde dagitilmali."
        )
    elif service == "liquid" and flow_regime == "cavitating-risk":
        recs.append("Baslangic kavitasyonu icin kademeli (single/multi-stage) kavitasyon trimi degerlendirilmeli.")

    if service in ("gas", "steam") and (pressure_drop_ratio_x > 0.5 or is_choked):
        recs.append(
            "Yuksek basinc dusumu / choked akis; cok kademeli basinc dusurme trimi (multi-stage letdown) "
            "gurultu ve titresimi azaltir."
        )

    if noise_db is not None:
        if noise_db > 85.0:
            recs.append(
                f"Gurultu {noise_db:.1f} dB(A) > 85 dB(A): dusuk gurultu trimi (or. Whisper Trim / aerodinamik "
                "difuzor kafes) gerekli."
            )
        elif noise_db > 75.0:
            recs.append(f"Gurultu {noise_db:.1f} dB(A): dusuk gurultu trimi secenegi degerlendirilebilir.")

    if opening_percent < 20.0:
        recs.append("Tasarim acikligi %20 altinda: reduced capacity trim veya bir kucuk vana ile kontrol kalitesi artirilmali.")
    elif opening_percent > 85.0:
        recs.append("Tasarim acikligi %85 uzerinde: bir buyuk vana govdesi veya tam kapasiteli trim degerlendirilmeli.")

    if service == "steam" and temperature_c > 230.0:
        recs.append("Yuksek sicaklik buhar: sertlestirilmis trim ve termal genlesme bosluklari vendor ile dogrulanmali.")

    if not recs:
        recs.append("Standart trim yeterli gorunuyor; ozel trim gereksinimi tespit edilmedi.")
    return recs
