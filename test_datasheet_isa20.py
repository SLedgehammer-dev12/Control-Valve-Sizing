"""Unit tests for ISA Form 20 Control Valve Specification Sheet generator."""

from datasheet_isa20 import (
    build_isa20_datasheet,
    generate_isa20_html,
    generate_isa20_markdown,
)
from valve_sizing import LiquidSizingInput, size_liquid_valve


def test_build_isa20_datasheet_single_case():
    inp = LiquidSizingInput(
        flow_m3h=75.0,
        inlet_pressure_bar_a=8.0,
        outlet_pressure_bar_a=4.5,
        density_kg_m3=990.0,
        vapor_pressure_bar_a=0.03,
        critical_pressure_bar_a=220.64,
        viscosity_pa_s=0.0008,
        fl=0.9,
    )
    result = size_liquid_valve(inp)

    sheet = build_isa20_datasheet(
        tag_number="FV-101",
        service_description="Cooling Water Supply",
        line_number='4"-CW-1001-A1',
        pid_number="PID-CW-01",
        service_type="liquid",
        fluid_name="Water",
        sizing_result=result,
    )

    assert sheet.tag_number == "FV-101"
    assert sheet.valve_dn_mm > 0
    assert len(sheet.cases) == 1

    row = sheet.cases[0]
    assert row.flow == 75.0
    assert row.p1_bar_a == 8.0
    assert row.p2_bar_a == 4.5
    assert row.density_or_mw == 990.0
    assert row.calculated_cv == result.required_cv


def test_build_isa20_datasheet_multicase():
    cases = [
        {"name": "Min", "flow": 30.0, "p1_bar_a": 8.5, "p2_bar_a": 5.0, "required_cv": 15.0, "opening_percent": 35.0},
        {"name": "Normal", "flow": 60.0, "p1_bar_a": 8.0, "p2_bar_a": 4.5, "required_cv": 32.0, "opening_percent": 65.0},
        {"name": "Max", "flow": 90.0, "p1_bar_a": 7.5, "p2_bar_a": 4.0, "required_cv": 52.0, "opening_percent": 88.0},
    ]

    sheet = build_isa20_datasheet(
        tag_number="PV-201",
        service_description="Fuel Gas to Boiler",
        line_number='3"-FG-2002-B1',
        pid_number="PID-FG-02",
        service_type="gas",
        fluid_name="Natural Gas",
        sizing_result={"rated_cv": 60.0, "valve_dn_mm": 50, "valve_inch": '2"'},
        multicase_cases=cases,
    )

    assert len(sheet.cases) == 3
    assert sheet.cases[0].case_name == "Min"
    assert sheet.cases[1].case_name == "Normal"
    assert sheet.cases[2].case_name == "Max"


def test_generate_isa20_markdown_and_html():
    sheet = build_isa20_datasheet(
        tag_number="TV-301",
        service_description="Steam to Reboiler",
        line_number='2"-ST-3001-C1',
        pid_number="PID-ST-03",
        service_type="steam",
        fluid_name="Steam",
        sizing_result={"rated_cv": 40.0, "valve_dn_mm": 50, "valve_inch": '2"', "required_cv": 25.0},
    )

    md = generate_isa20_markdown(sheet)
    assert "# ISA-20 KONTROL VANASI VERİ SAYFASI" in md
    assert "TV-301" in md
    assert "Steam to Reboiler" in md
    assert "| Parametre | Normal (Duty) |" in md

    html = generate_isa20_html(sheet)
    assert "<table" in html
    assert "TV-301" in html
    assert "ISA-20" in html


def test_reporting_isa20_with_multicase():
    from reporting import build_isa20_html_report, build_isa20_report

    mock_res = {"service": "liquid", "rated_cv": 60.0, "required_cv": 35.0}
    cases = [
        {"name": "Min", "flow": 20.0, "p1_bar_a": 6.0, "p2_bar_a": 4.0},
        {"name": "Normal", "flow": 50.0, "p1_bar_a": 6.0, "p2_bar_a": 4.0},
        {"name": "Max", "flow": 80.0, "p1_bar_a": 5.8, "p2_bar_a": 4.0},
    ]
    md = build_isa20_report(mock_res, tag="FCV-100", multicase_cases=cases)
    assert "| Min | Normal | Max |" in md
    assert "FCV-100" in md

    html = build_isa20_html_report(mock_res, tag="FCV-100", multicase_cases=cases)
    assert "Min" in html
    assert "Normal" in html
    assert "Max" in html
    assert "FCV-100" in html

