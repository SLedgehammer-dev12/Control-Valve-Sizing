"""Markdown report generation for control valve sizing results.

Produces a formatted report containing process data, calculated results,
selected valve details, method notes, and reference links."""

from __future__ import annotations

from datetime import UTC, datetime

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
    if thrust is not None:
        lines.extend(["", "## Actuator (est.)"])
        if isinstance(thrust, dict):
            lines.append(f"- Static unbalance thrust: {thrust.get('unbalance_n', 0.0):.1f} N")
            lines.append(f"- Shutoff thrust: {thrust.get('shutoff_n', 0.0):.1f} N")
            lines.append(f"- Packing friction: {thrust.get('packing_n', 0.0):.1f} N")
            lines.append(f"- Total estimated thrust: {thrust.get('total_n', 0.0):.1f} N")
        else:
            lines.append(f"- Total estimated thrust: {thrust:.1f} N")
        lines.append("- Note: estimate only; actuator sizing requires dynamic force and bench-set data.")

    if result.get("valve_spec"):
        spec = result["valve_spec"]
        lines.extend(["", "## Valve Specification (est.)"])
        lines.append(f"- Recommended ANSI class (P1-based): {spec.get('pressure_class_recommended', '-')}")
        lines.append(f"- Vendor body class: {spec.get('vendor_pressure_class', '-')}")
        lines.append(f"- Recommended seat leakage class: {spec.get('leakage_class_recommended', '-')}")
        lines.append(f"- Vendor seat leakage class: {spec.get('vendor_leakage_class', '-')}")
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
