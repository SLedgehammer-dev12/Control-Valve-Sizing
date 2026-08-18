from __future__ import annotations

import pandas as pd
import streamlit as st

from config import DEFAULT_GAS_ROWS, GAS_PRESET_NAMES, GAS_PRESETS
from fluid_properties import LIQUID_PRESETS, evaluate_gas_mixture, get_liquid_preset, get_pure_fluid_state, list_coolprop_fluids
from project_io import dump_project_json, load_project_json
from reporting import build_report
from units import (
    GAS_FLOW_UNITS,
    LIQUID_FLOW_UNITS,
    PRESSURE_UNITS,
    STEAM_FLOW_UNITS,
    TEMPERATURE_UNITS,
    gas_flow_to_nm3h,
    liquid_flow_to_m3h,
    pressure_from_bar_a,
    pressure_to_bar_a,
    steam_flow_to_kgh,
    temperature_from_c,
    temperature_to_c,
)
from valve_sizing import (
    SOURCE_LIBRARY,
    GasSizingInput,
    LiquidSizingInput,
    SizingResult,
    SteamSizingInput,
    size_gas_valve,
    size_liquid_valve,
    size_steam_valve,
)
from vendor_catalog import get_vendor_definition, get_vendor_options

DEFAULTS = {
    "service": "Liquid",
    "vendor_key": "fisher_globe_eqpct",
    "liquid_source": "Preset",
    "liquid_preset_label": "Su",
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
    "liquid_temp_unit": "C",
    "liquid_pres_unit": "bar_a",
    "liquid_flow_unit": "m3h",
    "gas_basis": "molar",
    "gas_temp_c": 20.0,
    "gas_p1": 8.0,
    "gas_p2": 6.0,
    "gas_flow_nm3h": 800.0,
    "gas_pipe_in_mm": 80.0,
    "gas_pipe_out_mm": 80.0,
    "gas_temp_unit": "C",
    "gas_pres_unit": "bar_a",
    "gas_flow_unit": "nm3h",
    "steam_flow_kgh": 2500.0,
    "steam_temp_c": 220.0,
    "steam_p1": 12.0,
    "steam_p2": 8.0,
    "steam_temp_unit": "C",
    "steam_pres_unit": "bar_a",
    "steam_flow_unit": "kgh",
    "design_margin": 15.0,
    "flow_characteristic": "equal_percentage",
}


def _unit_key(label: str, unit_map: dict[str, str]) -> str:
    reverse = {label_value: key for key, label_value in unit_map.items()}
    return reverse[label]


def _unit_selectors(prefix: str, flow_units: dict[str, str]) -> tuple[str, str, str]:
    """Render temperature / pressure / flow unit selectors for a service."""
    u1, u2, u3 = st.columns(3)
    temp_label = u1.selectbox("Sicaklik birimi", options=list(TEMPERATURE_UNITS.values()), key=f"{prefix}_temp_unit")
    pres_label = u2.selectbox("Basinc birimi", options=list(PRESSURE_UNITS.values()), key=f"{prefix}_pres_unit")
    flow_label = u3.selectbox("Debi birimi", options=list(flow_units.values()), key=f"{prefix}_flow_unit")
    if _unit_key(pres_label, PRESSURE_UNITS).endswith("_g"):
        st.caption("Gauge basinc degerleri 1.01325 bar atmosfer basinciyla mutlak degere cevrilir.")
    return (
        _unit_key(temp_label, TEMPERATURE_UNITS),
        _unit_key(pres_label, PRESSURE_UNITS),
        _unit_key(flow_label, flow_units),
    )


def _live_render(service: str, result: SizingResult, fluid_summary: dict) -> None:
    """Persist and render a freshly computed result (live calculation)."""
    st.session_state.last_result = result
    st.session_state.last_fluid_summary = fluid_summary
    st.session_state.last_report = build_report(service, fluid_summary, result)
    render_result(result)


def _init_state() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("gas_rows", DEFAULT_GAS_ROWS)
    st.session_state.setdefault("gas_valid", True)
    st.session_state.setdefault("last_result", None)
    st.session_state.setdefault("last_report", "")
    st.session_state.setdefault("last_fluid_summary", None)


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


def render_result(result: SizingResult) -> None:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Hesaplama Sonuçları")

    # Enhanced metrics display
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="metric-card"><h4>Gerekli Cv</h4><p>{result["required_cv"]:.3f}</p></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><h4>Gerekli Kv</h4><p>{result["required_kv"]:.3f}</p></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(
            f'<div class="metric-card"><h4>Seçilen Vana</h4>'
            f'<p>DN{result["valve_dn_mm"]} / {result["valve_inch"]}</p></div>',
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(f'<div class="metric-card"><h4>Rated Cv</h4><p>{result["rated_cv"]:.3f}</p></div>', unsafe_allow_html=True)

    # Enhanced visualization: Bar chart for Cv comparison
    cv_data = pd.DataFrame({
        'Type': ['Required Cv', 'Rated Cv'],
        'Value': [result["required_cv"], result["rated_cv"]]
    })
    st.bar_chart(cv_data.set_index('Type'), use_container_width=True)

    st.markdown("**Sonuç Özeti**")
    st.json(
        {
            "service": result["service"],
            "delta_p_bar": round(result["delta_p_bar"], 5),
            "is_choked": result["is_choked"],
            "opening_percent": round(result["opening_percent"], 1),
            "design_margin_pct": result["design_margin_pct"],
            "cv_ratio": round(result["cv_ratio"], 3),
            "pipe_out_velocity_m_s": round(result["velocity"]["pipe_out_m_s"], 2) if result.get("velocity") else None,
            "mach_outlet": round(result["velocity"]["mach_outlet"], 3) if result.get("velocity") and "mach_outlet" in result["velocity"] else None,
            "warning": result.get("warning", ""),
        }
    )

    est_cols = st.columns(2)
    with est_cols[0]:
        st.markdown("**Tahmini Gürültü (est.)**")
        if result.get("noise_db") is not None:
            st.metric("Valve noise", f"{result['noise_db']:.1f} dB(A)")
            st.caption("IEC 60534-8 tahmini; low-noise trim için vendor doğrulaması gerekir.")
        else:
            st.write("-")
    with est_cols[1]:
        st.markdown("**Tahmini Aktüatör (est.)**")
        thrust = result.get("actuator_thrust_n")
        if isinstance(thrust, dict):
            st.metric("Toplam kuvvet", f"{thrust.get('total_n', 0.0):.1f} N")
            st.caption("Statik tahmin; dinamik kuvvet ve bench-set için vendor doğrulaması gerekir.")
        else:
            st.write("-")

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
            [{"Parameter": k, "Value": v} for k, v in result.get("intermediate_values", {}).items()]
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
            st.write(f"- Onerilen sizdirmazlik sinifi: {spec['leakage_class_recommended']}")
            st.write(f"- Onerilen fail-safe: {spec['fail_safe_recommended']}")

    if result.get("warning"):
        st.warning(result["warning"])

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
        uploaded = st.file_uploader("Proje JSON yukle", type=["json"])
        if uploaded is not None:
            try:
                loaded = load_project_json(uploaded.getvalue().decode("utf-8"))
                for key, value in loaded["data"].items():
                    st.session_state[key] = value
                st.sidebar.success("Proje verisi yuklendi. Gerekirse sayfayi yeniden hesaplayin.")
            except Exception as exc:
                st.sidebar.error(f"Yukleme hatasi: {exc}")


def render_report_tools() -> None:
    if st.session_state.last_report:
        st.sidebar.download_button(
            "Raporu indir",
            st.session_state.last_report,
            file_name="control_valve_sizing_report.md",
            mime="text/markdown",
        )


def render_source_library() -> None:
    with st.sidebar.expander("Kaynak Kutuphanesi", expanded=False):
        for source in SOURCE_LIBRARY.values():
            st.write(f"- [{source['title']}]({source['url']})")
            st.caption(source["note"])


def render_liquid_section(vendor_key: str) -> tuple[dict | None, dict]:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Sivi Akiskan")
    source = st.selectbox("Akiskan tanimi", ["Preset", "CoolProp pure fluid", "Custom"], key="liquid_source")
    temp_unit, pres_unit, flow_unit = _unit_selectors("liquid", LIQUID_FLOW_UNITS)
    temp_label = TEMPERATURE_UNITS[temp_unit]
    pres_label = PRESSURE_UNITS[pres_unit]
    flow_label = LIQUID_FLOW_UNITS[flow_unit]
    c1, c2 = st.columns(2)
    temperature_c = temperature_to_c(c1.number_input(f"Sicaklik [{temp_label}]", key="liquid_temp_c", step=1.0), temp_unit)
    inlet_pressure = pressure_to_bar_a(
        c2.number_input(f"Giris P [{pres_label}]", key="liquid_p1", min_value=0.001, step=0.1), pres_unit
    )

    density_default = st.session_state.liquid_density
    pv_default = st.session_state.liquid_pv
    pc_default = st.session_state.liquid_pc
    mu_default = st.session_state.liquid_mu
    fluid_label: str = "Custom liquid"

    if source == "Preset":
        preset_map = {v["label"]: k for k, v in LIQUID_PRESETS.items()}
        label = st.selectbox("Preset", list(preset_map.keys()), key="liquid_preset_label")
        preset = get_liquid_preset(preset_map[label])
        density_default = preset["density_kg_m3"]
        pv_default = preset["vapor_pressure_bar_a"]
        pc_default = preset["critical_pressure_bar_a"]
        mu_default = preset["viscosity_pa_s"]
        fluid_label = str(label)
    elif source == "CoolProp pure fluid":
        fluid = st.selectbox("CoolProp fluid", list_coolprop_fluids(), index=list_coolprop_fluids().index("Water"))
        fluid_label = fluid
        try:
            props = get_pure_fluid_state(fluid, inlet_pressure, temperature_c)
            density_default = props["density_kg_m3"]
            pv_default = props["vapor_pressure_bar_a"]
            pc_default = props["critical_pressure_bar_a"]
            mu_default = props["viscosity_pa_s"]
            st.caption(
                f"Oto ozellikler: rho={density_default:.2f} kg/m3, Pv={pressure_from_bar_a(pv_default, pres_unit):.4f} {pres_label}, "
                f"Pc={pressure_from_bar_a(pc_default, pres_unit):.3f} {pres_label}, mu={mu_default:.6g} Pa.s"
            )
        except Exception as exc:
            st.warning(f"CoolProp ozellikleri okunamadi: {exc}")

    c3, c4, c5, c6 = st.columns(4)
    density = c3.number_input("Yogunluk [kg/m3]", value=float(density_default), key="liquid_density", min_value=0.001, step=1.0)
    vapor_pressure = pressure_to_bar_a(
        c4.number_input(f"Buhar basinci [{pres_label}]", value=float(pv_default), key="liquid_pv", min_value=0.0, step=0.01), pres_unit
    )
    critical_pressure = pressure_to_bar_a(
        c5.number_input(f"Kritik basinc [{pres_label}]", value=float(pc_default), key="liquid_pc", min_value=0.001, step=0.1), pres_unit
    )
    viscosity = c6.number_input("Viskozite [Pa.s]", value=float(mu_default), key="liquid_mu", min_value=1e-7, step=0.0001, format="%.7f")

    st.markdown("**Proses Verileri**")
    p2, q, d1, d2 = st.columns(4)
    flow_value = q.number_input(f"Debi [{flow_label}]", key="liquid_flow_m3h", min_value=0.0001, step=1.0)
    flow_m3h = liquid_flow_to_m3h(flow_value, flow_unit, density_kg_m3=density)
    outlet_pressure = pressure_to_bar_a(
        p2.number_input(f"Cikis P [{pres_label}]", key="liquid_p2", min_value=0.001, step=0.1), pres_unit
    )
    pipe_in_mm = d1.number_input("Hat giris capi [mm]", key="liquid_pipe_in_mm", min_value=1.0, step=1.0)
    pipe_out_mm = d2.number_input("Hat cikis capi [mm]", key="liquid_pipe_out_mm", min_value=1.0, step=1.0)

    vendor = get_vendor_definition(vendor_key)
    st.caption(f"Vendor representative data: {vendor.vendor} / {vendor.style}, FL={vendor.fl}, Fd={vendor.fd}")

    fluid_summary = {
        "Fluid": fluid_label,
        f"Temperature [{temp_label}]": f"{temperature_from_c(temperature_c, temp_unit):.3f}",
        "Density [kg/m3]": f"{density:.4f}",
        f"Pv [{pres_label}]": f"{pressure_from_bar_a(vapor_pressure, pres_unit):.5f}",
        f"Pc [{pres_label}]": f"{pressure_from_bar_a(critical_pressure, pres_unit):.5f}",
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
    except Exception as exc:
        st.error(f"Sivi sizing hesaplamasi yapilirken hata olustu: {exc}")
        st.session_state.last_result = None

    st.markdown('</div>', unsafe_allow_html=True)
    valid = st.session_state.last_result and st.session_state.last_result["service"] == "liquid"
    return (st.session_state.last_result if valid else None), fluid_summary


def validate_gas_composition():
    total_pct = 0.0
    gas_options = set(list_coolprop_fluids())
    valid = True
    for row in st.session_state.gas_rows:
        component = str(row.get("component", "")).strip()
        fraction = row.get("fraction_pct", 0)
        try:
            fraction = float(fraction)
        except (TypeError, ValueError):
            valid = False
            continue
        if component not in gas_options or fraction < 0.0:
            valid = False
        total_pct += fraction
    if abs(total_pct - 100.0) > 1e-6:
        valid = False
    st.session_state.gas_valid = valid


def render_gas_section(vendor_key: str) -> tuple[dict | None, dict | None]:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Gaz Akiskan ve Kompozisyon")
    temp_unit, pres_unit, flow_unit = _unit_selectors("gas", GAS_FLOW_UNITS)
    temp_label = TEMPERATURE_UNITS[temp_unit]
    pres_label = PRESSURE_UNITS[pres_unit]
    flow_label = GAS_FLOW_UNITS[flow_unit]
    c1, c2, c3, c4 = st.columns(4)
    basis = c1.radio("Kompozisyon bazisi", ["molar", "mass"], key="gas_basis", horizontal=True)
    temperature_c = temperature_to_c(c2.number_input(f"Sicaklik [{temp_label}]", key="gas_temp_c", step=1.0), temp_unit)
    inlet_pressure = pressure_to_bar_a(
        c3.number_input(f"Giris P [{pres_label}]", key="gas_p1", min_value=0.001, step=0.1), pres_unit
    )
    outlet_pressure = pressure_to_bar_a(
        c4.number_input(f"Cikis P [{pres_label}]", key="gas_p2", min_value=0.001, step=0.1), pres_unit
    )
    flow_value = st.number_input(f"Debi [{flow_label}]", key="gas_flow_nm3h", min_value=0.0001, step=10.0)

    gas_options = list_coolprop_fluids()
    gas_preset_options = GAS_PRESET_NAMES + ["Özel (Custom)"]
    if "gas_preset" not in st.session_state:
        st.session_state.gas_preset = "Özel (Custom)"

    def _on_gas_preset_change() -> None:
        name = st.session_state.get("gas_preset", "")
        if name in GAS_PRESETS:
            st.session_state.gas_rows = [dict(r) for r in GAS_PRESETS[name]["components"]]

    st.selectbox("Gaz preset", gas_preset_options, key="gas_preset", on_change=_on_gas_preset_change)
    gas_df = pd.DataFrame(st.session_state.gas_rows)
    edited = st.data_editor(
        gas_df,
        num_rows="dynamic",
        column_config={
            "component": st.column_config.SelectboxColumn("Bilesen", options=gas_options, required=True),
            "fraction_pct": st.column_config.NumberColumn("Yuzde [%]", min_value=0.0, max_value=100.0, step=0.1, format="%.4f"),
        },
        key=f"gas_editor_{st.session_state.get('gas_preset', '')}",
        on_change=validate_gas_composition,
    )
    st.session_state.gas_rows = edited.to_dict("records")

    # Real-time validation display
    total_pct = float(edited["fraction_pct"].fillna(0.0).sum()) if "fraction_pct" in edited else 0.0
    if abs(total_pct - 100.0) < 1e-6:
        st.markdown(f'<p class="success-msg">Toplam kompozisyon: {total_pct:.4f}%</p>', unsafe_allow_html=True)
    else:
        st.markdown(f'<p class="error-msg">Toplam kompozisyon 100% olmalı. Mevcut toplam: {total_pct:.4f}%</p>', unsafe_allow_html=True)

    vendor = get_vendor_definition(vendor_key)
    st.caption(f"Vendor representative data: {vendor.vendor} / {vendor.style}, xT={vendor.xt}, Fd={vendor.fd}")
    g1, g2 = st.columns(2)
    pipe_in_mm = g1.number_input("Hat giris capi [mm]", key="gas_pipe_in_mm", min_value=1.0, step=1.0)
    pipe_out_mm = g2.number_input("Hat cikis capi [mm]", key="gas_pipe_out_mm", min_value=1.0, step=1.0)

    if not getattr(st.session_state, "gas_valid", False):
        st.error("Gaz kompozisyonu geçersiz: toplam yüzde 100 olmalı.")
        st.session_state.last_result = None
    else:
        try:
            summary = evaluate_gas_mixture(st.session_state.gas_rows, basis, inlet_pressure, temperature_c)
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

            result = size_gas_valve(
                GasSizingInput(
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
                ),
                valve_series=list(vendor.sizes),
                valve_meta=_vendor_meta(vendor_key),
                design_margin_pct=st.session_state.design_margin,
                flow_characteristic=st.session_state.flow_characteristic,
            )
            _live_render("Gas", result, fluid_summary)
        except Exception as exc:
            st.error(f"Gaz sizing hesaplamasi yapilirken hata olustu: {exc}")
            st.session_state.last_result = None

    st.markdown('</div>', unsafe_allow_html=True)
    valid = st.session_state.last_result and st.session_state.last_result["service"] == "gas"
    return (st.session_state.last_result if valid else None), st.session_state.last_fluid_summary


def render_steam_section(vendor_key: str) -> tuple[dict | None, dict]:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Buhar")
    temp_unit, pres_unit, flow_unit = _unit_selectors("steam", STEAM_FLOW_UNITS)
    temp_label = TEMPERATURE_UNITS[temp_unit]
    pres_label = PRESSURE_UNITS[pres_unit]
    flow_label = STEAM_FLOW_UNITS[flow_unit]
    c1, c2, c3, c4 = st.columns(4)
    flow_kg_h = steam_flow_to_kgh(c1.number_input(f"Debi [{flow_label}]", key="steam_flow_kgh", min_value=0.0001, step=100.0), flow_unit)
    temperature_c = temperature_to_c(c2.number_input(f"Sicaklik [{temp_label}]", key="steam_temp_c", step=1.0), temp_unit)
    inlet_pressure = pressure_to_bar_a(
        c3.number_input(f"Giris P [{pres_label}]", key="steam_p1", min_value=0.001, step=0.1), pres_unit
    )
    outlet_pressure = pressure_to_bar_a(
        c4.number_input(f"Cikis P [{pres_label}]", key="steam_p2", min_value=0.001, step=0.1), pres_unit
    )

    vendor = get_vendor_definition(vendor_key)
    st.caption(f"Vendor representative data: {vendor.vendor} / {vendor.style}, xT={vendor.xt}")

    gamma = 1.30
    z_value = 1.0
    try:
        props = get_pure_fluid_state("Water", inlet_pressure, temperature_c)
        gamma = props["specific_heat_ratio"]
        z_value = props["z"]
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

    # Custom CSS for UI/UX improvements
    st.markdown("""
    <style>
    .card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        background-color: #f9f9f9;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .metric-card {
        text-align: center;
        padding: 10px;
        border: 1px solid #eee;
        border-radius: 5px;
        margin: 5px;
        background-color: white;
    }
    @media (max-width: 768px) {
        .card {
            padding: 10px;
            margin: 5px 0;
        }
        .stButton button {
            width: 100%;
        }
        .stColumns {
            flex-direction: column;
        }
    }
    .stTextInput, .stNumberInput, .stSelectbox, .stRadio {
        margin-bottom: 10px;
    }
    .error-msg {
        color: red;
        font-weight: bold;
    }
    .success-msg {
        color: green;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

    _init_state()

    st.title("Control Valve Sizing")
    st.caption("Kaynakli Streamlit arayuzu: liquid, gas ve steam servisleri icin IEC/ISA'ya yaklastirilmis sizing uygulamasi.")

    service_index = ["Liquid", "Gas", "Steam"].index(st.session_state.service)
    st.session_state.service = st.sidebar.radio("Servis tipi", ["Liquid", "Gas", "Steam"], index=service_index)
    vendor_key = st.sidebar.selectbox(
        "Vendor representative trim",
        get_vendor_options(),
        index=get_vendor_options().index(st.session_state.vendor_key),
    )
    st.session_state.vendor_key = vendor_key

    st.sidebar.markdown("**Tasarim secenekleri**")
    st.sidebar.number_input("Tasarim marji [%]", key="design_margin", min_value=0.0, max_value=100.0, step=5.0)
    st.sidebar.selectbox(
        "Akis karakteristigi",
        ("equal_percentage", "linear"),
        key="flow_characteristic",
    )

    render_source_library()
    render_report_tools()

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
        "liquid_temp_unit": st.session_state.liquid_temp_unit,
        "liquid_pres_unit": st.session_state.liquid_pres_unit,
        "liquid_flow_unit": st.session_state.liquid_flow_unit,
        "gas_basis": st.session_state.gas_basis,
        "gas_temp_c": st.session_state.gas_temp_c,
        "gas_p1": st.session_state.gas_p1,
        "gas_p2": st.session_state.gas_p2,
        "gas_flow_nm3h": st.session_state.gas_flow_nm3h,
        "gas_pipe_in_mm": st.session_state.gas_pipe_in_mm,
        "gas_pipe_out_mm": st.session_state.gas_pipe_out_mm,
        "gas_temp_unit": st.session_state.gas_temp_unit,
        "gas_pres_unit": st.session_state.gas_pres_unit,
        "gas_flow_unit": st.session_state.gas_flow_unit,
        "steam_flow_kgh": st.session_state.steam_flow_kgh,
        "steam_temp_c": st.session_state.steam_temp_c,
        "steam_p1": st.session_state.steam_p1,
        "steam_p2": st.session_state.steam_p2,
        "steam_temp_unit": st.session_state.steam_temp_unit,
        "steam_pres_unit": st.session_state.steam_pres_unit,
        "steam_flow_unit": st.session_state.steam_flow_unit,
    }
    render_project_tools(st.session_state.service, payload)

    if st.session_state.service == "Liquid":
        render_liquid_section(vendor_key)
    elif st.session_state.service == "Gas":
        render_gas_section(vendor_key)
    else:
        render_steam_section(vendor_key)

    with st.expander("Termal Genlesme (boru hatti)", expanded=False):
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
            expansion_mm = pipe_linear_expansion(te_len, delta_t, te_mat) * 1000.0
            stress_mpa = pipe_thermal_stress(delta_t, te_mat)
            c1, c2, c3 = st.columns(3)
            c1.metric("Uzama [mm]", f"{expansion_mm:.2f}")
            c2.metric("Termal gerilme [MPa]", f"{stress_mpa:.1f}")
            c3.metric("dT [C]", f"{delta_t:.1f}")
            st.caption("Genlesme kompansatoru / loop gereksinimi icin boru hatti mekanik analizi yapilmalidir.")

    with st.expander("Notlar", expanded=False):
        st.markdown(
            """
            - Vendor katalog verileri: Emerson Fisher (4 trim), Metso/Valmet (3), SAMSON (3), ARCA (2) — toplam 12 representative trim.
            - Hesap motoru IEC 60534 / ISA sizing mantigina yaklastirilmistir.
            - Final secim, seat leakage, body size, trim noise ve malzeme icin vendor yazilimiyle dogrulanmalidir.
            """
        )


if __name__ == "__main__":
    main()
