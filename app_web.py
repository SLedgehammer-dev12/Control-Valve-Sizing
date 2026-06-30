from __future__ import annotations

import pandas as pd
import streamlit as st

from config import DEFAULT_GAS_ROWS
from fluid_properties import LIQUID_PRESETS, evaluate_gas_mixture, get_liquid_preset, get_pure_fluid_state, list_coolprop_fluids
from project_io import dump_project_json, load_project_json
from reporting import build_report
from valve_sizing import SOURCE_LIBRARY, GasSizingInput, LiquidSizingInput, SizingResult, SteamSizingInput, size_gas_valve, size_liquid_valve, size_steam_valve
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
    "gas_basis": "molar",
    "gas_temp_c": 20.0,
    "gas_p1": 8.0,
    "gas_p2": 6.0,
    "gas_flow_nm3h": 800.0,
    "gas_pipe_in_mm": 80.0,
    "gas_pipe_out_mm": 80.0,
    "steam_flow_kgh": 2500.0,
    "steam_temp_c": 220.0,
    "steam_p1": 12.0,
    "steam_p2": 8.0,
}


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
        st.markdown(f'<div class="metric-card"><h4>Seçilen Vana</h4><p>DN{result["valve_dn_mm"]} / {result["valve_inch"]}</p></div>', unsafe_allow_html=True)
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
            "warning": result.get("warning", ""),
        }
    )

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
    c1, c2 = st.columns(2)
    temperature_c = c1.number_input("Sicaklik [C]", key="liquid_temp_c", step=1.0)
    inlet_pressure = c2.number_input("Giris P [bar(a)]", key="liquid_p1", min_value=0.001, step=0.1)

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
                f"Oto ozellikler: rho={density_default:.2f} kg/m3, Pv={pv_default:.4f} bar(a), Pc={pc_default:.3f} bar(a), mu={mu_default:.6g} Pa.s"
            )
        except Exception as exc:
            st.warning(f"CoolProp ozellikleri okunamadi: {exc}")

    c3, c4, c5, c6 = st.columns(4)
    density = c3.number_input("Yogunluk [kg/m3]", value=float(density_default), key="liquid_density", min_value=0.001, step=1.0)
    vapor_pressure = c4.number_input("Buhar basinci [bar(a)]", value=float(pv_default), key="liquid_pv", min_value=0.0, step=0.01)
    critical_pressure = c5.number_input("Kritik basinc [bar(a)]", value=float(pc_default), key="liquid_pc", min_value=0.001, step=0.1)
    viscosity = c6.number_input("Viskozite [Pa.s]", value=float(mu_default), key="liquid_mu", min_value=1e-7, step=0.0001, format="%.7f")

    st.markdown("**Proses Verileri**")
    p2, q, d1, d2 = st.columns(4)
    flow_m3h = q.number_input("Debi [m3/h]", key="liquid_flow_m3h", min_value=0.0001, step=1.0)
    outlet_pressure = p2.number_input("Cikis P [bar(a)]", key="liquid_p2", min_value=0.001, step=0.1)
    pipe_in_mm = d1.number_input("Hat giris capi [mm]", key="liquid_pipe_in_mm", min_value=1.0, step=1.0)
    pipe_out_mm = d2.number_input("Hat cikis capi [mm]", key="liquid_pipe_out_mm", min_value=1.0, step=1.0)

    vendor = get_vendor_definition(vendor_key)
    st.caption(f"Vendor representative data: {vendor.vendor} / {vendor.style}, FL={vendor.fl}, Fd={vendor.fd}")

    fluid_summary = {
        "Fluid": fluid_label,
        "Temperature [C]": f"{temperature_c:.3f}",
        "Density [kg/m3]": f"{density:.4f}",
        "Pv [bar(a)]": f"{vapor_pressure:.5f}",
        "Pc [bar(a)]": f"{critical_pressure:.5f}",
        "Viscosity [Pa.s]": f"{viscosity:.7g}",
    }

    if st.button("Sivi sizing hesapla", type="primary"):
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
        )
        st.session_state.last_result = result
        st.session_state.last_fluid_summary = fluid_summary
        st.session_state.last_report = build_report("Liquid", fluid_summary, result)
        render_result(result)

    st.markdown('</div>', unsafe_allow_html=True)
    return st.session_state.last_result if st.session_state.last_result and st.session_state.last_result["service"] == "liquid" else None, fluid_summary


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
    c1, c2, c3, c4 = st.columns(4)
    basis = c1.radio("Kompozisyon bazisi", ["molar", "mass"], key="gas_basis", horizontal=True)
    temperature_c = c2.number_input("Sicaklik [C]", key="gas_temp_c", step=1.0)
    inlet_pressure = c3.number_input("Giris P [bar(a)]", key="gas_p1", min_value=0.001, step=0.1)
    outlet_pressure = c4.number_input("Cikis P [bar(a)]", key="gas_p2", min_value=0.001, step=0.1)
    flow_nm3h = st.number_input("Debi [Nm3/h]", key="gas_flow_nm3h", min_value=0.0001, step=10.0)

    gas_options = list_coolprop_fluids()
    gas_df = pd.DataFrame(st.session_state.gas_rows)
    edited = st.data_editor(
        gas_df,
        num_rows="dynamic",
        column_config={
            "component": st.column_config.SelectboxColumn("Bilesen", options=gas_options, required=True),
            "fraction_pct": st.column_config.NumberColumn("Yuzde [%]", min_value=0.0, max_value=100.0, step=0.1, format="%.4f"),
        },
        key="gas_editor",
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

    if st.button("Gaz sizing hesapla", type="primary"):
        if not getattr(st.session_state, 'gas_valid', False):
            st.error("Gaz kompozisyonu geçersiz: toplam yüzde 100 olmalı.")
        else:
            try:
                summary = evaluate_gas_mixture(st.session_state.gas_rows, basis, inlet_pressure, temperature_c)
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
                )
                st.session_state.last_result = result
                st.session_state.last_fluid_summary = fluid_summary
                st.session_state.last_report = build_report("Gas", fluid_summary, result)
                render_result(result)
            except Exception as exc:
                st.error(f"Gaz sizing hesaplamasi yapilirken hata olustu: {exc}")

    st.markdown('</div>', unsafe_allow_html=True)
    return st.session_state.last_result if st.session_state.last_result and st.session_state.last_result["service"] == "gas" else None, st.session_state.last_fluid_summary


def render_steam_section(vendor_key: str) -> tuple[dict | None, dict]:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Buhar")
    c1, c2, c3, c4 = st.columns(4)
    flow_kg_h = c1.number_input("Debi [kg/h]", key="steam_flow_kgh", min_value=0.0001, step=100.0)
    temperature_c = c2.number_input("Sicaklik [C]", key="steam_temp_c", step=1.0)
    inlet_pressure = c3.number_input("Giris P [bar(a)]", key="steam_p1", min_value=0.001, step=0.1)
    outlet_pressure = c4.number_input("Cikis P [bar(a)]", key="steam_p2", min_value=0.001, step=0.1)

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

    if st.button("Buhar sizing hesapla", type="primary"):
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
        )
        st.session_state.last_result = result
        st.session_state.last_fluid_summary = fluid_summary
        st.session_state.last_report = build_report("Steam", fluid_summary, result)
        render_result(result)

    st.markdown('</div>', unsafe_allow_html=True)
    return st.session_state.last_result if st.session_state.last_result and st.session_state.last_result["service"] == "steam" else None, fluid_summary




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

    st.session_state.service = st.sidebar.radio("Servis tipi", ["Liquid", "Gas", "Steam"], index=["Liquid", "Gas", "Steam"].index(st.session_state.service))
    vendor_key = st.sidebar.selectbox("Vendor representative trim", get_vendor_options(), index=get_vendor_options().index(st.session_state.vendor_key))
    st.session_state.vendor_key = vendor_key

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
        "gas_basis": st.session_state.gas_basis,
        "gas_temp_c": st.session_state.gas_temp_c,
        "gas_p1": st.session_state.gas_p1,
        "gas_p2": st.session_state.gas_p2,
        "gas_flow_nm3h": st.session_state.gas_flow_nm3h,
        "gas_pipe_in_mm": st.session_state.gas_pipe_in_mm,
        "gas_pipe_out_mm": st.session_state.gas_pipe_out_mm,
        "steam_flow_kgh": st.session_state.steam_flow_kgh,
        "steam_temp_c": st.session_state.steam_temp_c,
        "steam_p1": st.session_state.steam_p1,
        "steam_p2": st.session_state.steam_p2,
    }
    render_project_tools(st.session_state.service, payload)

    if st.session_state.service == "Liquid":
        render_liquid_section(vendor_key)
    elif st.session_state.service == "Gas":
        render_gas_section(vendor_key)
    else:
        render_steam_section(vendor_key)

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
