from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from project_io import dump_project_json, load_project_json
from reporting import build_report
from valve_sizing import LiquidSizingInput, size_liquid_valve
from vendor_catalog import get_vendor_definition

APP_FILE = Path(__file__).with_name("app_web.py")


def test_project_json_round_trip():
    payload = {
        "service": "Liquid",
        "vendor_key": "fisher_globe_eqpct",
        "liquid_flow_m3h": 25.0,
        "liquid_p1": 8.0,
        "liquid_p2": 5.0,
    }
    dumped = dump_project_json("Liquid", payload)
    loaded = load_project_json(dumped)
    assert loaded["project_type"] == "control_valve_sizing"
    assert loaded["schema_version"] == 1
    assert loaded["service"] == "liquid"
    assert loaded["data"]["liquid_flow_m3h"] == 25.0


def test_load_project_json_accepts_legacy_without_schema_version():
    legacy = '{"project_type":"control_valve_sizing","service":"Liquid","data":{"liquid_flow_m3h":25.0,"liquid_p1":8.0,"liquid_p2":5.0}}'
    loaded = load_project_json(legacy)
    assert loaded["schema_version"] == 1


def test_load_project_json_rejects_newer_schema():
    newer = (
        '{"project_type":"control_valve_sizing","schema_version":999,"service":"Liquid",'
        '"data":{"liquid_flow_m3h":25.0,"liquid_p1":8.0,"liquid_p2":5.0}}'
    )
    with pytest.raises(ValueError, match="daha yeni bir schema"):
        load_project_json(newer)


def test_load_project_json_rejects_missing_required_keys():
    incomplete = (
        '{"project_type":"control_valve_sizing","schema_version":1,"service":"Gas",'
        '"data":{"gas_flow_nm3h":100.0}}'
    )
    with pytest.raises(ValueError, match="eksik alanlar"):
        load_project_json(incomplete)


def test_load_project_json_rejects_invalid_project_type():
    invalid = '{"project_type":"other_project","service":"Liquid","data":{}}'
    with pytest.raises(ValueError, match="control valve sizing proje dosyasi degil"):
        load_project_json(invalid)


def test_load_project_json_rejects_missing_data():
    invalid = '{"project_type":"control_valve_sizing","service":"Gas"}'
    with pytest.raises(ValueError, match="Proje data alanı bir JSON nesnesi olmalidir"):
        load_project_json(invalid)


def test_report_contains_result_and_sources():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=25.0,
            inlet_pressure_bar_a=8.0,
            outlet_pressure_bar_a=5.0,
            density_kg_m3=998.0,
            vapor_pressure_bar_a=0.03,
            critical_pressure_bar_a=220.64,
            viscosity_pa_s=0.00089,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
            pipe_inlet_diameter_mm=80.0,
            pipe_outlet_diameter_mm=80.0,
        ),
        valve_series=list(vendor.sizes),
        valve_meta={"vendor": vendor.vendor, "source_url": vendor.source_url},
    )
    report = build_report("Liquid", {"Fluid": "Water"}, result)
    assert "Control Valve Sizing Report" in report
    assert "Required Cv" in report
    assert "Sources" in report
    assert vendor.vendor in report


def test_report_flashing_includes_two_phase_velocity():
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=40.0,
            inlet_pressure_bar_a=10.0,
            outlet_pressure_bar_a=0.2,
            density_kg_m3=950.0,
            vapor_pressure_bar_a=2.5,
            critical_pressure_bar_a=46.0,
            viscosity_pa_s=0.0008,
            fl=vendor.fl or 0.85,
            fd=vendor.fd or 1.0,
            temperature_c=120.0,
        ),
        valve_series=list(vendor.sizes),
    )
    report = build_report("Liquid", None, result)
    assert "Two-phase outlet velocity" in report
    assert "API 14E erosion limit" in report
    assert "Erosion risk" in report


def test_report_scalar_actuator_thrust_branch():
    import dataclasses

    vendor = get_vendor_definition("fisher_globe_eqpct")
    result = size_liquid_valve(
        LiquidSizingInput(25.0, 8.0, 5.0, 998.0, 0.023, 220.64, 0.00089, fl=vendor.fl or 0.85, fd=vendor.fd or 1.0),
        valve_series=list(vendor.sizes),
    )
    modified = dataclasses.replace(result, extra={**result.extra, "actuator_thrust_n": 1234.5})
    report = build_report("Liquid", None, modified)
    assert "Total estimated thrust: 1234.5 N" in report


def test_streamlit_app_loads_and_shows_title():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    assert not at.exception
    assert at.title[0].value == "Control Valve Sizing"
    assert at.sidebar.radio[0].value == "Liquid"


def test_streamlit_liquid_calculation_shows_metrics():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    # Live calculation renders results on first run without clicking a button
    markdown_content = ' '.join([m.value for m in at.markdown if hasattr(m, 'value')])
    assert "Gerekli Cv" in markdown_content
    assert "Gerekli Kv" in markdown_content
    assert "DN40" in markdown_content or "Rated Cv" in markdown_content
    assert at.session_state["last_result"]["service"] == "liquid"


def test_streamlit_unit_selectors_present():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    selector_labels = {sb.label for sb in at.selectbox if sb.label}
    assert "Sicaklik birimi" in selector_labels
    assert "Basinc birimi" in selector_labels
    assert "Debi birimi" in selector_labels


def test_streamlit_liquid_gpm_unit_live_recalc():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    flow_sb = next(sb for sb in at.selectbox if sb.label == "Debi birimi")
    flow_sb.set_value("US gpm")
    at.run()
    _set_number_input(at, "liquid_flow_m3h", 110.0)
    at.run()
    assert not at.exception
    assert at.session_state["last_result"]["service"] == "liquid"
    assert at.session_state["liquid_flow_unit"] == "US gpm"


def test_streamlit_can_switch_to_gas_page():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    at.sidebar.radio[0].set_value("Gas")
    at.run()
    assert not at.exception
    assert at.subheader[0].value == "Gaz Akiskan ve Kompozisyon"


def test_streamlit_gas_preset_selector_present():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    at.sidebar.radio[0].set_value("Gas")
    at.run()
    presets = [sb.options for sb in at.selectbox if "Gaz preset" in (sb.label or "")]
    assert presets, "Gas preset selectbox not found"
    assert any("H2-NG" in name for name in presets[0])
    assert "Sentez Gazi (Syngas)" in presets[0]


def test_streamlit_gas_preset_loads_rows():
    from config import GAS_PRESETS

    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    at.sidebar.radio[0].set_value("Gas")
    at.run()
    sb = next(sb for sb in at.selectbox if "Gaz preset" in (sb.label or ""))
    sb.set_value("Sentez Gazi (Syngas)")
    at.run()
    assert not at.exception
    loaded = at.session_state["gas_rows"]
    assert len(loaded) == len(GAS_PRESETS["Sentez Gazi (Syngas)"]["components"])
    assert sum(float(r["fraction_pct"]) for r in loaded) == pytest.approx(100.0)


def _set_number_input(at, key: str, value: float) -> None:
    at.run()
    next(n for n in at.number_input if n.key == key).set_value(value)


def test_streamlit_gas_preset_calculation_shows_result():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    at.sidebar.radio[0].set_value("Gas")
    at.run()
    sb = next(sb for sb in at.selectbox if "Gaz preset" in (sb.label or ""))
    sb.set_value("Doğal Gaz")
    at.run()
    for key, val in [("gas_flow_nm3h", 800.0), ("gas_p1", 8.0), ("gas_p2", 6.0), ("gas_temp_c", 20.0)]:
        _set_number_input(at, key, val)
    at.run()
    assert not at.exception
    markdown = " ".join([m.value for m in at.markdown if hasattr(m, "value")])
    assert "Gerekli Cv" in markdown
    assert at.session_state["last_result"]["service"] == "gas"


def test_streamlit_gas_invalid_composition_shows_error():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    at.sidebar.radio[0].set_value("Gas")
    at.run()
    at.session_state["gas_valid"] = False
    at.run()
    errors = [e.value for e in at.error]
    assert any("kompozisyonu geçersiz" in e for e in errors)
    assert at.session_state["last_result"] is None


def test_streamlit_steam_calculation_shows_metrics():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    at.sidebar.radio[0].set_value("Steam")
    at.run()
    for key, val in [("steam_flow_kgh", 1000.0), ("steam_p1", 8.0), ("steam_p2", 6.0), ("steam_temp_c", 170.0)]:
        _set_number_input(at, key, val)
    at.run()
    assert not at.exception
    markdown = " ".join([m.value for m in at.markdown if hasattr(m, "value")])
    assert "Gerekli Cv" in markdown
    assert at.session_state["last_result"]["service"] == "steam"


def test_streamlit_gas_scfh_unit_live_recalc():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    at.sidebar.radio[0].set_value("Gas")
    at.run()
    flow_sb = next(sb for sb in at.selectbox if sb.label == "Debi birimi")
    flow_sb.set_value("scfh")
    at.run()
    _set_number_input(at, "gas_flow_nm3h", 28300.0)
    at.run()
    assert not at.exception
    assert at.session_state["last_result"]["service"] == "gas"
    assert at.session_state["gas_flow_unit"] == "scfh"


def test_streamlit_thermal_expansion_section():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    next(b for b in at.button if "Termal genlesme" in (b.label or "")).click()
    at.run()
    metric_labels = [m.label for m in at.metric]
    assert any("Uzama" in label for label in metric_labels)
    assert any("Termal gerilme" in label for label in metric_labels)


def test_streamlit_multicase_section():
    at = AppTest.from_file(str(APP_FILE), default_timeout=10)
    at.run()
    btn = next((b for b in at.button if "Coklu Durum Boyutlandirma" in (b.label or "")), None)
    assert btn is not None
    btn.click()
    at.run()
    assert not at.exception
    metric_labels = [m.label for m in at.metric]
    assert any("Turndown" in label for label in metric_labels)
    assert len(at.dataframe) > 0



def test_build_joule_thomson_report():
    from joule_thomson import calc_joule_thomson_drop
    from reporting import build_joule_thomson_report

    res = calc_joule_thomson_drop("Methane", 50.0, 10.0, 20.0)
    rep = build_joule_thomson_report(res)
    assert "Joule-Thomson & Gaz Hidrat Raporu" in rep
    assert "Methane" in rep
    assert "T1" in rep


def test_build_multicase_report():
    from multi_case import OperatingCase, size_multicase
    from reporting import build_multicase_report

    cases = [
        OperatingCase("Min", 15.0, 6.0, 4.0, 25.0),
        OperatingCase("Normal", 50.0, 6.0, 4.0, 25.0),
        OperatingCase("Max", 80.0, 5.8, 4.0, 25.0),
    ]
    fluid_data = {
        "density_kg_m3": 998.0,
        "vapor_pressure_bar_a": 0.023,
        "critical_pressure_bar_a": 220.64,
        "viscosity_pa_s": 0.001,
        "fl": 0.9,
    }
    res = size_multicase("liquid", cases, fluid_data)
    rep = build_multicase_report(res)
    assert "Multi-Case" in rep
    assert "Turndown" in rep
    assert "DN" in rep

