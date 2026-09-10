from datasheet_isa20 import build_isa20_datasheet, generate_isa20_html, generate_isa20_markdown
from packing_emissions import recommend_packing_system
from trim_guidance import evaluate_cavitation_severity


def test_cavitation_severity_evaluation():
    safe = evaluate_cavitation_severity(sigma=2.5, delta_p_bar=2.0, p1_bar_a=6.0, pv_bar_a=0.023)
    assert safe.severity_level == "G\u00fcvenli (Kavitasyonsuz)"
    assert safe.stages_recommended == 1
    assert "Standart" in safe.trim_recommendation

    incipient = evaluate_cavitation_severity(sigma=1.7, delta_p_bar=4.0, p1_bar_a=8.0, pv_bar_a=0.023)
    assert "Ba\u015flang\u0131\u00e7" in incipient.severity_level
    assert incipient.stages_recommended == 1
    assert "Sertle\u015ftirilmi\u015f" in incipient.trim_recommendation

    constant = evaluate_cavitation_severity(sigma=1.3, delta_p_bar=15.0, p1_bar_a=20.0, pv_bar_a=0.023)
    assert "Yo\u011fun" in constant.severity_level
    assert constant.stages_recommended == 2
    assert "2-Kademeli" in constant.trim_recommendation

    choking = evaluate_cavitation_severity(sigma=0.95, delta_p_bar=60.0, p1_bar_a=70.0, pv_bar_a=0.023)
    assert "\u015eiddetli" in choking.severity_level
    assert choking.stages_recommended >= 3
    assert "Labirent" in choking.trim_recommendation

    flashing = evaluate_cavitation_severity(sigma=0.5, delta_p_bar=5.0, p1_bar_a=5.0, pv_bar_a=6.0)
    assert "Flashing" in flashing.severity_level
    assert "Angle Body" in flashing.trim_recommendation


def test_packing_emissions_selection():
    ptfe = recommend_packing_system("liquid", "Water", 25.0, 10.0)
    assert "PTFE" in ptfe.packing_type
    assert "Class BH" in ptfe.emission_class
    assert ptfe.fire_safe is False

    steam_graphite = recommend_packing_system("steam", "Steam", 350.0, 40.0)
    assert "Grafit" in steam_graphite.packing_type
    assert steam_graphite.fire_safe is True
    assert any("live loading" in r.lower() for r in steam_graphite.recommendations)

    bellows = recommend_packing_system("gas", "Chlorine", 30.0, 6.0, is_toxic_or_lethal=True)
    assert "Bellows" in bellows.packing_type or "K\u00f6r\u00fckl\u00fc" in bellows.packing_type
    assert "Class AH" in bellows.emission_class

    sour = recommend_packing_system("gas", "NaturalGas", 40.0, 50.0, is_sour_gas=True)
    assert sour.nace_mr0175_compliant is True
    assert any("NACE MR0175" in r for r in sour.recommendations)


def test_isa20_datasheet_generation():
    sizing_mock = {
        "required_cv": 45.2,
        "rated_cv": 75.0,
        "valve_dn_mm": 65,
        "valve_inch": '2 1/2"',
        "delta_p_bar": 3.0,
        "opening_percent": 68.5,
        "noise_db": 78.4,
        "valve_spec": {
            "pressure_class_recommended": "CL300",
            "derated_mawp_bar": 45.0,
            "leakage_class_recommended": "IV",
            "fail_safe_recommended": "Fail-Closed",
        },
        "actuator_thrust_n": 3450.0,
        "actuator_selection": {"model": "DA-200 (+%35 marj)"},
        "velocity": {"pipe_out_m_s": 4.8},
        "extra": {
            "flow": 50.0,
            "p1": 8.0,
            "p2": 5.0,
            "temperature_c": 25.0,
            "density": 998.0,
            "viscosity_cp": 1.0,
        },
    }

    sheet = build_isa20_datasheet(
        tag_number="FV-204",
        service_description="Kazan Besleme Suyu Kontrolu",
        line_number='3"-BFW-102-CS',
        pid_number="PID-402",
        service_type="liquid",
        fluid_name="Su (Water)",
        sizing_result=sizing_mock,
    )

    assert sheet.tag_number == "FV-204"
    assert sheet.valve_dn_mm == 65
    assert sheet.rated_cv == 75.0

    md = generate_isa20_markdown(sheet)
    assert "# ISA-20 KONTROL VANASI VER\u0130 SAYFASI" in md
    assert "FV-204" in md
    assert "DN65" in md
    assert "CL300" in md

    html = generate_isa20_html(sheet)
    assert "<html>" in html
    assert "FV-204" in html
    assert "Kazan Besleme Suyu" in html
    assert "DN65" in html


def test_reporting_isa20():
    from reporting import build_isa20_html_report, build_isa20_report

    mock_res = {
        "service": "liquid",
        "required_cv": 30.0,
        "rated_cv": 50.0,
        "valve_dn_mm": 50,
        "valve_inch": '2"',
        "delta_p_bar": 2.0,
        "opening_percent": 60.0,
        "noise_db": 75.0,
        "valve_spec": {
            "pressure_class_recommended": "CL150",
            "derated_mawp_bar": 19.6,
            "leakage_class_recommended": "IV",
            "fail_safe_recommended": "Fail-Closed",
        },
        "actuator_thrust_n": 2200.0,
        "actuator_selection": {"model": "DA-100"},
        "velocity": {"pipe_out_m_s": 3.2},
        "extra": {
            "flow": 40.0,
            "p1": 6.0,
            "p2": 4.0,
            "temperature_c": 20.0,
            "density": 1000.0,
            "viscosity_cp": 1.0,
        },
    }
    md = build_isa20_report(mock_res, tag="TCV-301", service_desc="Cooling Water")
    assert "TCV-301" in md
    assert "Cooling Water" in md
    assert "DN50" in md

    html = build_isa20_html_report(mock_res, tag="TCV-301", service_desc="Cooling Water")
    assert "TCV-301" in html
    assert "<table" in html


def test_reporting_safety_piping():
    from reporting import build_safety_piping_report

    rep = build_safety_piping_report(
        service="gas",
        velocity_m_s=35.0,
        density_kg_m3=18.0,
        rated_cv=65.0,
        p1_bar_a=15.0,
        p_relief_bar_a=6.0,
        fluid_data={"molecular_weight": 28.0, "temperature_c": 30.0, "xt": 0.70},
    )
    assert "# BORU GUVENLIGI VE TAHLIYE KAPASITESI" in rep
    assert "API RP 14E" in rep
    assert "API RP 520" in rep
