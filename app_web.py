from __future__ import annotations

import math
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import DEFAULT_GAS_ROWS, GAS_PRESET_NAMES, GAS_PRESETS
from fluid_properties import (
    LIQUID_PRESETS,
    evaluate_gas_mixture,
    evaluate_liquid_preset,
    gas_component_options,
    get_pure_fluid_state,
    list_coolprop_fluids,
)
from project_io import dump_project_json, load_project_json
from reporting import build_report
from units import (
    GAS_FLOW_UNITS,
    LIQUID_FLOW_UNITS,
    PRESSURE_UNITS,
    STEAM_FLOW_UNITS,
    TEMPERATURE_UNITS,
    UNIT_KIND_LABELS,
    UNIT_MAPS,
    convert_unit,
    gas_flow_to_nm3h,
    liquid_flow_to_m3h,
    pressure_from_bar_a,
    pressure_to_bar_a,
    steam_flow_to_kgh,
    temperature_from_c,
    temperature_to_c,
)
from valve_curve import generate_characteristic_curve, generate_installed_characteristic
from valve_sizing import (
    SOURCE_LIBRARY,
    GasSizingInput,
    LiquidSizingInput,
    SizingResult,
    SteamSizingInput,
    size_gas_valve,
    size_liquid_valve,
    size_steam_valve,
    z_sensitivity_gas,
)
from vendor_catalog import get_vendor_definition, get_vendor_options

DEFAULTS = {
    "service": "Liquid",
    "vendor_key": "fisher_globe_eqpct",
    "liquid_source": "Preset",
    "liquid_preset_label": "Su",
    "_liquid_props_key": None,
    "liquid_temp_c": 25.0,
    "liquid_ref_pressure_bar_a": 1.01325,
    "liquid_density": 998.0,
    "liquid_pv": 0.023,
    "liquid_pc": 220.64,
    "liquid_mu": 0.00089,
    "liquid_flow_m3h": 25.0,
    "liquid_p1": 8.0,
    "liquid_p2": 5.0,
    "liquid_pipe_in_mm": 50.0,
    "liquid_pipe_out_mm": 50.0,
    "liquid_temp_unit": "°C",
    "liquid_pres_unit": "bar(a)",
    "liquid_flow_unit": "m³/h",
    "gas_basis": "molar",
    "gas_preset": "Doğal Gaz",
    "gas_model": "real",
    "gas_temp_c": 20.0,
    "gas_p1": 8.0,
    "gas_p2": 6.0,
    "gas_flow_nm3h": 800.0,
    "gas_pipe_in_mm": 80.0,
    "gas_pipe_out_mm": 80.0,
    "gas_temp_unit": "°C",
    "gas_pres_unit": "bar(a)",
    "gas_flow_unit": "Nm³/h",
    "steam_flow_kgh": 2500.0,
    "steam_temp_c": 220.0,
    "steam_p1": 12.0,
    "steam_p2": 8.0,
    "steam_temp_unit": "°C",
    "steam_pres_unit": "bar(a)",
    "steam_flow_unit": "kg/h",
    "design_margin": 15.0,
    "flow_characteristic": "equal_percentage",
}

SERVICE_LABELS = {"Liquid": "Sıvı", "Gas": "Gaz", "Steam": "Buhar"}
SERVICE_KEYS = {label: key for key, label in SERVICE_LABELS.items()}
SERVICE_TITLES = {"liquid": "Liquid", "gas": "Gas", "steam": "Steam"}
UNIT_STATE_MAPS = {
    "liquid": {"temp": TEMPERATURE_UNITS, "pres": PRESSURE_UNITS, "flow": LIQUID_FLOW_UNITS},
    "gas": {"temp": TEMPERATURE_UNITS, "pres": PRESSURE_UNITS, "flow": GAS_FLOW_UNITS},
    "steam": {"temp": TEMPERATURE_UNITS, "pres": PRESSURE_UNITS, "flow": STEAM_FLOW_UNITS},
}


def _unit_key(unit: str, unit_map: dict[str, str]) -> str:
    if unit in unit_map:
        return unit
    reverse = {label_value: key for key, label_value in unit_map.items()}
    return reverse[unit]


def _absolute_pressure_unit(unit: str) -> str:
    return {"bar_g": "bar_a", "psi_g": "psi_a"}.get(unit, unit)


def _convert_state_value(key: str, kind: str, previous: str, new: str, **context: float) -> None:
    value = st.session_state.get(key)
    if value is None:
        return
    try:
        st.session_state[key] = float(f"{convert_unit(kind, float(value), previous, new, **context):.6g}")
    except (TypeError, ValueError) as exc:
        st.warning(f"{key} birim donusumu yapilamadi: {exc}")


def _convert_state_units(prefix: str, kind: str, previous: str, new: str) -> None:
    if kind == "temp":
        _convert_state_value(f"{prefix}_temp_c", "temperature", previous, new)
        return
    if kind == "pres":
        _convert_state_value(f"{prefix}_p1", "pressure", previous, new)
        _convert_state_value(f"{prefix}_p2", "pressure", previous, new)
        if prefix == "liquid":
            old_unit = _absolute_pressure_unit(previous)
            new_unit = _absolute_pressure_unit(new)
            if old_unit != new_unit:
                _convert_state_value("liquid_pv", "pressure", old_unit, new_unit)
                _convert_state_value("liquid_pc", "pressure", old_unit, new_unit)
        return
    unit_kind = {"liquid": "liquid_flow", "gas": "gas_flow", "steam": "steam_flow"}[prefix]
    key = {"liquid": "liquid_flow_m3h", "gas": "gas_flow_nm3h", "steam": "steam_flow_kgh"}[prefix]
    context: dict[str, float] = {}
    if prefix == "liquid":
        context["density_kg_m3"] = float(st.session_state.get("liquid_density", 998.0))
    elif prefix == "gas" and ({"m3h", "kgh"} & {previous, new}):
        pres_unit = _unit_key(st.session_state.get("gas_pres_unit", "bar_a"), PRESSURE_UNITS)
        temp_unit = _unit_key(st.session_state.get("gas_temp_unit", "C"), TEMPERATURE_UNITS)
        pressure = pressure_to_bar_a(float(st.session_state.get("gas_p1", 1.0)), pres_unit)
        temperature = temperature_to_c(float(st.session_state.get("gas_temp_c", 15.0)), temp_unit)
        summary = st.session_state.get("gas_summary")
        z_factor = float(getattr(summary, "z", None) or 1.0)
        molecular_weight = float(getattr(summary, "average_molecular_weight", None) or 28.97) / 1000.0
        # shortcut: ideal-gas density with Z for kgh/m3h unit changes; upgrade to CoolProp density if composition accuracy matters.
        density = pressure * 1e5 * molecular_weight / (max(z_factor, 1e-6) * 8.314462618 * (temperature + 273.15))
        context.update(pressure_bar_a=pressure, temperature_c=temperature, z=z_factor, density_kg_m3=density)
    _convert_state_value(key, unit_kind, previous, new, **context)


def _unit_selectors(prefix: str, flow_units: dict[str, str]) -> tuple[str, str, str]:
    """Render temperature / pressure / flow unit selectors for a service."""
    u1, u2, u3 = st.columns(3)
    temp_label = u1.selectbox("Sicaklik birimi", options=list(TEMPERATURE_UNITS.values()), key=f"{prefix}_temp_unit")
    pres_label = u2.selectbox("Basinc birimi", options=list(PRESSURE_UNITS.values()), key=f"{prefix}_pres_unit")
    flow_label = u3.selectbox("Debi birimi", options=list(flow_units.values()), key=f"{prefix}_flow_unit")
    if _unit_key(pres_label, PRESSURE_UNITS).endswith("_g"):
        st.caption("Gauge basinc degerleri 1.01325 bar atmosfer basinciyla mutlak degere cevrilir.")
    current = {
        "temp": _unit_key(temp_label, TEMPERATURE_UNITS),
        "pres": _unit_key(pres_label, PRESSURE_UNITS),
        "flow": _unit_key(flow_label, flow_units),
    }
    for kind, unit in current.items():
        previous_key = f"_unit_prev_{prefix}_{kind}"
        previous = st.session_state.get(previous_key)
        if previous is not None and previous != unit:
            _convert_state_units(prefix, kind, previous, unit)
        st.session_state[previous_key] = unit
    return current["temp"], current["pres"], current["flow"]


def tooltip_label(label: str, help_text: str, key: str | None = None) -> None:
    """Render a label with an info tooltip icon."""
    import html
    safe_label = html.escape(label)
    safe_text = html.escape(help_text)
    key_attr = f' id="{key}"' if key else ""
    st.markdown(
        f'<div class="tooltip-container">'
        f'  <span class="help-label">{safe_label}</span>'
        f'  <button class="tooltip-btn"{key_attr} title="{safe_text}" aria-label="Yardım: {safe_text}">ⓘ</button>'
        f'  <div class="tooltip-content">{safe_text}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _live_render(service: str, result: SizingResult, fluid_summary: dict) -> None:
    """Persist and render a freshly computed result (live calculation)."""
    st.session_state.last_result = result
    st.session_state.last_fluid_summary = fluid_summary
    st.session_state.last_report = build_report(service, fluid_summary, result)

    # Sonucu gecmise ekle (tekrarlari atla, en son 3 benzersiz sonucu tut)
    entry = {
        "service": result["service"],
        "p1": round(float(result.get("p1", 0.0)), 3),
        "p2": round(float(result.get("p2", 0.0)), 3),
        "flow": round(float(result.get("flow", 0.0)), 3),
        "required_cv": float(result["required_cv"]),
        "rated_cv": float(result["rated_cv"]),
        "valve_dn_mm": int(result["valve_dn_mm"]),
        "valve_inch": str(result["valve_inch"]),
        "opening_percent": round(float(result["opening_percent"]), 1),
        "is_choked": bool(result["is_choked"]),
        "warning": str(result.get("warning", "")),
    }
    history = st.session_state.result_history
    if entry not in history:
        st.session_state.result_history = [entry, *history][:3]

    render_result(result)


def _init_state() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("gas_rows", DEFAULT_GAS_ROWS)
    st.session_state.setdefault("gas_valid", True)
    st.session_state.setdefault("last_result", None)
    st.session_state.setdefault("last_report", "")
    st.session_state.setdefault("last_fluid_summary", None)
    st.session_state.setdefault("result_history", [])


def _apply_pending_project_load() -> None:
    pending = st.session_state.pop("_pending_project_load", None)
    if not pending:
        return
    data = dict(pending.get("data", {}))
    for key, value in data.items():
        if key in {"service", "vendor_key"} or key.endswith("_unit"):
            continue
        st.session_state[key] = value
    if "vendor_key" in data:
        st.session_state.vendor_key = data["vendor_key"]
    service = str(pending.get("service") or data.get("service") or "liquid").lower()
    if service in SERVICE_TITLES:
        st.session_state.service = SERVICE_TITLES[service]
        st.session_state.service_slider = SERVICE_LABELS[SERVICE_TITLES[service]]
    for prefix, maps in UNIT_STATE_MAPS.items():
        for kind, unit_map in maps.items():
            key = f"{prefix}_{kind}_unit"
            unit_key = _unit_key(data.get(key, st.session_state.get(key, DEFAULTS[key])), unit_map)
            st.session_state[key] = unit_map[unit_key]
            st.session_state[f"_unit_prev_{prefix}_{kind}"] = unit_key
    st.session_state["_liquid_props_key"] = None
    st.session_state["_project_loaded"] = True


def _select_service(service: str) -> None:
    st.session_state.service = service
    st.session_state.service_slider = SERVICE_LABELS[service]


def _sync_service_from_slider() -> None:
    st.session_state.service = SERVICE_KEYS[st.session_state.service_slider]


def _vendor_meta(vendor_key: str) -> dict:
    definition = get_vendor_definition(vendor_key)
    return {
        "vendor": definition.vendor,
        "family": definition.family,
        "style": definition.style,
        "service": definition.service,
        "FL": definition.fl,
        "xT": definition.xt,
        "Fd": definition.fd,
        "opening": definition.opening_desc,
        "source": definition.source_note,
        "source_url": definition.source_url,
        "pressure_class": definition.pressure_class,
        "leakage_class": definition.leakage_class,
    }


@st.cache_data(show_spinner=False)
def _cv_margin_surface(
    required_cv: float,
    p1: float,
    p2: float,
    density: float,
    pv: float,
    pc: float,
    mu: float,
    fl: float,
    fd: float,
    pipe_in: float,
    pipe_out: float,
    characteristic: str,
) -> tuple[list[int], list[float], list[list[float]]]:
    """Compute the required-Cv margin surface once per unique input set."""
    openings = list(range(0, 101, 5))
    margins = [0.0, 0.1, 0.15, 0.2, 0.25, 0.3]
    z: list[list[float]] = []
    for margin_val in margins:
        row: list[float] = []
        for pct_val in openings:
            margin_factor = 1.0 + margin_val
            flow_factor = pct_val / 100.0
            try:
                r = size_liquid_valve(
                    LiquidSizingInput(
                        flow_m3h=float(required_cv) * margin_factor * max(0.1, flow_factor),
                        inlet_pressure_bar_a=p1,
                        outlet_pressure_bar_a=p2,
                        density_kg_m3=density,
                        vapor_pressure_bar_a=pv,
                        critical_pressure_bar_a=pc,
                        viscosity_pa_s=mu,
                        fl=fl,
                        fd=fd,
                        pipe_inlet_diameter_mm=pipe_in,
                        pipe_outlet_diameter_mm=pipe_out,
                    ),
                    valve_series=[],
                    valve_meta={},
                    design_margin_pct=margin_val,
                    flow_characteristic=characteristic,
                )
                row.append(float(r["required_cv"]))
            except Exception:
                row.append(float(required_cv))
        z.append(row)
    return openings, margins, z


def render_result(result: SizingResult) -> None:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Hesaplama Sonuçları")

    # Enhanced metrics display
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        tooltip_label("Gerekli Cv", "Gerekli debi ve basinc dusumune gore gereken vana kapasitesi (Cv).")
        st.markdown(f'<div class="metric-card"><h4>Gerekli Cv</h4><p>{result["required_cv"]:.3f}</p></div>', unsafe_allow_html=True)
    with col2:
        tooltip_label("Gerekli Kv", "Gerekli Cv'nin metrik birimdeki denkdugu deger (Kv = 0.865 x Cv).")
        st.markdown(f'<div class="metric-card"><h4>Gerekli Kv</h4><p>{result["required_kv"]:.3f}</p></div>', unsafe_allow_html=True)
    with col3:
        tooltip_label("Secilen Vana", "Tasarim margi dahil secilen vananin DN ve inc boyutu.")
        st.markdown(
            f'<div class="metric-card"><h4>Secilen Vana</h4>'
            f'<p>DN{result["valve_dn_mm"]} / {result["valve_inch"]}</p></div>',
            unsafe_allow_html=True,
        )
    with col4:
        tooltip_label("Rated Cv", "Secilen vananin rated (nominal) Cv degeri.")
        st.markdown(f'<div class="metric-card"><h4>Rated Cv</h4><p>{result["rated_cv"]:.3f}</p></div>', unsafe_allow_html=True)

    cv_fig = go.Figure(go.Bar(
        x=[result["required_cv"], result["rated_cv"]],
        y=["Gerekli Cv", "Rated Cv"],
        orientation="h",
        marker_color=["#2563eb", "#10b981"],
        text=[f'{result["required_cv"]:.3f}', f'{result["rated_cv"]:.3f}'],
        textposition="outside",
    ))
    cv_fig.add_vline(x=result["rated_cv"], line_dash="dash", line_color="#ef4444",
                     annotation_text="Rated Cv", annotation_position="top")
    cv_fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0),
                         xaxis_title="Cv", showlegend=False)
    st.plotly_chart(cv_fig, use_container_width=True)

    st.markdown("**Sonuç Özeti**")
    col_summary1, col_summary2 = st.columns(2)
    with col_summary1:
        tooltip_label("Basinc Dusu (Delta P)", "Giris ve cikis basinci arasindaki fark.")
        st.metric("Delta P [bar]", f"{result['delta_p_bar']:.3f}")
        tooltip_label("Choked (Kritik Akis)", "Delta P'nin kritik degeri (choked limit) uzerine ciktiysa akis kritik denir.")
        st.metric("Choked", "Yes" if result["is_choked"] else "No")
        tooltip_label("Opening %", "Vana aciligi yuzdesi. Ideal kontrol araligi %20-%80 arasindadir.")
        st.metric("Opening %", f"{result['opening_percent']:.1f}%")
        tooltip_label("Design Margin %", "Tasarim margisi. Gerekli Cv'nin uzerine eklenen guvenlik yuzdesi.")
        st.metric("Design Margin %", f"{result['design_margin_pct']:.1f}%")
    with col_summary2:
        tooltip_label("Cv Ratio", "Gerekli Cv'nin rated Cv'ye orani.")
        st.metric("Cv Ratio", f"{result['cv_ratio']:.3f}")
        pipe_out_vel = result.get("velocity", {}).get("pipe_out_m_s", None) if result.get("velocity") else None
        tooltip_label("Pipe Outlet Velocity", "Cikis boru hattindaki akis hizi. API 14E erozyon degerlendirmesinde kullanilir.")
        st.metric("Pipe Out Vel [m/s]", f"{pipe_out_vel:.2f}" if pipe_out_vel else "-")
        tooltip_label("Mach Outlet", "Cikis boru hattindaki Mach sayisi. Gaz/buhar icin kritik akis degerlendirmesinde kullanilir.")
        mach_outlet = result.get("velocity", {}).get("mach_outlet", None) if result.get("velocity") else None
        st.metric("Mach Outlet", f"{mach_outlet:.3f}" if mach_outlet else "-")

    est_cols = st.columns(2)
    with est_cols[0]:
        st.markdown("**Tahmini Gürültü (est.)**")
        if result.get("noise_db") is not None:
            st.metric("Valve noise", f"{result['noise_db']:.1f} dB(A)")
            st.caption("IEC 60534-8 tahmini; low-noise trim için vendor doğrulaması gerekir.")
            if float(result["noise_db"]) > 85.0:
                from valve_noise import evaluate_noise_attenuation

                dp_val = float(result.get("delta_p_bar", 1.0))
                att = evaluate_noise_attenuation(float(result["noise_db"]), result["service"], dp_val)
                st.warning(f"İş sağlığı sınırı (85 dBA) aşıldı! Öneri: {att.recommended_treatment}")
                with st.expander("Akustik İyileştirme Seçenekleri (IEC 60534-8-3)", expanded=False):
                    at1, at2 = st.columns(2)
                    at1.metric("Whisper Trim (-18 dBA)", f"{att.whisper_trim_dba:.1f} dB(A)")
                    at2.metric("Boru Ceketi (-10 dBA)", f"{att.acoustic_insulation_dba:.1f} dB(A)")
                    for n in att.engineering_notes:
                        st.caption(f"• {n}")
        else:
            st.write("-")
    with est_cols[1]:
        st.markdown("**Tahmini Aktüatör (est.)**")
        thrust = result.get("actuator_thrust_n")
        act_sel = result.get("actuator_selection")
        if act_sel and isinstance(act_sel, dict) and act_sel.get("model"):
            margin = act_sel.get("thrust_margin_pct", 0.0)
            st.metric("Model", f"{act_sel['model']} (+%{margin:.0f})")
            thrust_val = thrust.get("total_n", 0.0) if isinstance(thrust, dict) else (thrust or 0.0)
            stroke_status = "Yeterli" if act_sel.get("stroke_ok") else "Yetersiz"
            st.caption(f"Gereken kuvvet: {thrust_val:.0f} N | Strok: {stroke_status}")
        elif isinstance(thrust, dict):
            st.metric("Toplam kuvvet", f"{thrust.get('total_n', 0.0):.1f} N")
            st.caption("Statik tahmin; dinamik kuvvet ve bench-set için vendor doğrulaması gerekir.")
        elif thrust is not None:
            st.metric("Toplam kuvvet", f"{thrust:.1f} N")
        else:
            st.write("-")

    vel_info = result.get("velocity")
    if vel_info and vel_info.get("pipe_out_m_s"):
        from safety_piping import check_erosional_velocity

        v_val = float(vel_info["pipe_out_m_s"])
        d_val = float(result.get("extra", {}).get("density", 1000.0))
        eros_chk = check_erosional_velocity(v_val, d_val)
        if eros_chk.is_velocity_exceeded:
            st.error(
                f"API 14E Boru Erozyon Tehlikesi! Boru çıkış hızı {v_val:.2f} m/s, "
                f"izin verilen erozyonel limitin ({eros_chk.erosional_limit_m_s:.2f} m/s) üzerindedir!"
            )
            for w in eros_chk.warnings:
                st.caption(f"• {w}")

    with st.expander("Hesap metodu / kaynak", expanded=True):
        st.markdown("**Method Notes**")
        for item in result.get("method_panel", []):
            st.write(f"- {item}")
        st.markdown("**Equations**")
        for eq in result.get("equations", []):
            st.code(eq, language="text")
        st.markdown("**Sources**")
        for source in result.get("sources", []):
            st.write(f"- [{source['title']}]({source['url']})")
            st.caption(source["note"])

    with st.expander("Ara değerler", expanded=True):
        inter_df = pd.DataFrame(
            [
                {
                    "Parameter": str(k),
                    "Value": f"{v:.4f}" if isinstance(v, float) else str(v),
                }
                for k, v in result.get("intermediate_values", {}).items()
            ]
        )
        st.dataframe(inter_df, hide_index=True)

    with st.expander("Vendor verisi", expanded=False):
        meta = result.get("valve_meta", {})
        if meta:
            st.json(meta)

    trim_guidance = result.get("trim_guidance")
    if trim_guidance:
        with st.expander("Trim onerileri (est.)", expanded=True):
            for item in trim_guidance:
                st.write(f"- {item}")
            st.caption("Sezgisel yonlendirme; nihai trim secimi vendor dogrulamasi gerektirir.")

    spec = result.get("valve_spec")
    if spec:
        with st.expander("Vana spesifikasyonu (est.)", expanded=False):
            st.write(f"- Onerilen ANSI sinifi: {spec['pressure_class_recommended']}")
            if "derated_mawp_bar" in spec:
                t_sp = spec.get("temperature_c", 20.0)
                mat_grp = spec.get("material_group", "WCB")
                st.write(f"- ASME B16.34 MAWP (Derated): {spec['derated_mawp_bar']:.1f} bar @ {t_sp:.1f} °C ({mat_grp})")
            st.write(f"- Onerilen sizdirmazlik sinifi: {spec['leakage_class_recommended']}")
            if "allowable_leakage" in spec and isinstance(spec["allowable_leakage"], dict):
                al = spec["allowable_leakage"]
                st.write(f"- Izin verilen sizinti debisi: {al.get('max_rate', 0.0):.4f} {al.get('rate_unit', '')} ({al.get('note', '')})")
            st.write(f"- Onerilen fail-safe: {spec['fail_safe_recommended']}")

    char_type = st.session_state.get("flow_characteristic", "equal_percentage")
    curve = generate_characteristic_curve(
        rated_cv=float(result["rated_cv"]),
        required_cv=float(result["required_cv"]),
        characteristic=char_type,
    )
    with st.expander("Vana Karakteristik Eğrisi & Kontrol Analizi (IEC 60534-2-4)", expanded=True):
        tab_inh, tab_inst, tab_3d, tab_model = st.tabs([
            "Doğal (Inherent) Karakteristik",
            "Tesisat Kurulu (Installed) & Vana Otoritesi",
            "3D Karakteristik Eğrisi",
            "3D Vana Modeli",
        ])
        with tab_inh:
            op = curve.operating_point
            c_k1, c_k2, c_k3, c_k4 = st.columns(4)
            c_k1.metric("Çalışma Açıklığı", f"%{op.opening_pct:.1f}")
            c_k2.metric("Kontrol Bölgesi", op.controllability_zone)
            c_k3.metric("Kazanç dCv/dh", f"{op.point_gain:.2f}")
            c_k4.metric("Kapasite Oranı", f"%{op.relative_cv_pct:.1f}")

            if op.warnings:
                for w in op.warnings:
                    st.warning(f"⚠️ {w}")
            else:
                st.success("✅ Çalışma noktası ideal kontrol aralığında (%20 - %80 açıklık).")

            fig_inh = go.Figure()
            fig_inh.add_trace(go.Scatter(
                x=[pt.opening_pct for pt in curve.points],
                y=[pt.cv for pt in curve.points],
                mode="lines",
                name="Vana Cv (Eğri)",
                line=dict(color="#2563eb", width=2),
            ))
            fig_inh.add_trace(go.Scatter(
                x=[op.opening_pct],
                y=[op.required_cv],
                mode="markers",
                name="Çalışma Noktası",
                marker=dict(color="#ef4444", size=10, symbol="diamond"),
            ))
            fig_inh.add_vrect(x0=20.0, x1=80.0, line_width=0, fillcolor="#10b981", opacity=0.08)
            fig_inh.add_hline(y=op.required_cv, line_dash="dash", line_color="#10b981")
            fig_inh.update_layout(
                xaxis_title="Açıklık [%]",
                yaxis_title="Cv",
                height=320,
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_inh, use_container_width=True)

            with st.expander("Ayrık Karakteristik Tablosu (51 Nokta)", expanded=False):
                tbl_df = pd.DataFrame([p.to_dict() for p in curve.points])
                tbl_df.columns = ["Açıklık [%]", "Cv", "Kv", "Kazanç (dCv/dh)"]
                st.dataframe(tbl_df, hide_index=True)

        with tab_inst:
            st.caption("Boru hattı sürtünme kaybı ve pompa eğrisi nedeniyle vananın gerçek tesisattaki dinamik tepkisi (Installed Flow Response).")
            pr_val = st.slider(
                "Vana Otoritesi PR (ΔP_vana / ΔP_toplam, tam debide)",
                min_value=0.05,
                max_value=1.00,
                value=0.50,
                step=0.05,
                help="PR >= 0.50 ideal otoritedir. PR < 0.25 durumunda vana yetkisini kaybeder.",
                key=f"pr_slider_{result['service']}",
            )
            inst = generate_installed_characteristic(
                rated_cv=float(result["rated_cv"]),
                required_cv=float(result["required_cv"]),
                characteristic=char_type,
                valve_authority_pr=pr_val,
            )
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("Otorite Değerlendirmesi", inst.authority_assessment.split("(")[0].strip())
            i2.metric("Kazanç Oranı (Kmax/Kmin)", f"{inst.gain_ratio:.1f}:1")
            i3.metric("Doğrusallık Durumu", "Kararlı (<= 4:1)" if inst.is_gain_linear else "Doğrusal Değil (> 4:1)")
            i4.metric("Dinamik Kazanç dQ/dh", f"{inst.operating_installed_gain:.2f}")

            st.info(f"**Karakteristik Eğilimi:** {inst.distortion_trend}")

            if inst.warnings:
                for w in inst.warnings:
                    st.warning(f"⚠️ {w}")
            else:
                st.success("✅ Vana otoritesi yeterlidir; dinamik kazanç kontrol edilebilir sınırlar içerisindedir.")

            rated_val = float(result["rated_cv"])
            fig_inst = go.Figure()
            fig_inst.add_trace(go.Scatter(
                x=[p.opening_pct for p in inst.points],
                y=[p.installed_flow_pct for p in inst.points],
                mode="lines",
                name="Kurulu Debi Q [%]",
                line=dict(color="#2563eb", width=2),
            ))
            fig_inst.add_trace(go.Scatter(
                x=[p.opening_pct for p in inst.points],
                y=[(p.inherent_cv / rated_val * 100.0) if rated_val > 0 else 0.0 for p in inst.points],
                mode="lines",
                name="Doğal Cv [%]",
                line=dict(color="#94a3b8", width=1, dash="dot"),
            ))
            fig_inst.add_vrect(x0=20.0, x1=80.0, line_width=0, fillcolor="#10b981", opacity=0.08)
            op_pct_inst = min(float(result["opening_percent"]), 100.0)
            fig_inst.add_trace(go.Scatter(
                x=[op_pct_inst],
                y=[inst.operating_installed_flow_pct],
                mode="markers",
                name="Çalışma Noktası",
                marker=dict(color="#ef4444", size=10, symbol="diamond"),
            ))
            fig_inst.update_layout(
                xaxis_title="Açıklık [%]",
                yaxis_title="%",
                height=320,
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_inst, use_container_width=True)

            with st.expander("Ayrık Tesisat Tablosu (51 Nokta)", expanded=False):
                inst_tbl_df = pd.DataFrame([p.to_dict() for p in inst.points])
                inst_tbl_df.columns = ["Açıklık [%]", "Inherent Cv", "Kurulu Debi Q [%]", "Dinamik Kazanç (dQ/dh)", "Vana dP Oranı"]
                st.dataframe(inst_tbl_df, hide_index=True)

        with tab_3d:
            st.markdown("### 3D Vana Karakteristik Eğrisi")
            st.markdown("Bu 3D yüzey, vananın açıklık ve tasarım marjına göre gerekli Cv değerlerinin değişimini gösterir.")

            openings, margins, z_matrix = _cv_margin_surface(
                float(result["required_cv"]),
                float(result.get("p1", 8.0)),
                float(result.get("p2", 5.0)),
                float(result.get("extra", {}).get("density", 998.0)),
                float(result.get("extra", {}).get("vapor_pressure_bar_a", 0.023)),
                float(result.get("extra", {}).get("critical_pressure_bar_a", 220.64)),
                float(result.get("extra", {}).get("viscosity_pa_s", 0.00089)),
                float(result.get("extra", {}).get("fl", 0.85)),
                float(result.get("extra", {}).get("fd", 1.0)),
                float(result.get("extra", {}).get("pipe_inlet_diameter_mm", 50.0)),
                float(result.get("extra", {}).get("pipe_outlet_diameter_mm", 50.0)),
                char_type,
            )

            fig_3d = go.Figure(data=[go.Surface(
                z=z_matrix,
                x=openings,
                y=[f"{m*100:.0f}%" for m in margins],
                colorscale="Viridis",
                colorbar=dict(title="Gerekli Cv"),
            )])

            fig_3d.update_layout(
                title="Gerekli Cv - Açıklık vs Tasarım Marjı 3D Yüzeyi",
                scene=dict(
                    xaxis_title="Açıklık [%]",
                    yaxis_title="Tasarım Marjı [%]",
                    zaxis_title="Gerekli Cv",
                ),
                height=600,
                margin=dict(l=0, r=0, t=40, b=0),
            )

            st.plotly_chart(fig_3d, use_container_width=True)

            st.caption("3D yüzey, vananın açıklık ve tasarım marjına bağlı olarak gerekli Cv değerlerinin nasıl değiştiğini gösterir.")

        with tab_model:
            from valve_3d import build_valve_figure

            st.caption("Seçilen vana boyutuna (DN) göre parametrik gövde, flanş, bonnet, mil ve el çarkı modeli (sematik).")
            st.plotly_chart(build_valve_figure(float(result["valve_dn_mm"])), use_container_width=True)

    with st.expander("3D Tesisat Karakteristigi (Vana Otoritesi Etkisi)", expanded=False):
        from valve_curve import calc_installed_flow_ratio, cv_at_opening

        char_3d = st.session_state.get("flow_characteristic", "equal_percentage")
        rated_3d = float(result["rated_cv"])
        if rated_3d <= 0:
            st.write("-")
        else:
            openings = list(range(0, 101, 5))
            authorities = [round(0.05 + 0.05 * i, 2) for i in range(20)]
            surface = [
                [calc_installed_flow_ratio(cv_at_opening(float(pct), rated_3d, char_3d) / rated_3d, pr) * 100.0 for pct in openings]
                for pr in authorities
            ]
            fig3d = go.Figure(go.Surface(x=openings, y=authorities, z=surface, colorscale="Viridis",
                                         colorbar={"title": "Q/Qmax [%]"}))
            op_pr = float(st.session_state.get(f"pr_slider_{result['service']}", 0.5))
            op_pct = min(float(result["opening_percent"]), 100.0)
            op_flow = calc_installed_flow_ratio(cv_at_opening(op_pct, rated_3d, char_3d) / rated_3d, op_pr) * 100.0
            fig3d.add_trace(go.Scatter3d(x=[op_pct], y=[op_pr], z=[op_flow], mode="markers",
                                         marker={"size": 5, "color": "red"}, name="Calisma noktasi"))
            fig3d.update_layout(
                scene={"xaxis_title": "Aciklik [%]", "yaxis_title": "Vana Otoritesi PR",
                       "zaxis_title": "Kurulu Debi Q/Qmax [%]"},
                margin={"l": 0, "r": 0, "t": 10, "b": 0}, height=480,
            )
            st.plotly_chart(fig3d, use_container_width=True)
            st.caption("Yuzey, vana otoritesi PR degistikce kurulu debi karakteristiginin nasil bozuldugunu gosterir (IEC 60534-2-4).")

    if result.get("warning"):
        st.warning(result["warning"])

    # Önceki hesaplamalar (karşılaştırma için)
    history = st.session_state.get("result_history", [])
    if len(history) > 1:
        with st.expander("Önceki Hesaplamalar (Karşılaştırma)", expanded=False):
            cmp_df = pd.DataFrame([
                {
                    "#": i + 1,
                    "Servis": h["service"],
                    "P1": h.get("p1", "-"),
                    "P2": h.get("p2", "-"),
                    "Debi": h.get("flow", "-"),
                    "Durum": "🔴 Boğulmuş" if h["is_choked"] else "🟢 Normal",
                    "Gerekli Cv": round(h["required_cv"], 3),
                    "Rated Cv": round(h["rated_cv"], 3),
                    "Vana": f"DN{h['valve_dn_mm']} / {h['valve_inch']}",
                    "Açıklık %": round(h["opening_percent"], 1),
                    "Uyarı": h["warning"] if h["warning"] else "",
                }
                for i, h in enumerate(history)
            ])
            st.dataframe(cmp_df, hide_index=True, use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)


def render_project_tools(service: str, payload: dict) -> None:
    with st.sidebar.expander("Proje Kaydet / Yukle", expanded=False):
        project_json = dump_project_json(service, payload)
        st.download_button(
            "Projeyi JSON olarak indir",
            project_json,
            file_name="control_valve_sizing_project.json",
            mime="application/json",
        )
        if st.session_state.pop("_project_loaded", False):
            st.sidebar.success("Proje yuklendi.")
        uploaded = st.file_uploader("Proje JSON yukle", type=["json"])
        if uploaded is not None:
            upload_id = getattr(uploaded, "file_id", None) or f"{uploaded.name}:{uploaded.size}"
            if st.session_state.get("_project_upload_id") != upload_id:
                st.session_state["_project_upload_id"] = upload_id
                try:
                    st.session_state["_pending_project_load"] = load_project_json(uploaded.getvalue().decode("utf-8"))
                    st.rerun()
                except Exception as exc:
                    st.sidebar.error(f"Yukleme hatasi: {exc}")


def render_report_tools() -> None:
    if st.session_state.last_report:
        st.sidebar.download_button(
            "Raporu indir (MD)",
            st.session_state.last_report,
            file_name="control_valve_sizing_report.md",
            mime="text/markdown",
        )
        if st.session_state.last_result:
            from reporting import build_pdf_report

            pdf_bytes = bytes(
                build_pdf_report(
                    st.session_state.last_result["service"],
                    st.session_state.last_fluid_summary or {},
                    st.session_state.last_result,
                )
            )
            st.sidebar.download_button(
                "Raporu indir (PDF)",
                pdf_bytes,
                file_name="control_valve_sizing_report.pdf",
                mime="application/pdf",
            )
    if st.session_state.last_result:
        from reporting import build_isa20_html_report, build_isa20_report

        res = st.session_state.last_result
        fluid = (
            st.session_state.get("liquid_preset_label", "Su")
            if res["service"] == "liquid"
            else ("Doğal Gaz" if res["service"] == "gas" else "Buhar")
        )
        mc_cases = (
            st.session_state.last_multicase.to_isa20_process_cases()
            if getattr(st.session_state, "last_multicase", None)
            else None
        )
        isa_md = build_isa20_report(res, tag="CV-101", fluid_name=fluid, multicase_cases=mc_cases)
        isa_html = build_isa20_html_report(res, tag="CV-101", fluid_name=fluid, multicase_cases=mc_cases)
        st.sidebar.download_button(
            "ISA-20 Datasheet (HTML / Excel)",
            isa_html,
            file_name="isa20_control_valve_datasheet.html",
            mime="text/html",
        )
        st.sidebar.download_button(
            "ISA-20 Datasheet (Markdown)",
            isa_md,
            file_name="isa20_control_valve_datasheet.md",
            mime="text/markdown",
        )



def render_source_library() -> None:
    with st.sidebar.expander("Kaynak Kutuphanesi", expanded=False):
        for source in SOURCE_LIBRARY.values():
            st.write(f"- [{source['title']}]({source['url']})")
            st.caption(source["note"])


def render_unit_converter() -> None:
    """Sidebar converter backed by the centralized units module."""
    with st.sidebar.expander("Birim Dönüştürücü", expanded=False):
        kind_label = st.selectbox("Dönüştürücü türü", list(UNIT_KIND_LABELS.values()), key="conv_kind")
        kind = next(k for k, v in UNIT_KIND_LABELS.items() if v == kind_label)
        units = UNIT_MAPS[kind]
        labels = list(units.values())
        c1, c2 = st.columns(2)
        from_label = c1.selectbox("Kaynak birim", labels, key=f"conv_from_{kind}")
        to_label = c2.selectbox("Hedef birim", labels, index=1, key=f"conv_to_{kind}")
        value = st.number_input("Dönüştürülecek değer", value=1.0, key=f"conv_value_{kind}")
        kwargs: dict[str, float] = {}
        if kind in {"liquid_flow", "gas_flow"}:
            kwargs["density_kg_m3"] = st.number_input(
                "Yoğunluk [kg/m³]", value=998.0 if kind == "liquid_flow" else 1.2, key=f"conv_density_{kind}"
            )
        if kind == "gas_flow":
            kwargs["pressure_bar_a"] = st.number_input("Basınç [bar(a)]", value=1.01325, key=f"conv_p_{kind}")
            kwargs["temperature_c"] = st.number_input("Sıcaklık [°C]", value=15.0, key=f"conv_t_{kind}")
            kwargs["z"] = st.number_input("Sıkıştırılabilirlik Z", value=1.0, key=f"conv_z_{kind}")
        try:
            result = convert_unit(
                kind,
                float(value),
                next(k for k, v in units.items() if v == from_label),
                next(k for k, v in units.items() if v == to_label),
                **kwargs,
            )
        except (ValueError, StopIteration) as exc:
            st.error(str(exc))
        else:
            st.metric("Sonuç", f"{result:.6g} {to_label}")


def render_liquid_section(vendor_key: str) -> tuple[dict | None, dict]:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Sivi Akiskan")
    source = st.selectbox("Akiskan tanimi", ["Preset", "CoolProp pure fluid", "Custom"], key="liquid_source")
    temp_unit, pres_unit, flow_unit = _unit_selectors("liquid", LIQUID_FLOW_UNITS)
    temp_label = TEMPERATURE_UNITS[temp_unit]
    pres_label = PRESSURE_UNITS[pres_unit]
    pv_unit = _absolute_pressure_unit(pres_unit)
    pv_label = PRESSURE_UNITS[pv_unit]
    flow_label = LIQUID_FLOW_UNITS[flow_unit]

    # Fluid Properties Section
    with st.expander("Akiskan Ozellikleri", expanded=True):
        c1, c2 = st.columns(2)
        tooltip_label("Sicaklik", "Akiskan giris sicakligi. Viscosity, density ve cavitasyon hesaplamalarinda kullanilir.")
        temperature_c = temperature_to_c(c1.number_input(f"Sicaklik [{temp_label}]", key="liquid_temp_c", step=1.0), temp_unit)
        tooltip_label("Giris Basinci (P1)", "Vana giris mutlak basinci. Kavitasyon ve choked flow hesaplamalarinda kullanilir.")
        inlet_pressure = pressure_to_bar_a(
            c2.number_input(f"Giris P [{pres_label}]", key="liquid_p1", min_value=0.001, step=0.1), pres_unit
        )

        density_default = st.session_state.liquid_density
        pv_default = st.session_state.liquid_pv
        pc_default = st.session_state.liquid_pc
        mu_default = st.session_state.liquid_mu
        pv_display_default = float(st.session_state.liquid_pv)
        pc_display_default = float(st.session_state.liquid_pc)
        fluid_label: str = "Custom liquid"
        auto_key = None

        if source == "Preset":
            preset_map = {v["label"]: k for k, v in LIQUID_PRESETS.items()}
            label = st.selectbox("Preset", list(preset_map.keys()), key="liquid_preset_label")
            preset = evaluate_liquid_preset(preset_map[label], inlet_pressure, temperature_c)
            if preset.get("warning"):
                st.warning(preset["warning"])
            density_default = preset["density_kg_m3"]
            pv_default = preset["vapor_pressure_bar_a"]
            pc_default = preset["critical_pressure_bar_a"]
            mu_default = preset["viscosity_pa_s"]
            pv_display_default = pressure_from_bar_a(pv_default, pv_unit)
            pc_display_default = pressure_from_bar_a(pc_default, pv_unit)
            fluid_label = str(label)
            auto_key = ("Preset", fluid_label, pres_unit, round(inlet_pressure, 6), round(temperature_c, 6))
        elif source == "CoolProp pure fluid":
            fluid = st.selectbox("CoolProp fluid", list_coolprop_fluids(), index=list_coolprop_fluids().index("Water"))
            fluid_label = fluid
            try:
                props = get_pure_fluid_state(fluid, inlet_pressure, temperature_c)
                density_default = props["density_kg_m3"]
                pv_default = props["vapor_pressure_bar_a"]
                pc_default = props["critical_pressure_bar_a"]
                mu_default = props["viscosity_pa_s"]
                pv_display_default = pressure_from_bar_a(pv_default, pv_unit)
                pc_display_default = pressure_from_bar_a(pc_default, pv_unit)
                auto_key = ("CoolProp", fluid, pres_unit, round(inlet_pressure, 6), round(temperature_c, 6))
                st.caption(
                    f"Oto ozellikler: rho={density_default:.2f} kg/m3, Pv={pressure_from_bar_a(pv_default, pv_unit):.4f} {pv_label}, "
                    f"Pc={pressure_from_bar_a(pc_default, pv_unit):.3f} {pv_label}, mu={mu_default:.6g} Pa.s"
                )
            except Exception as exc:
                st.warning(f"CoolProp ozellikleri okunamadi: {exc}")

        if auto_key and st.session_state.get("_liquid_props_key") != auto_key:
            st.session_state["liquid_density"] = float(density_default)
            st.session_state["liquid_pv"] = float(pv_display_default)
            st.session_state["liquid_pc"] = float(pc_display_default)
            st.session_state["liquid_mu"] = float(mu_default)
            st.session_state["_liquid_props_key"] = auto_key
        elif not auto_key:
            st.session_state["_liquid_props_key"] = None

        c3, c4, c5, c6 = st.columns(4)
        tooltip_label("Yogunluk", "Akiskan yo gunlugu. Mass flow'dan hacimsel debi hesaplamada kullanilir.")
        density = c3.number_input("Yogunluk [kg/m3]", value=float(density_default), key="liquid_density", min_value=0.001, step=1.0)
        tooltip_label("Buhar Basinci", "Akiskan o anki sicakliktaki buhar basinci. Kavitasyon ve flashing riski hesaplamada kullanilir.")
        vapor_pressure = pressure_to_bar_a(
            c4.number_input(f"Buhar basinci [{pv_label}]", value=pv_display_default, key="liquid_pv", min_value=0.0, step=0.01), pv_unit
        )
        tooltip_label("Kritik Basinci", "Akiskan kritik noktasindaki basinc. Critical properties hesaplamada kullanilir.")
        critical_pressure = pressure_to_bar_a(
            c5.number_input(f"Kritik basinc [{pv_label}]", value=pc_display_default, key="liquid_pc", min_value=0.001, step=0.1), pv_unit
        )
        tooltip_label("Viskozite", "Akismanin ici surukleme katsayisi. Reynolds sayisi ve laminar akis kontrolunde kullanilir.")
        viscosity = c6.number_input("Viskozite [Pa.s]", value=float(mu_default), key="liquid_mu", min_value=1e-7, step=0.0001, format="%.7f")

    # Process Data Section
    st.markdown("**Proses Verileri**")
    p2, q, d1, d2 = st.columns(4)
    tooltip_label("Debi", "Hacimsel debi. Gerekli Cv hesaplamanin temel parametresidir.")
    flow_value = q.number_input(f"Debi [{flow_label}]", key="liquid_flow_m3h", min_value=0.0001, step=1.0)
    flow_m3h = liquid_flow_to_m3h(flow_value, flow_unit, density_kg_m3=density)
    tooltip_label("Cikis Basinci (P2)", "Vana cikis mutlak basinci. Delta P ve choked flow hesaplamada kullanilir.")
    outlet_pressure = pressure_to_bar_a(
        p2.number_input(f"Cikis P [{pres_label}]", key="liquid_p2", min_value=0.001, step=0.1), pres_unit
    )
    tooltip_label("Hat Giris Capi", "Vana giris boru capi. Reducer etkisi (FP) hesaplamada kullanilir.")
    pipe_in_mm = d1.number_input("Hat giris capi [mm]", key="liquid_pipe_in_mm", min_value=1.0, step=1.0)
    tooltip_label("Hat Cikis Capi", "Vana cikis boru capi. Erozion hizi hesaplamada kullanilir.")
    pipe_out_mm = d2.number_input("Hat cikis capi [mm]", key="liquid_pipe_out_mm", min_value=1.0, step=1.0)

    vendor = get_vendor_definition(vendor_key)
    st.caption(f"Vendor representative data: {vendor.vendor} / {vendor.style}, FL={vendor.fl}, Fd={vendor.fd}")
    tooltip_label("FL (Liquid Pressure Recovery Factor)", "Vana basinc dususunu kacar mape ceviren faktor. "
        "Tipik deger 0.85-0.95 globul vanalar icin. Dusuk FL daha fazla cavitasyon riski nerede.")
    tooltip_label("Fd (Valve Style Modifier)", "Vana stilligi duzeltme katsayisi. Globe vanalar icin "
        "1.0 dir.")

    fluid_summary = {
        "Fluid": fluid_label,
        f"Temperature [{temp_label}]": f"{temperature_from_c(temperature_c, temp_unit):.3f}",
        "Density [kg/m3]": f"{density:.4f}",
        f"Pv [{pv_label}]": f"{pressure_from_bar_a(vapor_pressure, pv_unit):.5f}",
        f"Pc [{pv_label}]": f"{pressure_from_bar_a(critical_pressure, pv_unit):.5f}",
        "Viscosity [Pa.s]": f"{viscosity:.7g}",
    }

    try:
        result = size_liquid_valve(
            LiquidSizingInput(
                flow_m3h=flow_m3h,
                inlet_pressure_bar_a=inlet_pressure,
                outlet_pressure_bar_a=outlet_pressure,
                density_kg_m3=density,
                vapor_pressure_bar_a=vapor_pressure,
                critical_pressure_bar_a=critical_pressure,
                viscosity_pa_s=viscosity,
                fl=vendor.fl or 0.9,
                fd=vendor.fd or 1.0,
                pipe_inlet_diameter_mm=pipe_in_mm,
                pipe_outlet_diameter_mm=pipe_out_mm,
            ),
            valve_series=list(vendor.sizes),
            valve_meta=_vendor_meta(vendor_key),
            design_margin_pct=st.session_state.design_margin,
            flow_characteristic=st.session_state.flow_characteristic,
        )
        _live_render("Liquid", result, fluid_summary)
        sigma_val = result.get("cavitation_index") if result else None
        if sigma_val is not None:
            from trim_guidance import evaluate_cavitation_severity

            cav_res = evaluate_cavitation_severity(
                sigma=float(sigma_val),
                delta_p_bar=inlet_pressure - outlet_pressure,
                p1_bar_a=inlet_pressure,
                pv_bar_a=vapor_pressure,
            )
            with st.expander("Kavitasyon & Ağır Hizmet Trim Analizi (ISA-RP75.23)", expanded=False):
                c_c1, c_c2, c_c3 = st.columns(3)
                c_c1.metric("Kavitasyon İndeksi (σ)", f"{cav_res.sigma:.3f}")
                c_c2.metric("Şiddet Seviyesi", cav_res.severity_level)
                c_c3.metric("Önerilen Kademe", f"{cav_res.stages_recommended} Kademe")
                st.info(f"**Önerilen Trim:** {cav_res.trim_recommendation}")
                if cav_res.stages_recommended > 1:
                    st.markdown(f"**Kademe Başına Maks İzin Verilen ΔP:** {cav_res.max_allowable_dp_per_stage_bar:.1f} bar")
                for w in cav_res.warnings:
                    st.warning(w)
                for n in cav_res.engineering_notes:
                    st.caption(f"• {n}")
    except Exception as exc:
        st.error(f"Sivi sizing hesaplamasi yapilirken hata olustu: {exc}")
        st.session_state.last_result = None

    st.markdown('</div>', unsafe_allow_html=True)
    valid = st.session_state.last_result and st.session_state.last_result["service"] == "liquid"
    return (st.session_state.last_result if valid else None), fluid_summary


def _gas_component_options() -> list[str]:
    return gas_component_options()


def validate_gas_composition():
    total_pct = 0.0
    gas_options = set(_gas_component_options())
    valid = True
    for row in st.session_state.gas_rows:
        component = str(row.get("component", "")).strip()
        fraction = row.get("fraction_pct", 0)
        try:
            fraction = float(fraction)
        except (TypeError, ValueError):
            valid = False
            continue
        if component not in gas_options or fraction < 0.0 or not math.isfinite(fraction):
            valid = False
        total_pct += fraction
    if not math.isfinite(total_pct) or abs(total_pct - 100.0) > 1e-6:
        valid = False
    st.session_state.gas_valid = valid


def render_gas_section(vendor_key: str) -> tuple[dict | None, dict | None]:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Gaz Akiskan ve Kompozisyon")
    temp_unit, pres_unit, flow_unit = _unit_selectors("gas", GAS_FLOW_UNITS)
    temp_label = TEMPERATURE_UNITS[temp_unit]
    pres_label = PRESSURE_UNITS[pres_unit]
    flow_label = GAS_FLOW_UNITS[flow_unit]
    # Gas Process Data Section
    with st.expander("Gaz Ozellikleri", expanded=True):
        gas_model = st.selectbox(
            "Gaz modeli",
            options=["real", "auto", "ideal"],
            format_func=lambda value: {"real": "Gerçek gaz (HEOS)", "auto": "Gerçek gaz (mümkünse)", "ideal": "İdeal gaz"}[value],
            key="gas_model",
        )
        c1, c2, c3, c4 = st.columns(4)
        basis = c1.radio("Kompozisyon bazisi", ["molar", "mass"], key="gas_basis", horizontal=True)
        tooltip_label("Sicaklik", "Gaz akiskan giris sicakligi. Z faktoru ve density hesaplamada kullanilir.")
        temperature_c = temperature_to_c(c2.number_input(f"Sicaklik [{temp_label}]", key="gas_temp_c", step=1.0), temp_unit)
        tooltip_label("Giris Basinci (P1)", "Gaz giris mutlak basinci. Choked flow ve density hesaplamada kullanilir.")
        inlet_pressure = pressure_to_bar_a(
            c3.number_input(f"Giris P [{pres_label}]", key="gas_p1", min_value=0.001, step=0.1), pres_unit
        )
        tooltip_label("Cikis Basinci (P2)", "Gaz cikis mutlak basinci. Delta P ve choked kontrolunde kullanilir.")
        outlet_pressure = pressure_to_bar_a(
            c4.number_input(f"Cikis P [{pres_label}]", key="gas_p2", min_value=0.001, step=0.1), pres_unit
        )
        tooltip_label("Debi", "Gaz hacimsel debi (nm3h). Gerekli Cv hesaplamanin temel parametresidir.")
        flow_value = st.number_input(f"Debi [{flow_label}]", key="gas_flow_nm3h", min_value=0.0001, step=10.0)

    # Gas Composition Section
    with st.expander("Gaz Kompozisyonu", expanded=True):
        gas_options = _gas_component_options()
        gas_preset_options = GAS_PRESET_NAMES + ["Özel (Custom)"]
        def _on_gas_preset_change() -> None:
            name = st.session_state.get("gas_preset", "")
            if name in GAS_PRESETS:
                st.session_state.gas_rows = [dict(r) for r in GAS_PRESETS[name]["components"]]
                st.session_state["_gas_editor_version"] = st.session_state.get("_gas_editor_version", 0) + 1
                validate_gas_composition()

        st.selectbox("Gaz preset", gas_preset_options, key="gas_preset", on_change=_on_gas_preset_change)
        gas_df = pd.DataFrame(st.session_state.gas_rows)
        edited = st.data_editor(
            gas_df,
            num_rows="dynamic",
            column_config={
                "component": st.column_config.SelectboxColumn("Bilesen", options=gas_options, required=True),
                "fraction_pct": st.column_config.NumberColumn("Yuzde [%]", min_value=0.0, max_value=100.0, step=0.1, format="%.4f"),
            },
            key=f"gas_editor_{st.session_state.get('gas_preset', '')}_{st.session_state.get('_gas_editor_version', 0)}",
        )
        st.session_state.gas_rows = edited.to_dict("records")
        validate_gas_composition()

        # Real-time validation display
        total_pct = float(edited["fraction_pct"].fillna(0.0).sum()) if "fraction_pct" in edited else 0.0
        if abs(total_pct - 100.0) < 1e-6:
            st.markdown(f'<p class="success-msg">Toplam kompozisyon: {total_pct:.4f}%</p>', unsafe_allow_html=True)
        elif total_pct > 0.0 and math.isfinite(total_pct):
            st.markdown(
                f'<p class="error-msg">Toplam kompozisyon %{total_pct:.3f}; 100% için normalize edilebilir.</p>',
                unsafe_allow_html=True,
            )
            if st.button("100'e normalize et", key="gas_normalize"):
                normalized = [
                    {"component": row["component"], "fraction_pct": float(row["fraction_pct"]) / total_pct * 100.0}
                    for row in st.session_state.gas_rows
                    if float(row["fraction_pct"]) > 0.0
                ]
                st.session_state.gas_rows = normalized
                st.session_state["_gas_editor_version"] = st.session_state.get("_gas_editor_version", 0) + 1
                validate_gas_composition()
                st.rerun()
        else:
            st.markdown('<p class="error-msg">Toplam kompozisyon sıfırdan büyük olmalı.</p>', unsafe_allow_html=True)

    vendor = get_vendor_definition(vendor_key)
    st.caption(f"Vendor representative data: {vendor.vendor} / {vendor.style}, xT={vendor.xt}, Fd={vendor.fd}")
    tooltip_label("xT (Liquid Pressure Drop Ratio Factor)", "Gaz icin kritik debi orani faktoru. Choked flow "
        "baslangic noktasini belirler. Tipik deger 0.6-0.7.")
    tooltip_label("Fd (Valve Style Modifier)", "Vana stilligi duzeltme katsayisi. Globe vanalar icin "
        "1.0 dir.")
    g1, g2 = st.columns(2)
    tooltip_label("Hat Giris Capi", "Gaz hat giris boru capi. Reducer etkisi hesaplamada kullanilir.")
    pipe_in_mm = g1.number_input("Hat giris capi [mm]", key="gas_pipe_in_mm", min_value=1.0, step=1.0)
    tooltip_label("Hat Cikis Capi", "Gaz hat cikis boru capi. Erozion hizi hesaplamada kullanilir.")
    pipe_out_mm = g2.number_input("Hat cikis capi [mm]", key="gas_pipe_out_mm", min_value=1.0, step=1.0)

    if not getattr(st.session_state, "gas_valid", False):
        st.error("Gaz kompozisyonu geçersiz: toplam yüzde 100 olmalı.")
        st.session_state.last_result = None
    else:
        try:
            summary = evaluate_gas_mixture(st.session_state.gas_rows, basis, inlet_pressure, temperature_c, gas_model)
            st.session_state.gas_summary = summary
            flow_nm3h = gas_flow_to_nm3h(
                flow_value,
                flow_unit,
                pressure_bar_a=inlet_pressure,
                temperature_c=temperature_c,
                z=summary.z or 1.0,
                density_kg_m3=summary.density_kg_m3,
            )
            fluid_summary = {
                "Mixture basis": basis,
                "Average MW": f"{summary.average_molecular_weight:.6f}",
                "Z": f"{summary.z:.6f}" if summary.z is not None else "-",
                "Density [kg/m3]": f"{summary.density_kg_m3:.6f}" if summary.density_kg_m3 is not None else "-",
                "Viscosity [Pa.s]": f"{summary.viscosity_pa_s:.6g}" if summary.viscosity_pa_s is not None else "-",
                "Cp [J/kg.K]": f"{summary.cp_j_kgk:.6f}" if summary.cp_j_kgk is not None else "-",
                "Cv [J/kg.K]": f"{summary.cv_j_kgk:.6f}" if summary.cv_j_kgk is not None else "-",
                "k = Cp/Cv": f"{summary.specific_heat_ratio:.6f}" if summary.specific_heat_ratio is not None else "-",
            }

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Ortalama MW", f"{summary.average_molecular_weight:.3f}")
            m2.metric("Z", f"{summary.z:.5f}" if summary.z is not None else "-")
            m3.metric("Yogunluk [kg/m3]", f"{summary.density_kg_m3:.4f}" if summary.density_kg_m3 is not None else "-")
            m4.metric("k = Cp/Cv", f"{summary.specific_heat_ratio:.4f}" if summary.specific_heat_ratio is not None else "-")

            gas_input = GasSizingInput(
                flow_nm3h=flow_nm3h,
                inlet_pressure_bar_a=inlet_pressure,
                outlet_pressure_bar_a=outlet_pressure,
                temperature_c=temperature_c,
                molecular_weight=summary.average_molecular_weight,
                specific_heat_ratio=summary.specific_heat_ratio or 1.30,
                viscosity_pa_s=summary.viscosity_pa_s or 1e-5,
                z=summary.z or 1.0,
                fl=vendor.fl or 0.9,
                fd=vendor.fd or 1.0,
                xt=vendor.xt or 0.7,
                pipe_inlet_diameter_mm=pipe_in_mm,
                pipe_outlet_diameter_mm=pipe_out_mm,
            )
            result = size_gas_valve(
                gas_input,
                valve_series=list(vendor.sizes),
                valve_meta=_vendor_meta(vendor_key),
                design_margin_pct=st.session_state.design_margin,
                flow_characteristic=st.session_state.flow_characteristic,
            )
            _live_render("Gas", result, fluid_summary)
            with st.expander("Joule-Thomson & Gaz Hidrat Analizi", expanded=False):
                try:
                    from joule_thomson import calc_joule_thomson_drop

                    dominant_fluid = "Methane"
                    if st.session_state.gas_rows:
                        dominant_fluid = max(
                            st.session_state.gas_rows,
                            key=lambda r: float(r.get("fraction_pct", 0.0) or 0.0),
                        ).get("component", "Methane")
                    jt_res = calc_joule_thomson_drop(dominant_fluid, inlet_pressure, outlet_pressure, temperature_c)
                    jt_c1, jt_c2, jt_c3, jt_c4 = st.columns(4)
                    jt_c1.metric("Cikis T2 (JT)", f"{jt_res.t2_c:.1f} \u00b0C", delta=f"-{jt_res.delta_t_c:.1f} \u00b0C")
                    jt_c2.metric("JT Katsayisi", f"{jt_res.mu_jt_c_per_bar:.3f} \u00b0C/bar")
                    jt_c3.metric("Hidrat Sicakligi", f"{jt_res.t_hydrate_c:.1f} \u00b0C")
                    jt_c4.metric("Min On Isitici", f"{jt_res.t_preheat_min_c:.1f} \u00b0C")
                    if jt_res.hydrate_risk:
                        st.error(
                            f"Gaz hidrat (kristallesme) riski! Cikis sicakligi {jt_res.t2_c:.1f} \u00b0C, "
                            f"hidrat esigine ({jt_res.t_hydrate_c:.1f} \u00b0C) cok yakin!"
                        )
                    if jt_res.freezing_risk:
                        st.warning(f"Donma riski: Vana cikisinda sicaklik {jt_res.t2_c:.1f} \u00b0C <= 0 \u00b0C.")
                    for w in jt_res.warnings:
                        st.caption(f"- {w}")
                except Exception as jt_exc:
                    st.caption(f"J-T analizi yapilamadi: {jt_exc}")
            with st.expander("Z Duyarliligi (delta_z = +/-0.05)", expanded=False):
                if st.checkbox("Hesapla", key="z_sens_enabled"):
                    zs = z_sensitivity_gas(
                        gas_input,
                        valve_series=list(vendor.sizes),
                        valve_meta=_vendor_meta(vendor_key),
                    )
                    z1, z2, z3, z4 = st.columns(4)
                    z1.metric("Cv (Z-0.05)", f"{zs['cv_low']:.3f}")
                    z2.metric("Cv (nominal)", f"{zs['cv_mid']:.3f}")
                    z3.metric("Cv (Z+0.05)", f"{zs['cv_high']:.3f}")
                    z4.metric("Degisim", f"%{zs['delta_percent']:.2f}")
                    st.caption("Z faktor belirsizliginin gerekli Cv'ye etkisi; nihai secim vendor yazilimi ile dogrulanmalidir.")
        except Exception as exc:
            st.error(f"Gaz sizing hesaplamasi yapilirken hata olustu: {exc}")
            st.session_state.last_result = None

    st.markdown('</div>', unsafe_allow_html=True)
    valid = st.session_state.last_result and st.session_state.last_result["service"] == "gas"
    return (st.session_state.last_result if valid else None), st.session_state.last_fluid_summary


def render_steam_section(vendor_key: str) -> tuple[dict | None, dict]:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Buhar")
    with st.expander("Buhar Ozellikleri", expanded=True):
        temp_unit, pres_unit, flow_unit = _unit_selectors("steam", STEAM_FLOW_UNITS)
        temp_label = TEMPERATURE_UNITS[temp_unit]
        pres_label = PRESSURE_UNITS[pres_unit]
        flow_label = STEAM_FLOW_UNITS[flow_unit]
        c1, c2, c3, c4 = st.columns(4)
        tooltip_label("Debi", "Buhar kutlesel debi (kg/h). Gerekli Cv hesaplamanin temel parametresidir.")
        flow_kg_h = steam_flow_to_kgh(c1.number_input(f"Debi [{flow_label}]", key="steam_flow_kgh", min_value=0.0001, step=100.0), flow_unit)
        tooltip_label("Sicaklik", "Buhar giris sicakligi. Z faktoru ve density hesaplamada kullanilir.")
        temperature_c = temperature_to_c(c2.number_input(f"Sicaklik [{temp_label}]", key="steam_temp_c", step=1.0), temp_unit)
        tooltip_label("Giris Basinci (P1)", "Buhar giris mutlak basinci. Choked flow ve density hesaplamada kullanilir.")
        inlet_pressure = pressure_to_bar_a(
            c3.number_input(f"Giris P [{pres_label}]", key="steam_p1", min_value=0.001, step=0.1), pres_unit
        )
        tooltip_label("Cikis Basinci (P2)", "Buhar cikis mutlak basinci. Delta P ve choked kontrolunde kullanilir.")
        outlet_pressure = pressure_to_bar_a(
            c4.number_input(f"Cikis P [{pres_label}]", key="steam_p2", min_value=0.001, step=0.1), pres_unit
        )

    from fluid_properties import evaluate_steam_state, get_saturated_steam_temperature

    t_sat = get_saturated_steam_temperature(inlet_pressure)
    lock_sat = st.checkbox(f"Doymus buhar sicakligini otomatik kilitle (T = Tsat = {t_sat:.1f} \u00b0C)", value=False, key="steam_lock_sat")
    if lock_sat:
        temperature_c = t_sat

    steam_eval = evaluate_steam_state(inlet_pressure, temperature_c)
    st.info(f"Buhar Durumu: {steam_eval['phase_label']} (Doyma Sicakligi Tsat = {t_sat:.1f} \u00b0C)")
    for w in steam_eval["warnings"]:
        st.warning(w)

    vendor = get_vendor_definition(vendor_key)
    st.caption(f"Vendor representative data: {vendor.vendor} / {vendor.style}, xT={vendor.xt}")
    tooltip_label("xT (Liquid Pressure Drop Ratio Factor)", "Buhar icin kritik debi orani faktoru. Choked flow "
        "baslangic noktasini belirler. Tipik deger 0.7-0.72.")

    gamma = 1.30
    z_value = 1.0
    try:
        props = get_pure_fluid_state("Water", inlet_pressure, temperature_c)
        gamma = props["specific_heat_ratio"]
        z_value = props["z"]
        st.session_state.steam_k = gamma
        st.session_state.steam_z = z_value
        st.caption(f"Water/steam referansi ile hesaplandi: k={gamma:.5f}, Z={z_value:.5f}")
    except Exception as exc:
        st.warning(f"Steam referans ozellikleri okunamadi: {exc}")

    fluid_summary = {
        "Reference fluid": "Water/Steam",
        "k = Cp/Cv": f"{gamma:.6f}",
        "Z": f"{z_value:.6f}",
    }

    try:
        result = size_steam_valve(
            SteamSizingInput(
                flow_kg_h=flow_kg_h,
                inlet_pressure_bar_a=inlet_pressure,
                outlet_pressure_bar_a=outlet_pressure,
                temperature_c=temperature_c,
                specific_heat_ratio=gamma,
                z=z_value,
                xt=vendor.xt or 0.72,
                fl=vendor.fl or 0.9,
                fd=vendor.fd or 1.0,
            ),
            valve_series=list(vendor.sizes),
            valve_meta=_vendor_meta(vendor_key),
            design_margin_pct=st.session_state.design_margin,
            flow_characteristic=st.session_state.flow_characteristic,
        )
        _live_render("Steam", result, fluid_summary)
    except Exception as exc:
        st.error(f"Buhar sizing hesaplamasi yapilirken hata olustu: {exc}")
        st.session_state.last_result = None

    st.markdown('</div>', unsafe_allow_html=True)
    valid = st.session_state.last_result and st.session_state.last_result["service"] == "steam"
    return (st.session_state.last_result if valid else None), fluid_summary




def main() -> None:
    st.set_page_config(page_title="Control Valve Sizing", page_icon="⚙️", layout="wide")

    # Custom CSS for modern UI/UX improvements
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    :root {
        --primary-color: #2563eb;
        --primary-hover: #1d4ed8;
        --secondary-color: #64748b;
        --success-color: #10b981;
        --warning-color: #f59e0b;
        --error-color: #ef4444;
        --card-bg: #ffffff;
        --card-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
        --bg-gradient: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        --text-primary: #1e293b;
        --text-secondary: #64748b;
        --border-color: #e2e8f0;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    }

    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    .main-header {
        text-align: center;
        margin-bottom: 2rem;
        padding: 2rem;
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        border-radius: 12px;
        color: white;
    }

    .main-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
    }

    .main-header p {
        margin: 0.5rem 0 0;
        font-size: 1.1rem;
        opacity: 0.9;
    }

    .card {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        background-color: #ffffff;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }

    .card:hover {
        box-shadow: 0 8px 12px -1px rgba(0, 0, 0, 0.1), 0 6px 6px -2px rgba(0, 0, 0, 0.1);
    }

    .metric-card {
        text-align: center;
        padding: 1rem;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        margin: 0.5rem;
        background-color: #ffffff;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }

    .metric-card h4 {
        margin: 0;
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .metric-card p {
        margin: 0.5rem 0 0;
        font-size: 1.25rem;
        font-weight: 700;
        color: #1e293b;
    }

    .highlight-card {
        border-left: 4px solid #2563eb;
        background-color: #f8fafc;
    }

    .warning-card {
        border-left: 4px solid #f59e0b;
        background-color: #fffbeb;
    }

    .error-card {
        border-left: 4px solid #ef4444;
        background-color: #fef2f2;
    }

    .success-card {
        border-left: 4px solid #10b981;
        background-color: #f0fdf4;
    }

    .section-header {
        font-size: 1.25rem;
        font-weight: 600;
        color: #1e293b;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #e2e8f0;
    }

    .section-subheader {
        font-size: 1rem;
        font-weight: 600;
        color: #475569;
        margin-bottom: 0.5rem;
    }

    /* Tooltip styles */
    .tooltip-container {
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }

    .tooltip-btn {
        font-size: 14px;
        cursor: help;
        border: none;
        background: transparent;
        color: #6c757d;
        padding: 0;
        line-height: 1;
    }

    .tooltip-btn:hover {
        color: #1a73e8;
    }

    .tooltip-content {
        visibility: hidden;
        position: absolute;
        background-color: #333;
        color: #fff;
        text-align: left;
        border-radius: 4px;
        padding: 8px 12px;
        z-index: 1000;
        font-size: 13px;
        line-height: 1.4;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        width: max-content;
        max-width: 300px;
        white-space: pre-wrap;
    }

    .tooltip-container:hover .tooltip-content {
        visibility: visible;
    }

    .help-label {
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .stTextInput, .stNumberInput, .stSelectbox, .stRadio {
        margin-bottom: 10px;
    }

    .error-msg {
        color: #ef4444;
        font-weight: bold;
    }

    .success-msg {
        color: #10b981;
        font-weight: bold;
    }

    @media (max-width: 768px) {
        .card {
            padding: 10px;
            margin: 5px 0;
        }
        .metric-card {
            padding: 0.75rem;
            margin: 0.5rem;
        }
        .stButton button {
            width: 100%;
        }
        .stColumns {
            flex-direction: column;
        }
    }
    </style>
    """, unsafe_allow_html=True)

    if st.context.theme.get("type") == "dark":
        st.markdown("""
        <style>
        .card {
            background-color: #1e293b;
            border-color: #334155;
        }
        .metric-card {
            background-color: #0f172a;
            border-color: #334155;
        }
        .metric-card h4 {
            color: #94a3b8;
        }
        .metric-card p {
            color: #e2e8f0;
        }
        .highlight-card {
            background-color: #0f172a;
        }
        .warning-card {
            background-color: #3b2f0b;
        }
        .error-card {
            background-color: #3b1414;
        }
        .success-card {
            background-color: #0d2b1c;
        }
        .section-header {
            color: #e2e8f0;
            border-bottom-color: #334155;
        }
        .section-subheader {
            color: #cbd5e1;
        }
        </style>
        """, unsafe_allow_html=True)

    _init_state()

    # Apply a pending reset BEFORE any widget is instantiated (Streamlit forbids
    # modifying widget-bound session_state keys after their widget is created).
    if st.session_state.pop("_reset_defaults", False):
        for key, value in DEFAULTS.items():
            st.session_state[key] = value
        st.session_state.service_slider = SERVICE_LABELS["Liquid"]
        st.session_state.gas_rows = DEFAULT_GAS_ROWS
        st.session_state.gas_valid = True
        st.session_state.last_result = None
        st.session_state.last_report = ""
        st.session_state.last_fluid_summary = None
        st.session_state.result_history = []
        for prefix in ("liquid", "gas", "steam"):
            for kind in ("temp", "pres", "flow"):
                st.session_state.pop(f"_unit_prev_{prefix}_{kind}", None)
        st.session_state.pop("_pending_project_load", None)

    _apply_pending_project_load()

    st.title("Control Valve Sizing")
    st.caption("Kaynakli Streamlit arayuzu: liquid, gas ve steam servisleri icin IEC/ISA'ya yaklastirilmis sizing uygulamasi.")

    nav_cols = st.columns(3, gap="small")
    for col, service in zip(nav_cols, ("Liquid", "Gas", "Steam"), strict=True):
        col.button(
            SERVICE_LABELS[service],
            key=f"service_tab_{service}",
            type="primary" if st.session_state.service == service else "secondary",
            use_container_width=True,
            on_click=_select_service,
            args=(service,),
        )
    slider_kwargs: dict[str, Any] = {"key": "service_slider", "on_change": _sync_service_from_slider}
    if "service_slider" not in st.session_state:
        slider_kwargs["value"] = SERVICE_LABELS[st.session_state.service]
    st.select_slider(
        "Servis",
        options=list(SERVICE_LABELS.values()),
        label_visibility="collapsed",
        **slider_kwargs,
    )

    vendor_key = st.sidebar.selectbox(
        "Vendor representative trim",
        get_vendor_options(),
        index=get_vendor_options().index(st.session_state.vendor_key),
    )
    st.session_state.vendor_key = vendor_key

    st.sidebar.markdown("**Tasarim secenekleri**")
    tooltip_label("Tasarim Marji [%]", "Gerekli Cv'nin uzerinde eklenen guvenlik marji. Tipik deger %15 dir. "
        "Yuksek marj daha buyuk vana secimine neden olur.")
    st.sidebar.number_input("Tasarim marji [%]", key="design_margin", min_value=0.0, max_value=100.0, step=5.0)
    tooltip_label("Akis Karakteristiği", "Vana aciligi ile debi arasindaki iliski. Equal percentage: dusuk debide hassas, "
        "linear: dogrusal, quick opening: hizli acilim.")
    st.sidebar.selectbox(
        "Akis karakteristigi",
        ("equal_percentage", "linear", "quick_opening"),
        key="flow_characteristic",
    )
    render_source_library()
    render_unit_converter()

    st.sidebar.markdown("---")
    if st.sidebar.button(
        "Varsayılana Sıfırla",
        type="secondary",
        use_container_width=True,
        help="Tüm giriş alanlarını ve sonucu fabrika ayarlarına döndürür.",
    ):
        st.session_state["_reset_defaults"] = True
        st.rerun()

    payload = {
        "service": st.session_state.service,
        "vendor_key": st.session_state.vendor_key,
        "gas_rows": st.session_state.gas_rows,
        "liquid_source": st.session_state.liquid_source,
        "liquid_preset_label": st.session_state.liquid_preset_label,
        "liquid_temp_c": st.session_state.liquid_temp_c,
        "liquid_ref_pressure_bar_a": st.session_state.liquid_ref_pressure_bar_a,
        "liquid_density": st.session_state.liquid_density,
        "liquid_pv": st.session_state.liquid_pv,
        "liquid_pc": st.session_state.liquid_pc,
        "liquid_flow_m3h": st.session_state.liquid_flow_m3h,
        "liquid_p1": st.session_state.liquid_p1,
        "liquid_p2": st.session_state.liquid_p2,
        "liquid_mu": st.session_state.liquid_mu,
        "liquid_pipe_in_mm": st.session_state.liquid_pipe_in_mm,
        "liquid_pipe_out_mm": st.session_state.liquid_pipe_out_mm,
        "liquid_temp_unit": _unit_key(st.session_state.liquid_temp_unit, TEMPERATURE_UNITS),
        "liquid_pres_unit": _unit_key(st.session_state.liquid_pres_unit, PRESSURE_UNITS),
        "liquid_flow_unit": _unit_key(st.session_state.liquid_flow_unit, LIQUID_FLOW_UNITS),
        "gas_basis": st.session_state.gas_basis,
        "gas_preset": st.session_state.gas_preset,
        "gas_model": st.session_state.gas_model,
        "gas_temp_c": st.session_state.gas_temp_c,
        "gas_p1": st.session_state.gas_p1,
        "gas_p2": st.session_state.gas_p2,
        "gas_flow_nm3h": st.session_state.gas_flow_nm3h,
        "gas_pipe_in_mm": st.session_state.gas_pipe_in_mm,
        "gas_pipe_out_mm": st.session_state.gas_pipe_out_mm,
        "gas_temp_unit": _unit_key(st.session_state.gas_temp_unit, TEMPERATURE_UNITS),
        "gas_pres_unit": _unit_key(st.session_state.gas_pres_unit, PRESSURE_UNITS),
        "gas_flow_unit": _unit_key(st.session_state.gas_flow_unit, GAS_FLOW_UNITS),
        "steam_flow_kgh": st.session_state.steam_flow_kgh,
        "steam_temp_c": st.session_state.steam_temp_c,
        "steam_p1": st.session_state.steam_p1,
        "steam_p2": st.session_state.steam_p2,
        "steam_temp_unit": _unit_key(st.session_state.steam_temp_unit, TEMPERATURE_UNITS),
        "steam_pres_unit": _unit_key(st.session_state.steam_pres_unit, PRESSURE_UNITS),
        "steam_flow_unit": _unit_key(st.session_state.steam_flow_unit, STEAM_FLOW_UNITS),
    }
    render_project_tools(st.session_state.service, payload)

    if st.session_state.service == "Liquid":
        render_liquid_section(vendor_key)
    elif st.session_state.service == "Gas":
        render_gas_section(vendor_key)
    else:
        render_steam_section(vendor_key)

    render_report_tools()

    adv_tabs = st.tabs([
        "Çoklu Durum",
        "Anti-Kavitasyon Trim",
        "Aktüatör Dinamiği",
        "Salmastra & Emisyon",
        "Boru Güvenliği & PSV",
        "Malzeme & Bonnet",
        "Termal Genleşme",
        "Notlar",
    ])

    with adv_tabs[0]:
        st.markdown(
            "IEC 60534 standartlarina gore vananin Minimum, Normal ve Maksimum debi durumlarinda "
            "eszamanli kontrol edilebilirligi (Min %10+, Normal %40-75, Max <%85 aciklik) analiz edilir."
        )
        cur_serv = st.session_state.service.lower()
        flow_key = "liquid_flow_m3h" if cur_serv == "liquid" else ("gas_flow_nm3h" if cur_serv == "gas" else "steam_flow_kgh")
        def_flow = float(st.session_state.get(flow_key, 100.0))
        def_p1 = float(st.session_state.get(f"{cur_serv}_p1", 8.0))
        def_p2 = float(st.session_state.get(f"{cur_serv}_p2", 5.0))
        flow_units = LIQUID_FLOW_UNITS if cur_serv == "liquid" else GAS_FLOW_UNITS if cur_serv == "gas" else STEAM_FLOW_UNITS
        flow_unit = _unit_key(st.session_state[f"{cur_serv}_flow_unit"], flow_units)
        pres_unit = _unit_key(st.session_state[f"{cur_serv}_pres_unit"], PRESSURE_UNITS)
        temp_unit = _unit_key(st.session_state[f"{cur_serv}_temp_unit"], TEMPERATURE_UNITS)
        flow_label = flow_units[flow_unit]
        pres_label = PRESSURE_UNITS[pres_unit]

        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.markdown("**Minimum Durum (Startup / Min)**")
            mc_min_q = st.number_input(f"Min Debi [{flow_label}]", value=max(def_flow * 0.4, 0.1), key="mc_min_q")
            mc_min_p1 = st.number_input(f"Min P1 [{pres_label}]", value=def_p1, key="mc_min_p1")
            mc_min_p2 = st.number_input(f"Min P2 [{pres_label}]", value=def_p2, key="mc_min_p2")
        with mc2:
            st.markdown("**Normal Durum (Duty Point)**")
            mc_norm_q = st.number_input(f"Normal Debi [{flow_label}]", value=max(def_flow, 0.1), key="mc_norm_q")
            mc_norm_p1 = st.number_input(f"Normal P1 [{pres_label}]", value=def_p1, key="mc_norm_p1")
            mc_norm_p2 = st.number_input(f"Normal P2 [{pres_label}]", value=def_p2, key="mc_norm_p2")
        with mc3:
            st.markdown("**Maksimum Durum (Design / Max)**")
            mc_max_q = st.number_input(f"Max Debi [{flow_label}]", value=max(def_flow * 1.3, 0.1), key="mc_max_q")
            mc_max_p1 = st.number_input(f"Max P1 [{pres_label}]", value=max(def_p1 * 0.95, 0.1), key="mc_max_p1")
            mc_max_p2 = st.number_input(f"Max P2 [{pres_label}]", value=def_p2, key="mc_max_p2")

        if st.button("Coklu Durum Boyutlandirma Analizi Yap"):
            from multi_case import OperatingCase, size_multicase

            temp_c = temperature_to_c(float(st.session_state.get(f"{cur_serv}_temp_c", 25.0)), temp_unit)
            gas_s = getattr(st.session_state, "gas_summary", None)

            def _case(name: str, flow: float, p1: float, p2: float) -> OperatingCase:
                p1_bar_a = pressure_to_bar_a(p1, pres_unit)
                p2_bar_a = pressure_to_bar_a(p2, pres_unit)
                if cur_serv == "liquid":
                    flow_engine = liquid_flow_to_m3h(flow, flow_unit, density_kg_m3=st.session_state.liquid_density)
                elif cur_serv == "gas":
                    case_summary: Any = gas_s
                    try:
                        case_summary = evaluate_gas_mixture(
                            st.session_state.gas_rows,
                            st.session_state.gas_basis,
                            p1_bar_a,
                            temp_c,
                            st.session_state.gas_model,
                        )
                    except Exception:
                        case_summary = gas_s
                    flow_engine = gas_flow_to_nm3h(
                        flow,
                        flow_unit,
                        pressure_bar_a=p1_bar_a,
                        temperature_c=temp_c,
                        z=(case_summary.z if case_summary and case_summary.z else 1.0),
                        density_kg_m3=case_summary.density_kg_m3 if case_summary else None,
                    )
                else:
                    flow_engine = steam_flow_to_kgh(flow, flow_unit)
                extra_props: dict[str, Any] = {}
                if cur_serv == "gas" and case_summary:
                    extra_props = {
                        "molecular_weight": case_summary.average_molecular_weight,
                        "specific_heat_ratio": case_summary.specific_heat_ratio or 1.30,
                        "viscosity_pa_s": case_summary.viscosity_pa_s or 1.8e-5,
                        "z": case_summary.z or 1.0,
                    }
                return OperatingCase(name, flow_engine, p1_bar_a, p2_bar_a, temp_c, extra_props=extra_props)

            cases = [
                _case("Min", mc_min_q, mc_min_p1, mc_min_p2),
                _case("Normal", mc_norm_q, mc_norm_p1, mc_norm_p2),
                _case("Max", mc_max_q, mc_max_p1, mc_max_p2),
            ]
            mc_fluid_data: dict[str, Any] = {}
            if cur_serv == "liquid":
                pv_unit = _absolute_pressure_unit(pres_unit)
                mc_fluid_data = {
                    "density_kg_m3": st.session_state.liquid_density,
                    "vapor_pressure_bar_a": pressure_to_bar_a(st.session_state.liquid_pv, pv_unit),
                    "critical_pressure_bar_a": pressure_to_bar_a(st.session_state.liquid_pc, pv_unit),
                    "viscosity_pa_s": st.session_state.liquid_mu,
                }
            elif cur_serv == "gas":
                if gas_s:
                    mc_fluid_data = {
                        "molecular_weight": gas_s.average_molecular_weight,
                        "specific_heat_ratio": gas_s.specific_heat_ratio or 1.30,
                        "viscosity_pa_s": gas_s.viscosity_pa_s or 1.8e-5,
                        "z": gas_s.z or 1.0,
                    }
                else:
                    mc_fluid_data = {
                        "molecular_weight": 28.96,
                        "specific_heat_ratio": 1.40,
                        "viscosity_pa_s": 1.8e-5,
                        "z": 1.0,
                    }
            else:
                steam_k = getattr(st.session_state, "steam_k", 1.30)
                steam_z = getattr(st.session_state, "steam_z", 1.0)
                mc_fluid_data = {"specific_heat_ratio": steam_k, "z": steam_z}

            vendor = get_vendor_definition(vendor_key)
            mc_fluid_data["fl"] = vendor.fl or 0.9
            mc_fluid_data["xt"] = vendor.xt or 0.7
            mc_fluid_data["fd"] = vendor.fd or 1.0

            mc_res = size_multicase(
                cur_serv,
                cases,
                mc_fluid_data,
                valve_series=list(vendor.sizes),
                flow_characteristic=st.session_state.flow_characteristic,
            )
            st.session_state.last_multicase = mc_res
            st.success(mc_res.overall_summary)
            st.metric("Turndown Orani (Qmax / Qmin)", f"{mc_res.turndown_ratio:.1f}:1")
            cand_rows = []
            for c in mc_res.candidates:
                cand_rows.append({
                    "Vana": f"DN{c.valve.dn_mm} ({c.valve.inch})",
                    "Rated Cv": c.valve.cv_rated,
                    "Min Aciklik": f"%{c.opening_min_pct:.1f}",
                    "Normal Aciklik": f"%{c.opening_norm_pct:.1f}",
                    "Max Aciklik": f"%{c.opening_max_pct:.1f}",
                    "Degerlendirme": c.status_label,
                    "Onerilen": "\u2605 EVET" if c.is_recommended else "",
                })
            st.dataframe(pd.DataFrame(cand_rows), hide_index=True)
            rec = mc_res.recommended or (mc_res.candidates[0] if mc_res.candidates else None)
            if rec:
                details = list(rec.case_details.values())
                fig_mc = go.Figure(go.Scatter3d(
                    x=[d.flow for d in details],
                    y=[d.p1_bar_a - d.p2_bar_a for d in details],
                    z=[d.opening_pct for d in details],
                    mode="markers+text",
                    text=[d.name for d in details],
                    textposition="top center",
                    marker={"size": 7, "color": [d.opening_pct for d in details],
                            "colorscale": "RdYlGn_r", "cmin": 0, "cmax": 100},
                ))
                fig_mc.update_layout(
                    scene={"xaxis_title": "Debi", "yaxis_title": "DeltaP [bar]", "zaxis_title": "Aciklik [%]"},
                    margin={"l": 0, "r": 0, "t": 10, "b": 0}, height=420,
                )
                st.plotly_chart(fig_mc, use_container_width=True)
            for w in mc_res.warnings:
                st.warning(w)

    with adv_tabs[1]:
        st.markdown(
            "Yüksek basınç düşüşlü sıvı servislerinde kavitasyon hasarını ve gürültüyü önlemek için "
            "basınç düşüşü $N$ kademeli direnç elemanlarına (Multi-Stage Letdown) paylaştırılır."
        )
        from trim_guidance import design_multistage_cavitation_trim

        cur_s = st.session_state.service.lower()
        if cur_s == "liquid":
            pres_unit = _unit_key(st.session_state.liquid_pres_unit, PRESSURE_UNITS)
            def_p1 = pressure_to_bar_a(float(st.session_state.liquid_p1), pres_unit)
            def_p2 = pressure_to_bar_a(float(st.session_state.liquid_p2), pres_unit)
            def_pv = pressure_to_bar_a(float(st.session_state.liquid_pv), _absolute_pressure_unit(pres_unit))
        else:
            def_p1 = 50.0
            def_p2 = 10.0
            def_pv = 0.5

        c_col1, c_col2, c_col3 = st.columns(3)
        c_p1 = c_col1.number_input("Giriş Basıncı P1 [bar(a)]", value=def_p1, key="cav_p1_in")
        c_p2 = c_col2.number_input("Çıkış Basıncı P2 [bar(a)]", value=def_p2, key="cav_p2_in")
        c_pv = c_col3.number_input("Buhar Basıncı Pv [bar(a)]", value=def_pv, key="cav_pv_in")

        c_sub1, c_sub2 = st.columns(2)
        init_cv = float(st.session_state.last_result["required_cv"]) if st.session_state.last_result else 25.0
        c_cv = c_sub1.number_input("Tasarım Cv", value=init_cv, key="cav_cv_in")
        stage_opts = ["Otomatik (Minimum Güvenli Kademe)", "1 Kademe", "2 Kademe", "3 Kademe", "4 Kademe", "6 Kademe"]
        c_mode = c_sub2.selectbox("Kademe Seçimi", stage_opts, key="cav_stage_mode")

        req_stg = None
        if c_mode != "Otomatik (Minimum Güvenli Kademe)":
            req_stg = int(c_mode.split()[0])

        cav_design = design_multistage_cavitation_trim(
            p1_bar_a=c_p1,
            p2_bar_a=c_p2,
            pv_bar_a=c_pv,
            required_cv=c_cv,
            requested_stages=req_stg,
        )

        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("Kavitasyon İndeksi (σ)", f"{cav_design.single_stage_sigma:.2f}")
        cm2.metric("Kademe Sayısı", f"{cav_design.stages_count} Kademe")
        cm3.metric("Kavitasyon Durumu", "Önlendi (Güvenli)" if cav_design.is_cavitation_eliminated else "Kavitasyon Riski!")
        cm4.metric("Gürültü Azaltma", f"-{cav_design.noise_reduction_dba:.1f} dB(A)")

        st.info(f"**Önerilen Trim Yapısı:** {cav_design.trim_description}")

        if cav_design.warnings:
            for w in cav_design.warnings:
                st.warning(f"⚠️ {w}")
        else:
            st.success("✅ Tüm kademelerde vena contracta basıncı buharlaşma sınırının üzerindedir; kavitasyon tamamen bertaraf edilmiştir.")

        st_rows = [
            {
                "Kademe": f"Kademe {s.stage_number}",
                "Giriş P [bar]": f"{s.inlet_pressure_bar_a:.2f}",
                "Çıkış P [bar]": f"{s.outlet_pressure_bar_a:.2f}",
                "ΔP [bar]": f"{s.delta_p_bar:.2f}",
                "P_vc (Vena Contracta) [bar]": f"{s.vena_contracta_pressure_bar_a:.2f}",
                "Buhar Marjı [bar]": f"{s.margin_to_vapor_bar:.2f}",
                "Kavitasyon?": "EVET" if s.is_cavitating else "HAYIR",
                "Kademe Cv": f"{s.stage_cv:.2f}",
            }
            for s in cav_design.stages
        ]
        st.dataframe(pd.DataFrame(st_rows), hide_index=True)

    with adv_tabs[2]:
        st.markdown(
            "Pnömatik aktüatörün açılma/kapanma strok süresi, konumlandırıcı (positioner) hava debisi, "
            "hacim yükseltici (volume booster) ihtiyacı ve enstrüman havası tüketim hesabı."
        )
        from actuator_sizing import analyze_actuator_dynamics, get_actuator_options

        act_opts = get_actuator_options()
        def_act = "DA-150"
        if st.session_state.last_result and isinstance(st.session_state.last_result.get("actuator_selection"), dict):
            sel_m = st.session_state.last_result["actuator_selection"].get("model")
            if sel_m and sel_m in act_opts:
                def_act = sel_m

        act_col1, act_col2 = st.columns(2)
        act_key = act_col1.selectbox("Aktüatör Modeli", act_opts, index=act_opts.index(def_act), key="dyn_act_key")
        act_p_sup = act_col2.number_input(
            "Hava Besleme Basıncı [bar(g)]", value=4.0, min_value=1.0, max_value=10.0, step=0.5, key="dyn_act_psup"
        )

        act_c3, act_c4, act_c5 = st.columns(3)
        act_q_pos = act_c3.number_input(
            "Konumlandırıcı Kapasitesi [Nm³/h]", value=14.0, min_value=1.0, step=1.0, key="dyn_act_qpos"
        )
        act_t_target = act_c4.number_input(
            "Hedef Strok Süresi [s]", value=2.0, min_value=0.1, step=0.5, key="dyn_act_ttarget"
        )
        act_cycles = act_c5.number_input(
            "Modülasyon Çevrimi [çevrim/saat]", value=60.0, min_value=0.0, step=10.0, key="dyn_act_cycles"
        )

        act_dyn = analyze_actuator_dynamics(
            actuator_key=act_key,
            supply_pressure_bar_g=act_p_sup,
            positioner_flow_capacity_nm3h=act_q_pos,
            target_stroke_time_sec=act_t_target,
            cycles_per_hour=act_cycles,
        )

        dm1, dm2, dm3, dm4 = st.columns(4)
        dm1.metric("Açılma Süresi (t_open)", f"{act_dyn.stroke_time_open_sec:.2f} s")
        dm2.metric("Kapanma Süresi (t_close)", f"{act_dyn.stroke_time_close_sec:.2f} s")
        dm3.metric("Oda Hacmi", f"{act_dyn.chamber_volume_liters:.2f} L")
        dm4.metric("Toplam Hava Tüketimi", f"{act_dyn.total_air_consumption_nm3h:.2f} Nm³/h")

        if act_dyn.booster_recommended:
            st.warning("⚠️ **Hacim Yükseltici (Volume Booster) Gerekli:** " + act_dyn.warnings[0])
        else:
            st.success(
                f"✅ Strok süresi ({max(act_dyn.stroke_time_open_sec, act_dyn.stroke_time_close_sec):.2f} s) "
                f"hedeflenen sınırın ({act_t_target:.2f} s) altındadır."
            )

        st.info(f"**Önerilen Enstrüman Hava Besleme Hattı:** {act_dyn.supply_line_recommendation}")

        for note in act_dyn.engineering_notes:
            st.caption(f"ℹ️ {note}")

    with adv_tabs[3]:
        from packing_emissions import recommend_packing_system

        pack_service = st.session_state.service.lower()
        pack_fluid = (
            st.session_state.get("liquid_preset_label", "Su")
            if pack_service == "liquid"
            else (st.session_state.get("gas_preset", "Doğal Gaz") if pack_service == "gas" else "Buhar")
        )
        pack_temp = float(st.session_state.get(f"{pack_service}_temp_c", 25.0))
        pack_pres = float(st.session_state.get(f"{pack_service}_p1", 10.0))

        pk_col1, pk_col2 = st.columns(2)
        with pk_col1:
            fluid_in = st.text_input("Akışkan Adı", value=pack_fluid, key="pack_fluid_in")
            temp_in = st.number_input("Çalışma Sıcaklığı [°C]", value=pack_temp, key="pack_temp_in")
            pres_in = st.number_input("Giriş Basıncı [bar(a)]", value=pack_pres, key="pack_pres_in")
        with pk_col2:
            is_toxic = st.checkbox("Zehirli / Kanserojen Akışkan (Lethal / Toxic Service)", value=False, key="pack_is_toxic")
            is_sour = st.checkbox("Ekşi Gaz / H2S Ortamı (NACE MR0175 / ISO 15156)", value=False, key="pack_is_sour")

        pk_res = recommend_packing_system(
            service=pack_service,
            fluid_name=fluid_in,
            temperature_c=temp_in,
            pressure_bar_a=pres_in,
            is_toxic_or_lethal=is_toxic,
            is_sour_gas=is_sour,
        )

        pk_c1, pk_c2, pk_c3 = st.columns(3)
        pk_c1.metric("Emisyon Sınıfı", pk_res.emission_class.split("/")[0].strip())
        pk_c2.metric("Sızdırmazlık Sınırı", f"< {pk_res.leakage_tightness_ppmv:.0f} ppmv")
        pk_c3.metric("Yangın Emniyeti", "API 607 Yangına Dayanıklı" if pk_res.fire_safe else "Yangın Korumasız")

        st.info(f"**Önerilen Salmastra Sistemi:** {pk_res.packing_type}")
        st.markdown(f"**Sıcaklık Aralığı:** {pk_res.temperature_range_c[0]:.0f} °C ... {pk_res.temperature_range_c[1]:.0f} °C")
        st.markdown(f"**Standart & Tasarım:** {pk_res.description}")
        if pk_res.nace_mr0175_compliant:
            st.success("NACE MR0175 / ISO 15156 gereksinimleri (mil sertliği ≤ 22 HRC vb.) karşılanmaktadır.")
        for r in pk_res.recommendations:
            st.caption(f"• {r}")

    with adv_tabs[4]:
        from safety_piping import calc_wide_open_relief_capacity, check_erosional_velocity

        cur_s = st.session_state.service.lower()
        res_cv = float(st.session_state.last_result["rated_cv"]) if st.session_state.last_result else 50.0
        res_p1 = float(st.session_state.get(f"{cur_s}_p1", 10.0))
        res_p2 = float(st.session_state.get(f"{cur_s}_p2", 4.0))

        bp_c1, bp_c2 = st.columns(2)
        with bp_c1:
            st.markdown("**API 14E Erozyonel Hız Sınırı**")
            bp_vel = st.number_input("Boru Akış Hızı [m/s]", value=4.5, step=0.1, key="bp_vel")
            bp_rho = st.number_input("Akışkan Yoğunluğu [kg/m³]", value=1000.0, step=10.0, key="bp_rho")
            bp_c_fact = st.selectbox(
                "API 14E C Katsayısı",
                [100.0, 125.0],
                format_func=lambda c: f"c={c:.0f} ({'Sürekli Servis' if c == 100 else 'Temiz Aralıklı'})",
            )
            eros_eval = check_erosional_velocity(bp_vel, bp_rho, c_factor=bp_c_fact)
            if eros_eval.is_velocity_exceeded:
                st.error(f"Erozyon Limiti Aşıldı! Limit: {eros_eval.erosional_limit_m_s:.2f} m/s (Oran: %{eros_eval.velocity_ratio*100:.0f})")
            else:
                st.success(f"Hız Güvenli: {bp_vel:.2f} m/s <= {eros_eval.erosional_limit_m_s:.2f} m/s")
            for w in eros_eval.warnings:
                st.caption(f"- {w}")

        with bp_c2:
            st.markdown("**API 520 Vana Tam Açık Tahliye Yükü**")
            bp_cv = st.number_input("Nominal Rated Cv", value=res_cv, step=5.0, key="bp_cv")
            bp_prel = st.number_input("PSV Tahliye Basıncı [bar(a)]", value=max(res_p2 * 1.1, 1.0), step=0.5, key="bp_prel")
            fl_data: dict[str, float] = {}
            if cur_s == "liquid":
                fl_data = {"specific_gravity": 1.0, "fl": 0.9, "vapor_pressure_bar_a": 0.023}
            elif cur_s == "gas":
                fl_data = {"molecular_weight": 28.96, "temperature_c": 20.0, "xt": 0.70, "specific_heat_ratio": 1.40}
            else:
                fl_data = {"density_kg_m3": 5.0, "xt": 0.70}

            relief_eval = calc_wide_open_relief_capacity(cur_s, bp_cv, res_p1, bp_prel, fl_data)
            st.metric("PSV Arıza Tahliye Debisi", f"{relief_eval.wide_open_flow_rate:.1f} {relief_eval.flow_unit}")
            if relief_eval.is_choked:
                st.info("Vana tam açık durumda sonik/kavitasyonel boğulma rejimindedir.")
            for sn in relief_eval.safety_notes:
                st.caption(f"- {sn}")

    with adv_tabs[5]:
        from valve_selection import recommend_alloy_material, recommend_bonnet_type

        mat_srv = st.session_state.service.lower()
        mat_temp = float(st.session_state.get(f"{mat_srv}_temp_c", 25.0))
        mat_fluid = st.text_input(
            "Akışkan",
            value="Doğal Gaz" if mat_srv == "gas" else ("Su" if mat_srv == "liquid" else "Buhar"),
            key="mat_fluid",
        )
        mat_col1, mat_col2 = st.columns(2)
        with mat_col1:
            mat_is_sour = st.checkbox("Ekşi Gaz / H2S Servisi (NACE MR0175)", value=False, key="mat_sour")
        with mat_col2:
            mat_is_h2 = st.checkbox("Hidrojen / Sentez Gazı (API 941 Nelson)", value=False, key="mat_h2")

        rec_bonnet = recommend_bonnet_type(mat_temp, mat_srv, mat_fluid)
        rec_alloy = recommend_alloy_material(mat_srv, mat_fluid, mat_temp, is_sour=mat_is_sour, is_h2=mat_is_h2)

        st.markdown(f"**Önerilen Bonnet Tipi:** {rec_bonnet}")
        m_c1, m_c2, m_c3 = st.columns(3)
        m_c1.metric("Gövde Malzemesi", rec_alloy.body_material.split("(")[0].strip())
        m_c2.metric("Trim Malzemesi", rec_alloy.trim_material.split("+")[0].strip())
        m_c3.metric("Mil Malzemesi", rec_alloy.stem_material.split("(")[0].strip())
        st.info(f"**Tasarım Standardı:** {rec_alloy.design_standard}")
        for mr in rec_alloy.recommendations:
            st.caption(f"• {mr}")

    with adv_tabs[6]:
        from thermal_expansion import (
            get_material_label,
            get_material_options,
            pipe_linear_expansion,
            pipe_thermal_stress,
        )

        te_mat = st.selectbox("Boru malzemesi", get_material_options(), format_func=get_material_label)
        te_len = st.number_input("Boru uzunlugu [m]", min_value=1.0, value=10.0, step=1.0)
        te_t1 = st.number_input("Montaj sicakligi [C]", min_value=-50.0, value=10.0, step=1.0)
        te_t2 = st.number_input("Isletme sicakligi [C]", min_value=-50.0, value=90.0, step=1.0)
        if st.button("Termal genlesme hesapla"):
            delta_t = te_t2 - te_t1
            expansion_mm = pipe_linear_expansion(te_len, delta_t, te_mat)
            stress_mpa = pipe_thermal_stress(delta_t, te_mat)
            c1, c2, c3 = st.columns(3)
            c1.metric("Uzama [mm]", f"{expansion_mm:.2f}")
            c2.metric("Termal gerilme [MPa]", f"{stress_mpa:.1f}")
            c3.metric("dT [C]", f"{delta_t:.1f}")
            st.caption("Genlesme kompansatoru / loop gereksinimi icin boru hatti mekanik analizi yapilmalidir.")

    with adv_tabs[7]:
        st.markdown(
            """
            - Vendor katalog verileri: Emerson Fisher (4 trim), Metso/Valmet (3), SAMSON (3), ARCA (2) — toplam 12 representative trim.
            - Hesap motoru IEC 60534 / ISA sizing mantigina yaklastirilmistir.
            - Final secim, seat leakage, body size, trim noise ve malzeme icin vendor yazilimiyle dogrulanmalidir.
            """
        )


if __name__ == "__main__":
    main()
