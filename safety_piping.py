"""Piping safety and relief load analysis per API RP 14E and API 520 / ISA-75.01.

Provides engineering verification for:
1. API RP 14E erosional velocity limits to prevent pipe wall thinning.
2. Control valve wide-open failure relief capacity for downstream PSV sizing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ErosionalVelocityCheck:
    """Evaluation of fluid velocity against API RP 14E erosional limits."""

    actual_velocity_m_s: float
    erosional_limit_m_s: float
    c_factor: float
    density_kg_m3: float
    is_velocity_exceeded: bool
    velocity_ratio: float
    min_recommended_pipe_dn_mm: int
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReliefCapacityAnalysis:
    """Control valve wide-open failure discharge capacity for relief sizing."""

    service: str
    rated_cv: float
    inlet_pressure_bar_a: float
    relief_pressure_bar_a: float
    differential_pressure_bar: float
    wide_open_flow_rate: float
    flow_unit: str
    is_choked: bool
    safety_notes: list[str] = field(default_factory=list)


def check_erosional_velocity(
    actual_velocity_m_s: float,
    density_kg_m3: float,
    actual_flow_m3_s: float = 0.0,
    c_factor: float = 100.0,
) -> ErosionalVelocityCheck:
    """Evaluate fluid velocity against API RP 14E erosional velocity limit."""
    rho = max(float(density_kg_m3), 0.001)
    v_act = max(float(actual_velocity_m_s), 0.0)
    c_val = max(float(c_factor), 10.0)

    v_limit = (1.22 * c_val) / math.sqrt(rho)
    ratio = v_act / v_limit if v_limit > 0 else 1.0
    exceeded = v_act > v_limit

    warnings: list[str] = []
    recs: list[str] = []
    min_dn = 0

    if exceeded:
        warnings.append(
            f"Boru hızı ({v_act:.2f} m/s) API 14E erozyonel hız limitini ({v_limit:.2f} m/s) aşıyor! "
            f"Oran: %{ratio * 100.0:.1f}."
        )
        recs.append("Boru cidarında aşınma/incelme riskine karşı vana çıkış boru çapı genişletilmelidir.")
        recs.append("Vana çıkışına redüksiyon / konik genişletici (expander) monte edilmelidir.")
        if actual_flow_m3_s > 0.0:
            target_v = v_limit * 0.85
            req_area = actual_flow_m3_s / target_v
            req_d_m = math.sqrt((4.0 * req_area) / math.pi)
            req_d_mm = req_d_m * 1000.0
            standard_dns = [15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200, 250, 300, 350, 400, 450, 500, 600]
            for dn in standard_dns:
                if dn >= req_d_mm:
                    min_dn = dn
                    break
            if min_dn == 0:
                min_dn = int(math.ceil(req_d_mm))
            recs.append(f"Önerilen minimum çıkış boru anma çapı: DN{min_dn} ({min_dn} mm).")
    else:
        recs.append(
            f"Boru hızı ({v_act:.2f} m/s) API 14E sınırının ({v_limit:.2f} m/s) altındadır; cidar aşınma riski güvenlidir."
        )

    return ErosionalVelocityCheck(
        actual_velocity_m_s=v_act,
        erosional_limit_m_s=v_limit,
        c_factor=c_val,
        density_kg_m3=rho,
        is_velocity_exceeded=exceeded,
        velocity_ratio=ratio,
        min_recommended_pipe_dn_mm=min_dn,
        warnings=warnings,
        recommendations=recs,
    )


def calc_wide_open_relief_capacity(
    service: str,
    rated_cv: float,
    inlet_pressure_bar_a: float,
    relief_pressure_bar_a: float,
    fluid_data: dict[str, float] | None = None,
) -> ReliefCapacityAnalysis:
    """Calculate maximum discharge capacity when control valve fails wide-open for PSV sizing."""
    cv = max(float(rated_cv), 0.01)
    p1 = max(float(inlet_pressure_bar_a), 0.01)
    p_rel = max(float(relief_pressure_bar_a), 0.0)
    data = fluid_data or {}

    dp = max(p1 - p_rel, 0.001)
    srv = service.lower().strip()
    is_choked = False
    notes: list[str] = []

    if srv == "liquid":
        sg = max(float(data.get("specific_gravity", 1.0)), 0.01)
        pv = max(float(data.get("vapor_pressure_bar_a", 0.023)), 0.0)
        fl = max(float(data.get("fl", 0.90)), 0.1)
        dp_max = (fl ** 2) * (p1 - 0.96 * pv)
        if dp > dp_max > 0:
            effective_dp = dp_max
            is_choked = True
            notes.append("Vana tam açık akışta kavitasyonel boğulmaya (choking) uğramaktadır.")
        else:
            effective_dp = dp
        flow_m3h = 0.865 * cv * math.sqrt(effective_dp / sg)
        flow_val = flow_m3h
        unit = "m\u00b3/h"
        notes.append(
            f"Downstream emniyet vanası (PSV) en az {flow_val:.1f} {unit} tahliye kapasitesine göre boyutlandırılmalıdır."
        )

    elif srv == "gas":
        mw = max(float(data.get("molecular_weight", 28.96)), 1.0)
        t_c = float(data.get("temperature_c", 20.0))
        t_k = t_c + 273.15
        z = max(float(data.get("z", 1.0)), 0.1)
        k = max(float(data.get("specific_heat_ratio", 1.40)), 1.01)
        xt = max(float(data.get("xt", 0.70)), 0.1)
        fk = k / 1.40
        xt_actual = xt * fk
        x = dp / p1
        if x >= xt_actual:
            x_eff = xt_actual
            y = 0.667
            is_choked = True
            notes.append("Gaz akışı vana tam açık durumda sonik boğulmaya (choked flow) ulaşmaktadır.")
        else:
            x_eff = x
            y = 1.0 - (x_eff / (3.0 * xt_actual))

        flow_nm3h = (cv * 24.6 * (p1 * 100.0) * y * math.sqrt(x_eff)) / math.sqrt(mw * t_k * z)
        flow_val = flow_nm3h
        unit = "Nm\u00b3/h"
        notes.append(
            f"Downstream PSV için gaz arıza tahliye kapasitesi: {flow_val:.1f} {unit}."
        )

    else:
        rho = max(float(data.get("density_kg_m3", 5.0)), 0.01)
        xt = max(float(data.get("xt", 0.70)), 0.1)
        x = dp / p1
        if x >= xt:
            x_eff = xt
            y = 0.667
            is_choked = True
            notes.append("Buhar akışı vana tam açık durumda boğulma rejimindedir.")
        else:
            x_eff = x
            y = 1.0 - (x_eff / (3.0 * xt))
        flow_kgh = cv * 27.3 * y * math.sqrt(x_eff * (p1 * 100.0) * rho)
        flow_val = flow_kgh
        unit = "kg/h"
        notes.append(
            f"Downstream PSV için buhar arıza tahliye kapasitesi: {flow_val:.1f} {unit}."
        )

    notes.append(
        "API RP 520 Kısım 1 gereği kontrol vanası tam açık arızası (fail-open) aşırı basınç senaryosudur."
    )

    return ReliefCapacityAnalysis(
        service=service,
        rated_cv=cv,
        inlet_pressure_bar_a=p1,
        relief_pressure_bar_a=p_rel,
        differential_pressure_bar=dp,
        wide_open_flow_rate=flow_val,
        flow_unit=unit,
        is_choked=is_choked,
        safety_notes=notes,
    )
