"""Markdown report generation for control valve sizing results.

Produces a formatted report containing process data, calculated results,
selected valve details, method notes, and reference links."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from valve_sizing import SizingResult


def build_report(service: str, fluid_summary: dict | None, result: SizingResult) -> str:
    """Generate a Markdown report string from sizing results."""
    lines = [
        "# Control Valve Sizing Report",
        "",
        f"Date: {datetime.now(UTC).isoformat().replace('+00:00', 'Z')}",
        f"Service: {service}",
        "",
        "## Result",
        f"- Required Cv: {result['required_cv']:.4f}",
        f"- Required Kv: {result['required_kv']:.4f}",
        f"- Selected Valve: DN{result['valve_dn_mm']} ({result['valve_inch']})",
        f"- Rated Cv: {result['rated_cv']:.4f}",
        f"- Rated Kv: {result['rated_kv']:.4f}",
        f"- DeltaP [bar]: {result['delta_p_bar']:.4f}",
        f"- Choked: {'Yes' if result['is_choked'] else 'No'}",
        f"- Opening (est.): {result['opening_percent']:.1f}% of rated travel",
        f"- Design margin: {result['design_margin_pct']:.1f}%",
        f"- Cv ratio (with margin / rated): {result['cv_ratio']:.3f}",
    ]

    if result.get("flow_regime"):
        lines.append(f"- Flow regime: {result['flow_regime']}")

    if result.get("rangeability_ok") is not None:
        lines.extend(["", "## Rangeability (est.)"])
        lines.append(f"- Min. controllable Cv: {result['rangeability_min_cv']:.3f}")
        status = "within rangeability" if result["rangeability_ok"] else "below rangeability"
        lines.append(f"- Status: {status}")
        lines.append("- Note: based on inherent characteristic and rangeability; vendor trim validation required.")

    if result.get("noise_db") is not None:
        lines.extend(["", "## Acoustic (est.)"])
        lines.append(f"- Predicted valve noise: {result['noise_db']:.1f} dB(A) at 1 m downstream (IEC 60534-8)")
        lines.append("- Note: estimate only; low-noise trim/diffuser selection requires vendor validation.")

    thrust = result.get("actuator_thrust_n")
    act_sel = result.get("actuator_selection")
    if thrust is not None or act_sel is not None:
        lines.extend(["", "## Actuator (est.)"])
        if isinstance(thrust, dict):
            lines.append(f"- Static unbalance thrust: {thrust.get('unbalance_n', 0.0):.1f} N")
            lines.append(f"- Shutoff thrust: {thrust.get('shutoff_n', 0.0):.1f} N")
            lines.append(f"- Packing friction: {thrust.get('packing_n', 0.0):.1f} N")
            lines.append(f"- Total estimated thrust: {thrust.get('total_n', 0.0):.1f} N")
        elif thrust is not None:
            lines.append(f"- Total estimated thrust: {thrust:.1f} N")
        if act_sel and isinstance(act_sel, dict) and act_sel.get("model"):
            lines.append(f"- Selected actuator: {act_sel['model']}")
            lines.append(f"- Thrust capacity: {act_sel.get('thrust_n', 0.0):.1f} N")
            lines.append(f"- Thrust safety margin: {act_sel.get('thrust_margin_pct', 0.0):.1f}%")
            status = "adequate" if act_sel.get("stroke_ok") else "insufficient"
            lines.append(f"- Stroke status: {status}")
        lines.append("- Note: estimate only; actuator sizing requires dynamic force and bench-set data.")

    if result.get("valve_spec"):
        spec = result["valve_spec"]
        lines.extend(["", "## Valve Specification (est.)"])
        lines.append(f"- Recommended ANSI class (P1-based): {spec.get('pressure_class_recommended', '-')}")
        lines.append(f"- Vendor body class: {spec.get('vendor_pressure_class', '-')}")
        if "derated_mawp_bar" in spec:
            t_spec = spec.get("temperature_c", 20.0)
            mat_grp = spec.get("material_group", "WCB")
            lines.append(f"- ASME B16.34 Derated MAWP: {spec['derated_mawp_bar']:.1f} bar @ {t_spec:.1f} °C ({mat_grp})")
        lines.append(f"- Recommended seat leakage class: {spec.get('leakage_class_recommended', '-')}")
        lines.append(f"- Vendor seat leakage class: {spec.get('vendor_leakage_class', '-')}")
        if "allowable_leakage" in spec and isinstance(spec["allowable_leakage"], dict):
            al = spec["allowable_leakage"]
            lines.append(f"- Max allowable seat leakage: {al.get('max_rate', 0.0):.4f} {al.get('rate_unit', '')} ({al.get('note', '')})")
        lines.append(f"- Recommended fail-safe: {spec.get('fail_safe_recommended', '-')}")
        lines.append(f"- Note: {spec.get('note', '')}")

    velocity = result.get("velocity")
    if velocity:
        lines.extend(["", "## Velocity / Erosion (est.)"])
        if "pipe_in_m_s" in velocity:
            lines.append(f"- Pipe inlet velocity: {velocity['pipe_in_m_s']:.2f} m/s")
        lines.append(f"- Pipe outlet velocity: {velocity['pipe_out_m_s']:.2f} m/s")
        if "mach_outlet" in velocity:
            lines.append(f"- Outlet Mach number: {velocity['mach_outlet']:.3f}")
        if "two_phase_out_m_s" in velocity:
            lines.append(f"- Two-phase outlet velocity: {velocity['two_phase_out_m_s']:.2f} m/s")
            lines.append(f"- API 14E erosion limit: {velocity['api_14e_limit_m_s']:.2f} m/s")
            lines.append(f"- Erosion risk: {'Yes' if velocity['erosion_risk'] else 'No'}")
        lines.append("- Note: guideline values; erosion assessment requires material and trim review.")

    if result.get("trim_guidance"):
        lines.extend(["", "## Trim Guidance (est.)"])
        for item in result["trim_guidance"]:
            lines.append(f"- {item}")
        lines.append("- Note: heuristic guidance; final trim selection requires vendor confirmation.")

    if result.get("warning"):
        lines.extend(["", "## Warning", result["warning"]])

    if fluid_summary:
        lines.extend(["", "## Fluid Summary"])
        for key, value in fluid_summary.items():
            lines.append(f"- {key}: {value}")

    iv = result.get("intermediate_values", {})
    if "Z" in iv:
        lines.extend(["", "## Compressibility (Z)"])
        lines.append(f"- Z factor: {iv['Z']:.4f}")
        lines.append(f"- Source: {iv.get('Z_source', 'Calculated from composition')}")

    lines.extend(["", "## Equations"])
    for eq in result.get("equations", []):
        lines.append(f"- {eq}")

    lines.extend(["", "## Intermediate Values"])
    for key, value in result.get("intermediate_values", {}).items():
        if isinstance(value, float):
            lines.append(f"- {key}: {value:.6g}")
        else:
            lines.append(f"- {key}: {value}")

    lines.extend(["", "## Method Notes"])
    for item in result.get("method_panel", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Sources"])
    for source in result.get("sources", []):
        lines.append(f"- {source['title']}: {source['url']}")
        lines.append(f"  Note: {source['note']}")

    if result.get("valve_meta"):
        meta = result["valve_meta"]
        lines.extend(["", "## Vendor Data"])
        for key, value in meta.items():
            lines.append(f"- {key}: {value}")

    return "\n".join(lines) + "\n"


def build_joule_thomson_report(jt: Any) -> str:
    """Generate a Markdown report from Joule-Thomson and hydrate analysis."""
    lines = [
        "# Joule-Thomson & Gaz Hidrat Raporu",
        "",
        f"- Ak\u0131\u015fkan: {jt.fluid}",
        f"- Giri\u015f Bas\u0131nc\u0131: {jt.p1_bar_a:.2f} bar(a)",
        f"- \u00c7\u0131k\u0131\u015f Bas\u0131nc\u0131: {jt.p2_bar_a:.2f} bar(a)",
        f"- Giri\u015f S\u0131cakl\u0131\u011f\u0131 (T1): {jt.t1_c:.1f} \u00b0C",
        f"- \u00c7\u0131k\u0131\u015f S\u0131cakl\u0131\u011f\u0131 (T2): {jt.t2_c:.1f} \u00b0C",
        f"- S\u0131cakl\u0131k D\u00fc\u015f\u00fc\u015f\u00fc (\u0394T_JT): {jt.delta_t_c:.1f} \u00b0C",
        f"- J-T Katsay\u0131s\u0131 (\u03bc_JT): {jt.mu_jt_c_per_bar:.3f} \u00b0C/bar",
        f"- Hidrat Olu\u015fma S\u0131cakl\u0131\u011f\u0131 (T_hyd @ P2): {jt.t_hydrate_c:.1f} \u00b0C",
        f"- Hidrat Riski: {'VAR (Tehlike)' if jt.hydrate_risk else 'YOK (G\u00fcvenli)'}",
        f"- Donma Riski (T2 <= 0 \u00b0C): {'VAR (Buzlanma)' if jt.freezing_risk else 'YOK'}",
        f"- Minimum \u00d6n \u0131s\u0131t\u0131c\u0131 S\u0131cakl\u0131\u011f\u0131: {jt.t_preheat_min_c:.1f} \u00b0C",
        "",
        "## \u00d6zet ve Uyar\u0131lar",
        jt.summary,
    ]
    for w in jt.warnings:
        lines.append(f"- {w}")
    return "\n".join(lines) + "\n"


def build_multicase_report(analysis: Any) -> str:
    """Generate a Markdown report from multi-case sizing analysis."""
    lines = [
        "# \u00c7oklu \u00c7al\u0131\u015fma Durumu (Multi-Case) Vana Boyutland\u0131rma Raporu",
        "",
        f"- Servis: {analysis.service}",
        f"- Turndown Oran\u0131 (Qmax / Qmin): {analysis.turndown_ratio:.1f}:1",
        f"- Genel De\u011ferlendirme: {analysis.overall_summary}",
        "",
        "## \u00c7al\u0131\u015fma Durumlar\u0131 (Operating Cases)",
    ]
    for c in analysis.cases:
        lines.append(f"- **{c.name}**: Debi = {c.flow}, P1 = {c.p1_bar_a:.2f} bar, P2 = {c.p2_bar_a:.2f} bar, T = {c.temperature_c:.1f} \u00b0C")

    rec = analysis.recommended
    if rec:
        lines.extend([
            "",
            "## \u00d6nerilen Vana Se\u00e7imi",
            f"- Vana \u00c7ap\u0131: DN{rec.valve.dn_mm} ({rec.valve.inch})",
            f"- Nominal Kapasite (Rated Cv): {rec.valve.cv_rated:.1f}",
            f"- Min Ak\u0131\u015f A\u00e7\u0131kl\u0131\u011f\u0131: %{rec.opening_min_pct:.1f}",
            f"- Normal Ak\u0131\u015f A\u00e7\u0131kl\u0131\u011f\u0131: %{rec.opening_norm_pct:.1f}",
            f"- Max Ak\u0131\u015f A\u00e7\u0131kl\u0131\u011f\u0131: %{rec.opening_max_pct:.1f}",
            f"- Durum: {rec.status_label}",
        ])
        for note in rec.evaluation_notes:
            lines.append(f"- Not: {note}")

    lines.extend(["", "## T\u00fcm Vana Adaylar\u0131"])
    for cand in analysis.candidates:
        flag = " [\u00d6NER\u0130LEN]" if cand.is_recommended else ""
        lines.append(
            f"- DN{cand.valve.dn_mm} ({cand.valve.inch}) [Cv {cand.valve.cv_rated}]: "
            f"Min %{cand.opening_min_pct:.1f} | Norm %{cand.opening_norm_pct:.1f} | Max %{cand.opening_max_pct:.1f} "
            f"-> {cand.status_label}{flag}"
        )

    return "\n".join(lines) + "\n"


def build_isa20_report(
    result: Any,
    tag: str = "CV-101",
    service_desc: str = "Control Valve",
    line_no: str = "",
    pid_no: str = "",
    fluid_name: str = "",
    body_material: str = "WCB",
) -> str:
    """Generate an ISA-20 datasheet report in Markdown format."""
    from datasheet_isa20 import build_isa20_datasheet, generate_isa20_markdown
    from packing_emissions import recommend_packing_system

    srv = result.get("service", "liquid")
    temp_c = float(result.get("extra", {}).get("temperature_c", 25.0))
    p1 = float(result.get("extra", {}).get("p1", 5.0))
    fluid = fluid_name or ("Water" if srv == "liquid" else ("NaturalGas" if srv == "gas" else "Steam"))
    packing = recommend_packing_system(srv, fluid, temp_c, p1)

    sheet = build_isa20_datasheet(
        tag_number=tag,
        service_description=service_desc,
        line_number=line_no,
        pid_number=pid_no,
        service_type=srv,
        fluid_name=fluid,
        sizing_result=result,
        body_material=body_material,
        packing_guidance=packing,
    )
    return generate_isa20_markdown(sheet)


def build_isa20_html_report(
    result: Any,
    tag: str = "CV-101",
    service_desc: str = "Control Valve",
    line_no: str = "",
    pid_no: str = "",
    fluid_name: str = "",
    body_material: str = "WCB",
) -> str:
    """Generate an ISA-20 datasheet report in HTML/Excel format."""
    from datasheet_isa20 import build_isa20_datasheet, generate_isa20_html
    from packing_emissions import recommend_packing_system

    srv = result.get("service", "liquid")
    temp_c = float(result.get("extra", {}).get("temperature_c", 25.0))
    p1 = float(result.get("extra", {}).get("p1", 5.0))
    fluid = fluid_name or ("Water" if srv == "liquid" else ("NaturalGas" if srv == "gas" else "Steam"))
    packing = recommend_packing_system(srv, fluid, temp_c, p1)

    sheet = build_isa20_datasheet(
        tag_number=tag,
        service_description=service_desc,
        line_number=line_no,
        pid_number=pid_no,
        service_type=srv,
        fluid_name=fluid,
        sizing_result=result,
        body_material=body_material,
        packing_guidance=packing,
    )
    return generate_isa20_html(sheet)


def build_safety_piping_report(
    service: str,
    velocity_m_s: float,
    density_kg_m3: float,
    rated_cv: float,
    p1_bar_a: float,
    p_relief_bar_a: float,
    fluid_data: dict[str, float] | None = None,
) -> str:
    """Generate an API 14E erosional velocity and API 520 wide-open relief report in Markdown."""
    from safety_piping import calc_wide_open_relief_capacity, check_erosional_velocity

    eros = check_erosional_velocity(velocity_m_s, density_kg_m3)
    relief = calc_wide_open_relief_capacity(service, rated_cv, p1_bar_a, p_relief_bar_a, fluid_data)

    lines = [
        "# BORU GUVENLIGI VE TAHLIYE KAPASITESI RAPORU (API 14E / API 520)",
        "",
        "## 1. API RP 14E Boru Erozyonel Hız Değerlendirmesi",
        f"- **Mevcut Boru Çıkış Hızı:** {eros.actual_velocity_m_s:.2f} m/s",
        f"- **API 14E Erozyonel Hız Limiti (ve):** {eros.erosional_limit_m_s:.2f} m/s (c = {eros.c_factor:.0f})",
        f"- **Hız Oranı (v / ve):** %{eros.velocity_ratio * 100.0:.1f}",
        f"- **Erozyon Limiti Aşıldı mı?:** {'EVET (TEHLİKE!)' if eros.is_velocity_exceeded else 'HAYIR (GÜVENLİ)'}",
    ]
    if eros.min_recommended_pipe_dn_mm > 0:
        lines.append(f"- **Önerilen Minimum Çıkış Boru Çapı:** DN{eros.min_recommended_pipe_dn_mm}")
    for w in eros.warnings:
        lines.append(f"- **[UYARI]:** {w}")
    for r in eros.recommendations:
        lines.append(f"- {r}")

    lines.extend([
        "",
        "## 2. API RP 520 Vana Tam Açık Arıza Tahliye Kapasitesi (Wide-Open Relief Load)",
        f"- **Nominal Vana Kapasitesi (Rated Cv):** {relief.rated_cv:.1f}",
        f"- **Giriş Basıncı P1:** {relief.inlet_pressure_bar_a:.2f} bar(a)",
        f"- **Emniyet Ventili (PSV) Tahliye Basıncı Prelief:** {relief.relief_pressure_bar_a:.2f} bar(a)",
        f"- **Fark Basınç ΔP:** {relief.differential_pressure_bar:.2f} bar",
        f"- **Maksimum Arıza Tahliye Debisi:** {relief.wide_open_flow_rate:.1f} {relief.flow_unit}",
        f"- **Akış Boğuldu mu (Choked)?:** {'EVET' if relief.is_choked else 'HAYIR'}",
    ])
    for n in relief.safety_notes:
        lines.append(f"- {n}")

    return "\n".join(lines) + "\n"


