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
    assert loaded["service"] == "Liquid"
    assert loaded["data"]["liquid_flow_m3h"] == 25.0


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


def test_streamlit_app_loads_and_shows_title():
    at = AppTest.from_file(str(APP_FILE))
    at.run()
    assert not at.exception
    assert at.title[0].value == "Control Valve Sizing"
    assert at.sidebar.radio[0].value == "Liquid"


def test_streamlit_liquid_calculation_shows_metrics():
    at = AppTest.from_file(str(APP_FILE))
    at.run()
    at.button[0].click()
    at.run()
    # Updated to match new UI structure using custom HTML metric cards instead of st.metric components
    markdown_content = ' '.join([m.value for m in at.markdown if hasattr(m, 'value')])
    assert "Gerekli Cv" in markdown_content
    assert "Gerekli Kv" in markdown_content
    assert "DN40" in markdown_content or "Rated Cv" in markdown_content


def test_streamlit_can_switch_to_gas_page():
    at = AppTest.from_file(str(APP_FILE))
    at.run()
    at.sidebar.radio[0].set_value("Gas")
    at.run()
    assert not at.exception
    assert at.subheader[0].value == "Gaz Akiskan ve Kompozisyon"
