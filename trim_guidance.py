"""Rule-based trim selection guidance for control valves.

Provides engineering guidance on trim style (anti-cavitation, low-noise,
anti-flash, multi-stage) from the sizing result conditions. These rules
are heuristics aligned with vendor practices (Fisher Cavitrol/Whisper,
etc.); final trim selection requires vendor confirmation.
"""

from __future__ import annotations


def recommend_trim(
    service: str,
    flow_regime: str = "",
    is_choked: bool = False,
    noise_db: float | None = None,
    opening_percent: float = 50.0,
    cavitation_index: float | None = None,
    pressure_drop_ratio_x: float = 0.0,
    temperature_c: float = 25.0,
) -> list[str]:
    """Return a list of trim recommendations (Turkish) based on conditions.

    Parameters
    ----------
    service : "liquid", "gas", or "steam"
    flow_regime : Liquid flow regime label ("" for gas/steam)
    is_choked : Choked-flow flag
    noise_db : Predicted noise [dB(A)] if available
    opening_percent : Estimated design opening [%]
    cavitation_index : Classic cavitation index (liquid only)
    pressure_drop_ratio_x : dP/P1 (gas/steam)
    temperature_c : Process temperature [C]
    """
    recs: list[str] = []

    if service == "liquid" and flow_regime == "flashing":
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

    if (
        service == "liquid"
        and cavitation_index is not None
        and cavitation_index < 1.5
        and flow_regime not in ("flashing", "choked-cavitating")
    ):
        recs.append("Cavitation index dusuk; sertlestirilmis trim malzemesi onerilir.")

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
