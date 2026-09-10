"""ISA Form 20 (ISA-S20.50) Control Valve Specification Sheet generator.

Produces engineering procurement datasheets compliant with ISA-20,
IEC 60534, ASME B16.34, and ISO 15848-1 standards in Markdown and HTML/Excel formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ProcessConditionRow:
    """Operating condition metrics for a single operational state in ISA-20."""

    case_name: str
    flow: float
    flow_unit: str
    p1_bar_a: float
    p2_bar_a: float
    delta_p_bar: float
    temperature_c: float
    density_or_mw: float
    viscosity_cp: float
    calculated_cv: float
    opening_percent: float
    noise_dba: float | None
    velocity_m_s: float | None


@dataclass(frozen=True)
class ISA20Datasheet:
    """Universal ISA-20 Control Valve Specification Sheet."""

    tag_number: str
    service_description: str
    line_number: str
    pid_number: str
    date_iso: str
    service_type: str
    fluid_name: str
    valve_dn_mm: int
    valve_inch: str
    valve_style: str
    pressure_class: str
    end_connections: str
    body_material: str
    bonnet_type: str
    packing_type: str
    emission_standard: str
    trim_type: str
    trim_characteristic: str
    rated_cv: float
    leakage_class: str
    plug_material: str
    seat_material: str
    stem_material: str
    actuator_type: str
    actuator_model: str
    fail_action: str
    actuator_thrust_n: float
    air_supply_bar: float
    positioner: str
    cases: list[ProcessConditionRow] = field(default_factory=list)
    engineering_notes: list[str] = field(default_factory=list)


def build_isa20_datasheet(
    tag_number: str,
    service_description: str,
    line_number: str,
    pid_number: str,
    service_type: str,
    fluid_name: str,
    sizing_result: dict[str, Any],
    multicase_cases: list[dict[str, Any]] | None = None,
    vendor_key: str = "fisher_globe_eqpct",
    body_material: str = "WCB",
    bonnet_type: str = "Standard",
    end_connections: str = "Flanged ASME B16.5 RF",
    packing_guidance: Any = None,
) -> ISA20Datasheet:
    """Construct an ISA-20 datasheet data object from sizing results and metadata."""
    from vendor_catalog import get_vendor_definition

    vendor = get_vendor_definition(vendor_key)
    spec = sizing_result.get("valve_spec", {})
    act_sel = sizing_result.get("actuator_selection") or {}

    p_class = spec.get("pressure_class_recommended", "CL150")
    if "derated_mawp_bar" in spec:
        p_class = f"{p_class} (MAWP {spec['derated_mawp_bar']:.1f} bar)"

    leak_cls = spec.get("leakage_class_recommended", "IV")
    fail_safe = spec.get("fail_safe_recommended", "Fail-Closed")

    trim_notes = sizing_result.get("trim_guidance", [])
    severe_type = trim_notes[0] if trim_notes else "Standard Equal-Percentage"

    packing_name = packing_guidance.packing_type if packing_guidance else "Canl\u0131 Y\u00fcklemeli PTFE V-Halka"
    emiss_std = packing_guidance.emission_class if packing_guidance else "ISO 15848-1 Class BH / API 641"

    thrust_val = 0.0
    act_t = sizing_result.get("actuator_thrust_n")
    if isinstance(act_t, dict):
        thrust_val = float(act_t.get("total_n", 0.0))
    elif act_t is not None:
        thrust_val = float(act_t)

    act_model = act_sel.get("model", "Pn\u00f6matik Diyafram / Yay D\u00f6n\u00fc\u015fl\u00fc")

    case_rows: list[ProcessConditionRow] = []
    if multicase_cases:
        for c in multicase_cases:
            case_rows.append(
                ProcessConditionRow(
                    case_name=c.get("name", "Normal"),
                    flow=float(c.get("flow", 0.0)),
                    flow_unit=c.get("flow_unit", "m3/h"),
                    p1_bar_a=float(c.get("p1_bar_a", 0.0)),
                    p2_bar_a=float(c.get("p2_bar_a", 0.0)),
                    delta_p_bar=float(c.get("p1_bar_a", 0.0) - c.get("p2_bar_a", 0.0)),
                    temperature_c=float(c.get("temperature_c", 25.0)),
                    density_or_mw=float(c.get("density", 998.0)),
                    viscosity_cp=float(c.get("viscosity_cp", 1.0)),
                    calculated_cv=float(c.get("required_cv", sizing_result.get("required_cv", 0.0))),
                    opening_percent=float(c.get("opening_percent", sizing_result.get("opening_percent", 0.0))),
                    noise_dba=c.get("noise_dba"),
                    velocity_m_s=c.get("velocity_m_s"),
                )
            )
    else:
        vel = sizing_result.get("velocity", {})
        case_rows.append(
            ProcessConditionRow(
                case_name="Normal (Duty)",
                flow=float(sizing_result.get("extra", {}).get("flow", 100.0)),
                flow_unit="m3/h" if service_type.lower() == "liquid" else ("Nm3/h" if service_type.lower() == "gas" else "kg/h"),
                p1_bar_a=float(sizing_result.get("extra", {}).get("p1", 5.0)),
                p2_bar_a=float(sizing_result.get("extra", {}).get("p2", 3.0)),
                delta_p_bar=float(sizing_result.get("delta_p_bar", 2.0)),
                temperature_c=float(sizing_result.get("extra", {}).get("temperature_c", 25.0)),
                density_or_mw=float(sizing_result.get("extra", {}).get("density", 998.0)),
                viscosity_cp=float(sizing_result.get("extra", {}).get("viscosity_cp", 1.0)),
                calculated_cv=float(sizing_result.get("required_cv", 0.0)),
                opening_percent=float(sizing_result.get("opening_percent", 0.0)),
                noise_dba=sizing_result.get("noise_db"),
                velocity_m_s=vel.get("pipe_out_m_s"),
            )
        )

    notes = [
        "Vana boyutlandırması IEC 60534 ve ISA-75.01 standartlarına göre yapılmıştır.",
        "Basınç-sıcaklık (P-T) de-rating dayanımı ASME B16.34 standardına uygundur.",
        "Sit kaçak sınıfı ANSI FCI 70-2 / IEC 60534-4 uyarınca test edilecektir.",
    ]
    if packing_guidance and packing_guidance.nace_mr0175_compliant:
        notes.append("Ekşi gaz servisi için tüm ıslak parçalar NACE MR0175 / ISO 15156 standardına uygun olmalıdır.")

    if bonnet_type in ("Standard", "Standart"):
        from valve_selection import recommend_bonnet_type

        temp_val = float(sizing_result.get("extra", {}).get("temperature_c", 25.0))
        bonnet_type = recommend_bonnet_type(temp_val, service_type, fluid_name)

    vel_val = sizing_result.get("velocity", {}).get("pipe_out_m_s")
    dens_val = float(sizing_result.get("extra", {}).get("density", 1000.0))
    if vel_val:
        from safety_piping import check_erosional_velocity

        eros_check = check_erosional_velocity(float(vel_val), dens_val)
        if eros_check.is_velocity_exceeded:
            notes.append(
                f"API 14E Uyarısı: Boru hızı ({float(vel_val):.2f} m/s) erozyonel limiti "
                f"({eros_check.erosional_limit_m_s:.2f} m/s) aşıyor! Çıkış borusu genişletilmelidir."
            )

    rated_cv = float(sizing_result.get("rated_cv", 0.0))
    p1_val = float(sizing_result.get("extra", {}).get("p1", 5.0))
    p2_val = float(sizing_result.get("extra", {}).get("p2", 3.0))
    if rated_cv > 0:
        from safety_piping import calc_wide_open_relief_capacity

        relief_analysis = calc_wide_open_relief_capacity(
            service=service_type,
            rated_cv=rated_cv,
            inlet_pressure_bar_a=p1_val,
            relief_pressure_bar_a=p2_val * 1.1,
            fluid_data=sizing_result.get("extra", {}),
        )
        notes.append(
            f"API 520 Wide-Open Arıza Tahliye Kapasitesi (PSV Load): "
            f"{relief_analysis.wide_open_flow_rate:.1f} {relief_analysis.flow_unit}."
        )

    noise_db = sizing_result.get("noise_db")
    if noise_db and float(noise_db) > 85.0:
        from valve_noise import evaluate_noise_attenuation

        dp_val = float(sizing_result.get("delta_p_bar", 1.0))
        att = evaluate_noise_attenuation(float(noise_db), service_type, dp_val)
        notes.append(f"Akustik İyileştirme ({float(noise_db):.1f} dBA): {att.recommended_treatment}.")

    return ISA20Datasheet(
        tag_number=tag_number or "CV-101",
        service_description=service_description or "Proses Kontrol Vanas\u0131",
        line_number=line_number or "4\"-P-101-CS",
        pid_number=pid_number or "PID-001",
        date_iso=datetime.now(UTC).strftime("%Y-%m-%d"),
        service_type=service_type.upper(),
        fluid_name=fluid_name,
        valve_dn_mm=int(sizing_result.get("valve_dn_mm", 50)),
        valve_inch=str(sizing_result.get("valve_inch", '2"')),
        valve_style=vendor.style,
        pressure_class=p_class,
        end_connections=end_connections,
        body_material=body_material,
        bonnet_type=bonnet_type,
        packing_type=packing_name,
        emission_standard=emiss_std,
        trim_type=severe_type,
        trim_characteristic=sizing_result.get("valve_meta", {}).get("opening", "Equal Percentage"),
        rated_cv=float(sizing_result.get("rated_cv", 0.0)),
        leakage_class=f"Class {leak_cls}",
        plug_material="316SS + Stellite 6 Kaplama",
        seat_material="Stellite 6 / CoCr",
        stem_material="17-4PH / Inconel 718",
        actuator_type="Pn\u00f6matik Diyafram",
        actuator_model=act_model,
        fail_action=fail_safe,
        actuator_thrust_n=thrust_val,
        air_supply_bar=4.0,
        positioner="Ak\u0131ll\u0131 Pozisyoner (Smart HART 4-20 mA)",
        cases=case_rows,
        engineering_notes=notes,
    )


def generate_isa20_markdown(sheet: ISA20Datasheet) -> str:
    """Generate an ISA-20 datasheet formatted in Markdown."""
    lines = [
        f"# ISA-20 KONTROL VANASI VER\u0130 SAYFASI (DATASHEET) — {sheet.tag_number}",
        "",
        f"**Tarih:** {sheet.date_iso} | **Hizmet:** {sheet.service_description} | **Hat No:** {sheet.line_number} | **P&ID:** {sheet.pid_number}",
        "",
        "## 1. Genel Bilgiler",
        f"- **Tag No:** {sheet.tag_number}",
        f"- **Ak\u0131\u015fkan:** {sheet.fluid_name} ({sheet.service_type})",
        f"- **Vana \u00c7ap\u0131:** DN{sheet.valve_dn_mm} ({sheet.valve_inch})",
        f"- **G\u00f6vde Tipi:** {sheet.valve_style}",
        f"- **Bas\u0131n\u00e7 S\u0131n\u0131f\u0131 (Rating):** {sheet.pressure_class}",
        f"- **Ba\u011flant\u0131 Tipi:** {sheet.end_connections}",
        f"- **G\u00f6vde Malzemesi:** {sheet.body_material}",
        f"- **Bonnet Tipi:** {sheet.bonnet_type}",
        f"- **Salmastra Tipi:** {sheet.packing_type}",
        f"- **Ka\u00e7ak Emisyon Standard\u0131:** {sheet.emission_standard}",
        "",
        "## 2. Trim Bilgileri",
        f"- **Trim Tipi:** {sheet.trim_type}",
        f"- **Ak\u0131\u015f Karakteristi\u011fi:** {sheet.trim_characteristic}",
        f"- **Nominal Kapasite (Rated Cv):** {sheet.rated_cv:.1f}",
        f"- **Sit Ka\u00e7ak S\u0131n\u0131f\u0131:** {sheet.leakage_class}",
        f"- **Klape (Plug) Malzemesi:** {sheet.plug_material}",
        f"- **Sit Malzemesi:** {sheet.seat_material}",
        f"- **Mil (Stem) Malzemesi:** {sheet.stem_material}",
        "",
        "## 3. Akt\u00fcat\u00f6r ve Enstr\u00fcman",
        f"- **Akt\u00fcat\u00f6r Modeli:** {sheet.actuator_model}",
        f"- **Ar\u0131za Konumu (Fail Action):** {sheet.fail_action}",
        f"- **Gereken Kapatma Kuvveti:** {sheet.actuator_thrust_n:.1f} N",
        f"- **Hava Besleme Bas\u0131nc\u0131:** {sheet.air_supply_bar:.1f} bar(g)",
        f"- **Pozisyoner:** {sheet.positioner}",
        "",
        "## 4. \u00c7al\u0131\u015fma Ko\u015fullar\u0131 Tablosu (Process Operating Conditions)",
        "",
        "| Parametre | " + " | ".join(c.case_name for c in sheet.cases) + " |",
        "| :--- | " + " | ".join(":---:" for _ in sheet.cases) + " |",
        "| Debi | " + " | ".join(f"{c.flow:.1f} {c.flow_unit}" for c in sheet.cases) + " |",
        "| Giri\u015f Bas\u0131nc\u0131 P1 [bar(a)] | " + " | ".join(f"{c.p1_bar_a:.2f}" for c in sheet.cases) + " |",
        "| \u00c7\u0131k\u0131\u015f Bas\u0131nc\u0131 P2 [bar(a)] | " + " | ".join(f"{c.p2_bar_a:.2f}" for c in sheet.cases) + " |",
        "| Fark Bas\u0131n\u00e7 DeltaP [bar] | " + " | ".join(f"{c.delta_p_bar:.2f}" for c in sheet.cases) + " |",
        "| S\u0131cakl\u0131k [\u00b0C] | " + " | ".join(f"{c.temperature_c:.1f}" for c in sheet.cases) + " |",
        "| Hesaplanan Gerekli Cv | " + " | ".join(f"{c.calculated_cv:.2f}" for c in sheet.cases) + " |",
        "| Vana A\u00e7\u0131kl\u0131\u011f\u0131 | " + " | ".join(f"%{c.opening_percent:.1f}" for c in sheet.cases) + " |",
    ]
    if any(c.noise_dba is not None for c in sheet.cases):
        lines.append(
            "| G\u00fcr\u00fclt\u00fc dB(A) | " + " | ".join(f"{c.noise_dba:.1f}" if c.noise_dba else "-" for c in sheet.cases) + " |"
        )
    if any(c.velocity_m_s is not None for c in sheet.cases):
        vel_cells = " | ".join(f"{c.velocity_m_s:.2f}" if c.velocity_m_s else "-" for c in sheet.cases)
        lines.append(f"| Boru Çıkış Hızı [m/s] | {vel_cells} |")

    lines.extend(["", "## 5. M\u00fchendislik Notlar\u0131 ve Standartlar"])
    for n in sheet.engineering_notes:
        lines.append(f"- {n}")

    return "\n".join(lines) + "\n"


def generate_isa20_html(sheet: ISA20Datasheet) -> str:
    """Generate a cleanly styled HTML / Excel-compatible table for ISA-20 datasheet."""
    cases_th = "".join(f"<th style='border:1px solid #999;padding:6px;background:#f2f5f8;'>{c.case_name}</th>" for c in sheet.cases)
    flow_td = "".join(f"<td style='border:1px solid #999;padding:6px;text-align:center;'>{c.flow:.1f} {c.flow_unit}</td>" for c in sheet.cases)
    p1_td = "".join(f"<td style='border:1px solid #999;padding:6px;text-align:center;'>{c.p1_bar_a:.2f}</td>" for c in sheet.cases)
    p2_td = "".join(f"<td style='border:1px solid #999;padding:6px;text-align:center;'>{c.p2_bar_a:.2f}</td>" for c in sheet.cases)
    dp_td = "".join(f"<td style='border:1px solid #999;padding:6px;text-align:center;'>{c.delta_p_bar:.2f}</td>" for c in sheet.cases)
    t_td = "".join(f"<td style='border:1px solid #999;padding:6px;text-align:center;'>{c.temperature_c:.1f}</td>" for c in sheet.cases)
    cv_td = "".join(f"<td style='border:1px solid #999;padding:6px;text-align:center;'><b>{c.calculated_cv:.2f}</b></td>" for c in sheet.cases)
    open_td = "".join(f"<td style='border:1px solid #999;padding:6px;text-align:center;'><b>%{c.opening_percent:.1f}</b></td>" for c in sheet.cases)

    notes_html = "".join(f"<li>{n}</li>" for n in sheet.engineering_notes)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ISA-20 Datasheet - {sheet.tag_number}</title>
<style>
body {{ font-family: Arial, sans-serif; font-size: 13px; color: #333; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
th, td {{ border: 1px solid #bbb; padding: 6px 10px; }}
th {{ background-color: #12344d; color: white; text-align: left; }}
.section-title {{ background-color: #e2eaf0; font-weight: bold; color: #12344d; }}
</style>
</head>
<body>
<h2>ISA FORM 20 — KONTROL VANASI SPESİFİKASYON VERİ SAYFASI</h2>
<table>
  <tr><th colspan="4" style="background:#12344d;color:white;">PROJE VE GENEL BİLGİLER</th></tr>
  <tr><td><b>Vana Tag No:</b></td><td>{sheet.tag_number}</td><td><b>Tarih:</b></td><td>{sheet.date_iso}</td></tr>
  <tr>
    <td><b>Hizmet Tanımı:</b></td><td>{sheet.service_description}</td>
    <td><b>Akışkan:</b></td><td>{sheet.fluid_name} ({sheet.service_type})</td>
  </tr>
  <tr><td><b>Hat No:</b></td><td>{sheet.line_number}</td><td><b>P&ID No:</b></td><td>{sheet.pid_number}</td></tr>
</table>

<table>
  <tr><th colspan="4">VANA GÖVDE VE BAĞLANTI SPESİFİKASYONU</th></tr>
  <tr>
    <td><b>Anma Çapı:</b></td><td>DN{sheet.valve_dn_mm} ({sheet.valve_inch})</td>
    <td><b>Gövde Tipi:</b></td><td>{sheet.valve_style}</td>
  </tr>
  <tr>
    <td><b>Basınç Sınıfı:</b></td><td>{sheet.pressure_class}</td>
    <td><b>Bağlantı Tipi:</b></td><td>{sheet.end_connections}</td>
  </tr>
  <tr>
    <td><b>Gövde Malzemesi:</b></td><td>{sheet.body_material}</td>
    <td><b>Bonnet Tipi:</b></td><td>{sheet.bonnet_type}</td>
  </tr>
  <tr>
    <td><b>Salmastra:</b></td><td>{sheet.packing_type}</td>
    <td><b>Kaçak Standardı:</b></td><td>{sheet.emission_standard}</td>
  </tr>
</table>

<table>
  <tr><th colspan="4">TRİM VE SIZDIRMAZLIK SPESİFİKASYONU</th></tr>
  <tr>
    <td><b>Trim Tipi:</b></td><td>{sheet.trim_type}</td>
    <td><b>Akış Karakteristiği:</b></td><td>{sheet.trim_characteristic}</td>
  </tr>
  <tr>
    <td><b>Nominal Kapasite (Rated Cv):</b></td><td>{sheet.rated_cv:.1f}</td>
    <td><b>Sit Kaçak Sınıfı:</b></td><td>{sheet.leakage_class}</td>
  </tr>
  <tr>
    <td><b>Klape Malzemesi:</b></td><td>{sheet.plug_material}</td>
    <td><b>Sit Malzemesi:</b></td><td>{sheet.seat_material}</td>
  </tr>
  <tr><td><b>Mil Malzemesi:</b></td><td>{sheet.stem_material}</td><td><b>Test Standardı:</b></td><td>ANSI FCI 70-2 / IEC 60534-4</td></tr>
</table>

<table>
  <tr><th colspan="4">AKTÜATÖR VE POZİSYONER</th></tr>
  <tr>
    <td><b>Aktüatör Tipi:</b></td><td>{sheet.actuator_type}</td>
    <td><b>Aktüatör Modeli:</b></td><td>{sheet.actuator_model}</td>
  </tr>
  <tr>
    <td><b>Arıza Konumu:</b></td><td>{sheet.fail_action}</td>
    <td><b>Gereken Kuvvet:</b></td><td>{sheet.actuator_thrust_n:.1f} N</td>
  </tr>
  <tr><td><b>Hava Beslemesi:</b></td><td>{sheet.air_supply_bar:.1f} bar(g)</td><td><b>Pozisyoner:</b></td><td>{sheet.positioner}</td></tr>
</table>

<table>
  <tr><th colspan="{len(sheet.cases) + 1}">PROSES \u00c7ALI\u015eMA KO\u015eULLARI (PROCESS CONDITIONS)</th></tr>
  <tr><th>Parametre</th>{cases_th}</tr>
  <tr><td>Debi</td>{flow_td}</tr>
  <tr><td>Giri\u015f Bas\u0131nc\u0131 P1 [bar(a)]</td>{p1_td}</tr>
  <tr><td>\u00c7\u0131k\u0131\u015f Bas\u0131nc\u0131 P2 [bar(a)]</td>{p2_td}</tr>
  <tr><td>Fark Bas\u0131n\u00e7 DeltaP [bar]</td>{dp_td}</tr>
  <tr><td>S\u0131cakl\u0131k [\u00b0C]</td>{t_td}</tr>
  <tr><td>Hesaplanan Gerekli Cv</td>{cv_td}</tr>
  <tr><td>Vana A\u00e7\u0131kl\u0131\u011f\u0131 (%)</td>{open_td}</tr>
</table>

<h3>M\u00dcHEND\u0130SL\u0130K NOTLARI</h3>
<ul>
{notes_html}
</ul>
</body>
</html>
"""
    return html
