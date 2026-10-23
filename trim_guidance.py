"""Rule-based trim selection and severe service cavitation guidance for control valves.

Provides engineering guidance on trim style (anti-cavitation, low-noise,
anti-flash, multi-stage) aligned with ISA-RP75.23 and IEC 60534-8-2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


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


@dataclass(frozen=True)
class StageDetail:
    """Individual pressure drop stage in a multi-stage anti-cavitation trim."""

    stage_number: int
    inlet_pressure_bar_a: float
    outlet_pressure_bar_a: float
    delta_p_bar: float
    vena_contracta_pressure_bar_a: float
    vapor_pressure_bar_a: float
    margin_to_vapor_bar: float
    is_cavitating: bool
    stage_cv: float
    fl: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_number": self.stage_number,
            "inlet_pressure_bar_a": self.inlet_pressure_bar_a,
            "outlet_pressure_bar_a": self.outlet_pressure_bar_a,
            "delta_p_bar": self.delta_p_bar,
            "vena_contracta_pressure_bar_a": self.vena_contracta_pressure_bar_a,
            "vapor_pressure_bar_a": self.vapor_pressure_bar_a,
            "margin_to_vapor_bar": self.margin_to_vapor_bar,
            "is_cavitating": self.is_cavitating,
            "stage_cv": self.stage_cv,
            "fl": self.fl,
        }


@dataclass(frozen=True)
class MultiStageTrimDesign:
    """Multi-stage anti-cavitation trim design and pressure profile analysis."""

    p1_bar_a: float
    p2_bar_a: float
    total_delta_p_bar: float
    pv_bar_a: float
    required_cv: float
    stages_count: int
    is_cavitation_eliminated: bool
    noise_reduction_dba: float
    min_recommended_stages: int
    single_stage_sigma: float
    stages: tuple[StageDetail, ...]
    trim_description: str
    warnings: tuple[str, ...]
    engineering_notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "p1_bar_a": self.p1_bar_a,
            "p2_bar_a": self.p2_bar_a,
            "total_delta_p_bar": self.total_delta_p_bar,
            "pv_bar_a": self.pv_bar_a,
            "required_cv": self.required_cv,
            "stages_count": self.stages_count,
            "is_cavitation_eliminated": self.is_cavitation_eliminated,
            "noise_reduction_dba": self.noise_reduction_dba,
            "min_recommended_stages": self.min_recommended_stages,
            "single_stage_sigma": self.single_stage_sigma,
            "stages": [s.to_dict() for s in self.stages],
            "trim_description": self.trim_description,
            "warnings": list(self.warnings),
            "engineering_notes": list(self.engineering_notes),
        }


def evaluate_cavitation_severity(
    sigma: float,
    delta_p_bar: float,
    p1_bar_a: float,
    pv_bar_a: float,
    fl: float = 0.90,
) -> CavitationAnalysis:
    """Evaluate liquid cavitation severity and determine required trim stages per ISA-RP75.23."""
    dp = max(float(delta_p_bar), 0.001)
    p1 = max(float(p1_bar_a), 0.001)
    pv = max(float(pv_bar_a), 0.0)

    scale = (fl / 0.90) ** 2 if fl > 0 else 1.0
    sigma_eff = sigma * scale

    warnings: list[str] = []
    notes: list[str] = []

    if p1 <= pv:
        severity = "Buharlaşma (Flashing)"
        stages = 1
        trim = "Anti-Flash genişleme gövdesi (Angle Body) + Stellite kaplama"
        max_dp_stage = dp
        warnings.append("Akışkan girişte kaynıyor (P1 <= Pv). Kavitasyon değil iki fazlı flashing rejimindedir.")
        notes.append("Yüksek hızlı sıvı damlacık erozyonuna karşı gövde genişletilmeli ve sertleştirilmiş yüzey seçilmelidir.")
    elif sigma_eff > 2.0:
        severity = "Güvenli (Kavitasyonsuz)"
        stages = 1
        trim = "Standart Trim"
        max_dp_stage = dp
        notes.append("Kavitasyon hasarı veya gürültü riski bulunmamaktadır.")
    elif sigma_eff > 1.5:
        severity = "Başlangıç Kavitasyonu (Incipient Cavitation)"
        stages = 1
        trim = "Sertleştirilmiş Trim (Stellite 6 / CoCr veya 410SS)"
        max_dp_stage = (p1 - pv) / (1.5 / scale) if scale > 0 else dp
        warnings.append("Düşük düzeyde kavitasyon başlangıcı tespit edildi. Uzun dönemli sit aşınması mümkündür.")
        notes.append("Tek kademeli sertleştirilmiş trim (Stellite sit/klape) yüzey ömrünü korur.")
    elif sigma_eff > 1.1:
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
    fl: float = 0.90,
) -> list[str]:
    """Return a list of trim recommendations based on operating conditions."""
    recs: list[str] = []

    if service == "liquid" and cavitation_index is not None:
        analysis = evaluate_cavitation_severity(cavitation_index, delta_p_bar, p1_bar_a, pv_bar_a, fl=fl)
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


def design_multistage_cavitation_trim(
    p1_bar_a: float,
    p2_bar_a: float,
    pv_bar_a: float,
    required_cv: float = 25.0,
    fl_per_stage: float = 0.90,
    requested_stages: int | None = None,
) -> MultiStageTrimDesign:
    """Design multi-stage anti-cavitation letdown trim and calculate stage pressure profiles."""
    p1 = max(float(p1_bar_a), 0.01)
    p2 = max(float(p2_bar_a), 0.001)
    pv = max(float(pv_bar_a), 0.0)
    dp_total = max(p1 - p2, 0.001)
    cv_req = max(float(required_cv), 0.01)
    fl = max(0.50, min(0.99, float(fl_per_stage)))

    sigma_single = (p1 - pv) / dp_total if dp_total > 0 else 999.0
    warnings: list[str] = []
    notes: list[str] = []

    if p2 <= pv:
        warnings.append(
            f"Çıkış basıncı P2 ({p2:.3f} bar) buhar basıncının ({pv:.3f} bar) altındadır. "
            "Sistem flashing (buharlaşma) rejimindedir; kademeli trim flashing oluşumunu önleyemez. "
            "Angle body ve Stellite sert kaplama gereklidir."
        )

    fl_sq = fl ** 2
    if p2 > pv and dp_total > 0:
        req_n = math.ceil((dp_total * (1.0 - fl_sq)) / (fl_sq * (p2 - pv)))
        min_stages = max(1, min(6, req_n))
    else:
        min_stages = 1

    if requested_stages is not None and requested_stages >= 1:
        n_stages = max(1, min(6, int(requested_stages)))
    elif sigma_single > 1.5:
        n_stages = 1
    elif sigma_single > 1.1:
        n_stages = max(2, min_stages)
    else:
        n_stages = max(3, min(6, max(min_stages, math.ceil(dp_total / 25.0))))

    dp_stage = dp_total / n_stages
    stage_cv = cv_req * math.sqrt(n_stages)

    stage_list: list[StageDetail] = []
    cav_eliminated = p2 > pv

    current_pin = p1
    for i in range(1, n_stages + 1):
        p_out = current_pin - dp_stage
        p_vc = current_pin - (dp_stage / fl_sq)
        margin = p_vc - pv
        is_cav = margin <= 0.0
        if is_cav:
            cav_eliminated = False

        stage_list.append(
            StageDetail(
                stage_number=i,
                inlet_pressure_bar_a=round(current_pin, 3),
                outlet_pressure_bar_a=round(p_out, 3),
                delta_p_bar=round(dp_stage, 3),
                vena_contracta_pressure_bar_a=round(p_vc, 3),
                vapor_pressure_bar_a=round(pv, 3),
                margin_to_vapor_bar=round(margin, 3),
                is_cavitating=is_cav,
                stage_cv=round(stage_cv, 2),
                fl=fl,
            )
        )
        current_pin = p_out

    noise_red = round(15.0 * math.log10(n_stages), 1) if n_stages > 1 else 0.0

    if n_stages == 1:
        trim_desc = "Tek Kademeli Standart / Sertleştirilmiş Trim"
        notes.append("Tek kademeli basınç düşümü; kavitasyon indeksi ve akış koşulları izlenmelidir.")
    elif n_stages == 2:
        trim_desc = "2-Kademeli Anti-Kavitasyon Kafesi (Cavitrol II / Çift Direnç)"
        notes.append("2 kademeli letdown ile basınç düşümü paylaştırılarak kavitasyon hasarı önlenir.")
    elif n_stages <= 4:
        trim_desc = f"{n_stages}-Kademeli Disk-Stack / Çok Kademeli Kafes (Cavitrol III / Multi-Path)"
        notes.append(f"{n_stages} direnç kademesiyle akış hızı kontrol altında tutulur ve basınç buharlaşma sınırının üzerinde kalır.")
    else:
        trim_desc = f"{n_stages}-Kademeli Ağır Hizmet Labirent Trim (Tortuous Path / Yüksek Basınç Letdown)"
        notes.append(f"{n_stages} kademeli labirent disk trim aşırı basınç düşüşlerinde (dP > 100 bar) tam kavitasyon ve aşınma koruması sağlar.")

    if not cav_eliminated and p2 > pv:
        warnings.append(
            f"{n_stages} kademede bazı kademelerde vena contracta buharlaşma basıncına yakındır. "
            f"Daha yüksek kademe ({min_stages} kademe) veya daha yüksek FL trimi değerlendiriniz."
        )

    return MultiStageTrimDesign(
        p1_bar_a=round(p1, 3),
        p2_bar_a=round(p2, 3),
        total_delta_p_bar=round(dp_total, 3),
        pv_bar_a=round(pv, 3),
        required_cv=round(cv_req, 3),
        stages_count=n_stages,
        is_cavitation_eliminated=cav_eliminated,
        noise_reduction_dba=noise_red,
        min_recommended_stages=min_stages,
        single_stage_sigma=round(sigma_single, 3),
        stages=tuple(stage_list),
        trim_description=trim_desc,
        warnings=tuple(warnings),
        engineering_notes=tuple(notes),
    )

