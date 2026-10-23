"""Markdown report generation for control valve sizing results.

Produces a formatted report containing process data, calculated results,
selected valve details, method notes, and reference links."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF

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

    try:
        from vendor_catalog import find_catalog_matches

        req_cv = float(result.get("required_cv", 0.0))
        if req_cv > 0:
            matches = find_catalog_matches(req_cv)
            if matches:
                lines.extend(["", "## Suitable Vendor Valve Models (Global Catalog Matches)"])
                lines.append("| Manufacturer | Model | Type | DN (inch) | Rated Cv | Opening % | Status |")
                lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
                for m in matches[:6]:
                    lines.append(
                        f"| {m['manufacturer']} | {m['model_name']} | {m['valve_type']} | "
                        f"DN{m['dn_mm']} ({m['inch']}) | {m['cv_rated']:.1f} | {m['opening_percent']:.1f}% | {m['status']} |"
                    )
    except Exception:
        pass

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
        f"- Hidrat Riski: {'VAR (Tehlike)' if jt.hydrate_risk else 'YOK (Güvenli)'}",
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

    if getattr(analysis, "split_range", None):
        sr = analysis.split_range
        lines.extend([
            "",
            "## Paralel Split-Range Vana Çözümü (Dual-Valve Configuration)",
            f"- Vana A (Küçük Debi): DN{sr.small_valve.dn_mm} ({sr.small_valve.inch}), Rated Cv: {sr.small_valve_cv_rated:.1f}",
            f"- Vana B (Büyük Debi): DN{sr.large_valve.dn_mm} ({sr.large_valve.inch}), Rated Cv: {sr.large_valve_cv_rated:.1f}",
            f"- Toplam Nominal Kapasite: {sr.total_cv_rated:.1f} Cv",
            f"- Kombine Efektif Rangeability: ~{sr.combined_rangeability:.0f}:1",
            f"- Sinyal Dağılımı Vana A: {sr.signal_range_small}",
            f"- Sinyal Dağılımı Vana B: {sr.signal_range_large}",
            f"- DCS Geçiş Örtüşmesi: {sr.overlap_range}",
        ])
        for r in sr.recommendations:
            lines.append(f"- Mühendislik Notu: {r}")

    return "\n".join(lines) + "\n"


def build_isa20_report(
    result: Any,
    tag: str = "CV-101",
    service_desc: str = "Control Valve",
    line_no: str = "",
    pid_no: str = "",
    fluid_name: str = "",
    body_material: str = "WCB",
    multicase_cases: list[dict[str, Any]] | None = None,
    bonnet_type: str = "Standard",
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
        multicase_cases=multicase_cases,
        bonnet_type=bonnet_type,
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
    multicase_cases: list[dict[str, Any]] | None = None,
    bonnet_type: str = "Standard",
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
        multicase_cases=multicase_cases,
        bonnet_type=bonnet_type,
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
    actual_flow_m3_s: float | None = None,
) -> str:
    """Generate an API 14E erosional velocity and API 520 wide-open relief report in Markdown."""
    from safety_piping import calc_wide_open_relief_capacity, check_erosional_velocity

    eros = check_erosional_velocity(
        velocity_m_s, density_kg_m3,
        actual_flow_m3_s=actual_flow_m3_s if actual_flow_m3_s is not None else 0.0,
    )
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


def _pdf_safe(text: str) -> str:
    """Replace Turkish glyphs absent from fpdf2 core fonts (Latin-1)."""
    return (
        str(text)
        .replace("İ", "I").replace("ı", "i")
        .replace("Ğ", "G").replace("ğ", "g")
        .replace("Ş", "S").replace("ş", "s")
    )


def build_pdf_report(service: str, fluid_summary: dict | None, result: SizingResult) -> bytes:
    """Generate a PDF report from sizing results (fpdf2, core fonts)."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=10)

    def title(text: str) -> None:
        pdf.set_font("Helvetica", style="B", size=14)
        pdf.cell(0, 8, _pdf_safe(text), ln=1)  # type: ignore[arg-type]
        pdf.set_font("Helvetica", size=10)
        pdf.ln(2)

    def heading(text: str) -> None:
        pdf.set_font("Helvetica", style="B", size=11)
        pdf.cell(0, 7, _pdf_safe(text), ln=1)  # type: ignore[arg-type]
        pdf.set_font("Helvetica", size=10)
        pdf.ln(1)

    def field(label: str, value: str) -> None:
        pdf.cell(55, 5, _pdf_safe(label))
        pdf.cell(0, 5, _pdf_safe(value), ln=1)  # type: ignore[arg-type]

    def para(text: str) -> None:
        pdf.multi_cell(0, 5, _pdf_safe(text))
        pdf.ln(1)

    def summary_box(x: float, y: float, w: float, h: float, label: str, value: str, ok: bool | None) -> None:
        if ok is True:
            pdf.set_fill_color(232, 245, 233)
        elif ok is False:
            pdf.set_fill_color(253, 235, 236)
        else:
            pdf.set_fill_color(240, 240, 240)
        pdf.rect(x, y, w, h, style="F")
        pdf.set_draw_color(200, 200, 200)
        pdf.rect(x, y, w, h)
        pdf.set_font("Helvetica", size=7)
        pdf.set_xy(x, y + 1.5)
        pdf.cell(w, 4, _pdf_safe(label), align="C")
        pdf.set_font("Helvetica", style="B", size=10)
        pdf.set_xy(x, y + 6)
        pdf.cell(w, 5, _pdf_safe(value), align="C")
        pdf.set_font("Helvetica", size=10)

    def summary_strip() -> None:
        """Color-coded highlight boxes for noise, actuator margin, opening and choking."""
        heading("Key Highlights")
        x0 = pdf.get_x()
        y0 = pdf.get_y()
        box_w, box_h, gap = 44.0, 14.0, 4.0
        noise = result.get("noise_db")
        noise_ok = None if noise is None else (float(noise) <= 85.0)
        summary_box(x0, y0, box_w, box_h, "Noise", f"{float(noise):.1f} dBA" if noise is not None else "n/a", noise_ok)
        act = result.get("actuator_selection")
        if act and isinstance(act, dict) and act.get("model"):
            summary_box(x0 + box_w + gap, y0, box_w, box_h, "Actuator margin",
                        f"+%{act.get('thrust_margin_pct', 0.0):.0f}", bool(act.get("stroke_ok")))
        else:
            summary_box(x0 + box_w + gap, y0, box_w, box_h, "Actuator margin", "n/a", None)
        opening = float(result["opening_percent"])
        summary_box(x0 + 2 * (box_w + gap), y0, box_w, box_h, "Opening", f"{opening:.1f}%", 20.0 <= opening <= 85.0)
        choked = bool(result["is_choked"])
        summary_box(x0 + 3 * (box_w + gap), y0, box_w, box_h, "Choked flow", "Yes" if choked else "No", not choked)
        pdf.set_y(y0 + box_h + 3)

    def curve_chart() -> None:
        """Draw the inherent characteristic curve with the operating point (fpdf2 primitives)."""
        if float(result["rated_cv"]) <= 0:
            return
        try:
            from valve_curve import generate_characteristic_curve

            chart = generate_characteristic_curve(
                rated_cv=float(result["rated_cv"]),
                required_cv=float(result["required_cv"]),
                characteristic=str(result.get("flow_characteristic", "equal_percentage")),
            )
        except Exception:
            return
        heading("Valve Characteristic Curve")
        x0 = pdf.get_x()
        y0 = pdf.get_y()
        w, h = 170.0, 48.0
        if y0 + h + 14 > pdf.h - pdf.b_margin:
            pdf.add_page()
            x0 = pdf.get_x()
            y0 = pdf.get_y()
        max_cv = max((pt.cv for pt in chart.points), default=0.0) or 1.0
        pdf.set_draw_color(150, 150, 150)
        pdf.set_line_width(0.2)
        pdf.rect(x0, y0, w, h)
        for pct in (25.0, 50.0, 75.0):
            gx = x0 + pct / 100.0 * w
            pdf.line(gx, y0, gx, y0 + h)
        ry = y0 + h - min(float(result["required_cv"]) / max_cv, 1.0) * h
        pdf.set_draw_color(200, 60, 60)
        pdf.line(x0, ry, x0 + w, ry)
        pdf.set_draw_color(30, 80, 140)
        pdf.set_line_width(0.6)
        prev: tuple[float, float] | None = None
        for pt in chart.points:
            px = x0 + pt.opening_pct / 100.0 * w
            py = y0 + h - min(pt.cv / max_cv, 1.0) * h
            if prev is not None:
                pdf.line(prev[0], prev[1], px, py)
            prev = (px, py)
        op = chart.operating_point
        ox = x0 + min(op.opening_pct, 100.0) / 100.0 * w
        oy = y0 + h - min(op.required_cv / max_cv, 1.0) * h
        pdf.set_fill_color(200, 60, 60)
        pdf.ellipse(ox - 1.2, oy - 1.2, 2.4, 2.4, style="F")
        pdf.set_font("Helvetica", size=8)
        pdf.set_xy(x0, y0 + h + 1)
        pdf.cell(w, 4, "X: Opening [%] 0-100 | Y: Cv | red = required Cv, dot = operating point", align="C")
        pdf.set_font("Helvetica", size=10)
        pdf.set_y(y0 + h + 6)
        field("Characteristic:", f"{chart.characteristic} | opening {op.opening_pct:.1f}% | {op.controllability_zone}")
        pdf.ln(2)

    def curve_table() -> None:
        """Önemli açıklık noktalarında Cv/Kv değerlerini tabloyla gösterir."""
        try:
            from valve_curve import generate_characteristic_curve

            chart = generate_characteristic_curve(
                rated_cv=float(result["rated_cv"]),
                required_cv=float(result["required_cv"]),
                characteristic=str(result.get("flow_characteristic", "equal_percentage")),
            )
        except Exception:
            return
        if float(result["rated_cv"]) <= 0 or not chart.points:
            return
        heading("Characteristic Curve Values")
        # 25/50/75/100% noktalarını seç
        points = chart.points
        picks = {}
        for pct in (25.0, 50.0, 75.0, 100.0):
            nearest = min(points, key=lambda pt: abs(pt.opening_pct - pct))
            picks[nearest.opening_pct] = nearest
        col_w = [30.0, 40.0, 40.0]
        col_x = pdf.get_x()
        y0 = pdf.get_y()
        if y0 + 14 > pdf.h - pdf.b_margin:
            pdf.add_page()
            col_x = pdf.get_x()
            y0 = pdf.get_y()
        pdf.set_font("Helvetica", style="B", size=9)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(col_w[0], 6, "Opening [%]", border=1, align="C", fill=True)
        pdf.cell(col_w[1], 6, "Cv", border=1, align="C", fill=True)
        pdf.cell(col_w[2], 6, "Kv", border=1, align="C", fill=True)
        pdf.ln(6)
        pdf.set_font("Helvetica", size=9)
        for op_pt in [picks.get(p) for p in (25.0, 50.0, 75.0, 100.0)]:
            if op_pt is None:
                continue
            pdf.set_x(col_x)
            pdf.cell(col_w[0], 5, f"{op_pt.opening_pct:.0f}", border=1, align="C")
            pdf.cell(col_w[1], 6, f"{op_pt.cv:.3f}", border=1, align="C")
            pdf.cell(col_w[2], 6, f"{op_pt.cv:.3f}", border=1, align="C")
            pdf.ln(6)
        pdf.ln(2)

    # Header
    title("Control Valve Sizing Report")
    field("Date:", datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    field("Service:", service)
    pdf.ln(2)

    # Result
    heading("Result")
    field("Required Cv:", f"{result['required_cv']:.4f}")
    field("Required Kv:", f"{result['required_kv']:.4f}")
    field("Selected Valve:", f"DN{result['valve_dn_mm']} ({result['valve_inch']})")
    field("Rated Cv:", f"{result['rated_cv']:.4f}")
    field("Rated Kv:", f"{result['rated_kv']:.4f}")
    field("DeltaP [bar]:", f"{result['delta_p_bar']:.4f}")
    field("Choked:", "Yes" if result["is_choked"] else "No")
    field("Opening (est.):", f"{result['opening_percent']:.1f}% of rated travel")
    field("Design margin:", f"{result['design_margin_pct']:.1f}%")
    field("Cv ratio:", f"{result['cv_ratio']:.3f}")
    pdf.ln(2)

    summary_strip()
    curve_chart()
    curve_table()

    if result.get("flow_regime"):
        heading("Flow Regime")
        para(f"{result['flow_regime']}")

    if result.get("rangeability_ok") is not None:
        heading("Rangeability (est.)")
        field("Min. controllable Cv:", f"{result['rangeability_min_cv']:.3f}")
        status = "within rangeability" if result["rangeability_ok"] else "below rangeability"
        field("Status:", status)
        para("Note: based on inherent characteristic and rangeability; vendor trim validation required.")

    if result.get("noise_db") is not None:
        heading("Acoustic (est.)")
        field("Predicted valve noise:", f"{result['noise_db']:.1f} dB(A) at 1 m downstream (IEC 60534-8)")
        para("Note: estimate only; low-noise trim/diffuser selection requires vendor validation.")

    thrust = result.get("actuator_thrust_n")
    act_sel = result.get("actuator_selection")
    if thrust is not None or act_sel is not None:
        heading("Actuator (est.)")
        if isinstance(thrust, dict):
            field("Static unbalance thrust:", f"{thrust.get('unbalance_n', 0.0):.1f} N")
            field("Shutoff thrust:", f"{thrust.get('shutoff_n', 0.0):.1f} N")
            field("Packing friction:", f"{thrust.get('packing_n', 0.0):.1f} N")
            field("Total estimated thrust:", f"{thrust.get('total_n', 0.0):.1f} N")
        elif thrust is not None:
            field("Total estimated thrust:", f"{thrust:.1f} N")
        if act_sel and isinstance(act_sel, dict) and act_sel.get("model"):
            field("Selected actuator:", act_sel["model"])
            field("Thrust capacity:", f"{act_sel.get('thrust_n', 0.0):.1f} N")
            field("Thrust safety margin:", f"{act_sel.get('thrust_margin_pct', 0.0):.1f}%")
            status = "adequate" if act_sel.get("stroke_ok") else "insufficient"
            field("Stroke status:", status)
        para("Note: estimate only; actuator sizing requires dynamic force and bench-set data.")

    if result.get("valve_spec"):
        spec = result["valve_spec"]
        heading("Valve Specification (est.)")
        field("Recommended ANSI class (P1-based):", spec.get("pressure_class_recommended", "-"))
        field("Vendor body class:", spec.get("vendor_pressure_class", "-"))
        if "derated_mawp_bar" in spec:
            t_spec = spec.get("temperature_c", 20.0)
            mat_grp = spec.get("material_group", "WCB")
            field("ASME B16.34 Derated MAWP:", f"{spec['derated_mawp_bar']:.1f} bar @ {t_spec:.1f} C ({mat_grp})")
        field("Recommended seat leakage class:", spec.get("leakage_class_recommended", "-"))
        field("Vendor seat leakage class:", spec.get("vendor_leakage_class", "-"))
        if "allowable_leakage" in spec and isinstance(spec["allowable_leakage"], dict):
            al = spec["allowable_leakage"]
            field("Max allowable seat leakage:", f"{al.get('max_rate', 0.0):.4f} {al.get('rate_unit', '')} ({al.get('note', '')})")
        field("Recommended fail-safe:", spec.get("fail_safe_recommended", "-"))
        para(f"Note: {spec.get('note', '')}")

    velocity = result.get("velocity")
    if velocity:
        heading("Velocity / Erosion (est.)")
        if "pipe_in_m_s" in velocity:
            field("Pipe inlet velocity:", f"{velocity['pipe_in_m_s']:.2f} m/s")
        field("Pipe outlet velocity:", f"{velocity['pipe_out_m_s']:.2f} m/s")
        if "mach_outlet" in velocity:
            field("Outlet Mach number:", f"{velocity['mach_outlet']:.3f}")
        if "two_phase_out_m_s" in velocity:
            field("Two-phase outlet velocity:", f"{velocity['two_phase_out_m_s']:.2f} m/s")
            field("API 14E erosion limit:", f"{velocity['api_14e_limit_m_s']:.2f} m/s")
            field("Erosion risk:", "Yes" if velocity["erosion_risk"] else "No")
        para("Note: guideline values; erosion assessment requires material and trim review.")

    if result.get("trim_guidance"):
        heading("Trim Guidance (est.)")
        for item in result["trim_guidance"]:
            pdf.cell(0, 5, f"- {_pdf_safe(item)}", ln=1)  # type: ignore[arg-type]
        para("Note: heuristic guidance; final trim selection requires vendor confirmation.")

    if result.get("warning"):
        heading("Warning")
        para(result["warning"])

    if fluid_summary:
        heading("Fluid Summary")
        for key, value in fluid_summary.items():
            field(f"{key}:", str(value))

    iv = result.get("intermediate_values", {})
    if "Z" in iv:
        heading("Compressibility (Z)")
        field("Z factor:", f"{iv['Z']:.4f}")
        field("Source:", iv.get("Z_source", "Calculated from composition"))

    heading("Equations")
    for eq in result.get("equations", []):
        pdf.cell(0, 5, f"- {_pdf_safe(eq)}", ln=1)  # type: ignore[arg-type]

    heading("Intermediate Values")
    for key, value in result.get("intermediate_values", {}).items():
        if isinstance(value, float):
            field(f"{key}:", f"{value:.6g}")
        else:
            field(f"{key}:", str(value))

    heading("Method Notes")
    for item in result.get("method_panel", []):
        pdf.cell(0, 5, f"- {_pdf_safe(item)}", ln=1)  # type: ignore[arg-type]

    heading("Sources")
    for source in result.get("sources", []):
        pdf.cell(0, 5, f"- {_pdf_safe(source['title'])}: {source['url']}", ln=1)  # type: ignore[arg-type]
        pdf.cell(0, 5, f"  Note: {_pdf_safe(source['note'])}", ln=1)  # type: ignore[arg-type]

    if result.get("valve_meta"):
        heading("Vendor Data")
        meta = result["valve_meta"]
        for key, value in meta.items():
            field(f"{key}:", str(value))

    try:
        from vendor_catalog import find_catalog_matches

        req_cv = float(result.get("required_cv", 0.0))
        if req_cv > 0:
            matches = find_catalog_matches(req_cv)
            if matches:
                heading("Suitable Vendor Valve Models (Global Matches)")
                pdf.set_font("Helvetica", style="B", size=8)
                pdf.set_fill_color(240, 240, 240)
                col_w = [30, 32, 28, 26, 20, 22, 28]
                for i, h in enumerate(["Vendor", "Model", "Type", "Size", "Rated Cv", "Opening", "Status"]):
                    pdf.cell(col_w[i], 5, _pdf_safe(h), border=1, fill=True, align="C")
                pdf.ln()
                pdf.set_font("Helvetica", size=8)
                for m in matches[:6]:
                    pdf.cell(col_w[0], 5, _pdf_safe(m["manufacturer"][:14]), border=1)
                    pdf.cell(col_w[1], 5, _pdf_safe(m["model_name"][:16]), border=1)
                    pdf.cell(col_w[2], 5, _pdf_safe(m["valve_type"][:14]), border=1)
                    pdf.cell(col_w[3], 5, _pdf_safe(f"DN{m['dn_mm']} {m['inch']}"), border=1, align="C")
                    pdf.cell(col_w[4], 5, f"{m['cv_rated']:.1f}", border=1, align="R")
                    pdf.cell(col_w[5], 5, f"{m['opening_percent']:.1f}%", border=1, align="R")
                    pdf.cell(col_w[6], 5, _pdf_safe(m["status"][:16]), border=1, align="C")
                    pdf.ln()
                pdf.ln(1)
    except Exception:
        pass

    return bytes(pdf.output())  # type: ignore[call-overload]


