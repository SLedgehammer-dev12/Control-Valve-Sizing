"""Desktop application integration tests (non-GUI testing of logic layer)."""

import ast
import json
import re
import sys
import tomllib
from pathlib import Path

import pytest

APP_DIR = Path(__file__).parent
APP_FILE = APP_DIR / "app_desktop.py"


def test_desktop_syntax():
    code = APP_FILE.read_text(encoding="utf-8")
    ast.parse(code)


def test_desktop_imports():
    code = APP_FILE.read_text(encoding="utf-8")
    required_imports = [
        "valve_sizing",
        "fluid_properties",
        "vendor_catalog",
        "project_io",
        "reporting",
        "config",
    ]
    for mod in required_imports:
        assert f"import {mod}" in code or f"from {mod}" in code, f"Missing import: {mod}"


def test_desktop_service_key_normalizes_and_rejects():
    from app_desktop import _service_key

    assert _service_key("Liquid") == "liquid"
    assert _service_key("gas") == "gas"
    with pytest.raises(ValueError):
        _service_key("water")


def test_desktop_unit_labels_map_to_engine_keys():
    from app_desktop import _unit_key_for_label
    from units import PRESSURE_UNITS

    assert _unit_key_for_label(PRESSURE_UNITS, "bar(a)") == "bar_a"
    assert _unit_key_for_label(PRESSURE_UNITS, "bar_a") == "bar_a"


def test_desktop_has_gas_presets():
    sys.path.insert(0, str(APP_DIR))
    from config import GAS_PRESET_NAMES, GAS_PRESETS
    assert len(GAS_PRESETS) >= 3
    assert len(GAS_PRESET_NAMES) == len(GAS_PRESETS)


def test_desktop_has_vendor_integration():
    from vendor_catalog import get_vendor_options
    opts = get_vendor_options()
    assert len(opts) >= 3


def test_desktop_has_liquid_presets():
    from fluid_properties import LIQUID_PRESETS
    assert len(LIQUID_PRESETS) >= 3


def test_desktop_has_project_io():
    from project_io import dump_project_json, load_project_json
    data = dump_project_json("Liquid", {"liquid_flow_m3h": 25.0, "liquid_p1": 8.0, "liquid_p2": 5.0, "test": 1})
    loaded = load_project_json(data)
    assert loaded["service"] == "liquid"


def test_desktop_has_reporting():
    from reporting import build_report
    from valve_sizing import LiquidSizingInput, size_liquid_valve
    li = LiquidSizingInput(25.0, 8.0, 5.0, 998.0, 0.023, 220.64, 0.00089, fl=0.9, fd=1.0)
    result = size_liquid_valve(li)
    report = build_report("Liquid", None, result)
    assert "Control Valve Sizing Report" in report


def test_desktop_composition_parsing_regex():
    text = "Methane 90\nEthane 6\nNitrogen 4"
    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'[:\s]+', line)
        if len(parts) >= 2:
            result.append((parts[0], float(parts[1])))
    assert len(result) == 3
    assert result[0] == ("Methane", 90.0)
    assert result[1] == ("Ethane", 6.0)
    assert result[2] == ("Nitrogen", 4.0)
    total = sum(v for _, v in result)
    assert abs(total - 100.0) < 1e-6


def test_desktop_composition_parsing_with_colon():
    text = "Methane: 90\nEthane: 6\nNitrogen: 4"
    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'[:\s]+', line)
        if len(parts) >= 2:
            result.append((parts[0], float(parts[1])))
    assert len(result) == 3
    assert abs(sum(v for _, v in result) - 100.0) < 1e-6


def test_desktop_composition_parsing_empty_lines_skipped():
    text = "Methane 100\n\n  \n"
    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'[:\s]+', line)
        if len(parts) >= 2:
            result.append((parts[0], float(parts[1])))
    assert len(result) == 1
    assert result[0][0] == "Methane"


def test_desktop_vendor_meta_for_service():
    from vendor_catalog import get_vendor_definition
    vendor = get_vendor_definition("fisher_globe_eqpct")
    base = {"vendor": vendor.vendor, "family": vendor.family, "style": vendor.style}
    meta_gas = dict(base, FL=vendor.fl, Fd=vendor.fd, xT=vendor.xt)
    assert meta_gas["FL"] == 0.85
    assert meta_gas["xT"] == 0.69
    assert meta_gas["Fd"] == 0.31


def _desktop_gas_fake(inputs, parse_rows, raise_on_error):
    import sys

    sys.path.insert(0, str(APP_DIR))
    import app_desktop

    del raise_on_error

    class Var:
        def __init__(self, value):
            self._value = value

        def get(self):
            return self._value

        def set(self, value):
            self._value = value

    class Display:
        def __init__(self):
            self._value = ""

        def set(self, value):
            self._value = value

    app = object.__new__(app_desktop.ValveSizingApp)
    app.inputs = {k: Var(v) for k, v in inputs.items()}
    app.z_calculated_display = Display()
    app.k_calculated_display = Display()
    app.viscosity_calculated_display = Display()
    app.gas_status_text = Display()
    for prefix in ("liquid", "gas", "steam"):
        setattr(app, f"{prefix}_temp_unit", Var("C"))
        setattr(app, f"{prefix}_pres_unit", Var("bar_a"))
        setattr(app, f"{prefix}_flow_unit", Var("m3h" if prefix == "liquid" else "nm3h" if prefix == "gas" else "kgh"))
    app._parse_custom_composition = lambda: parse_rows
    return app


class _Var:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class _Display:
    def __init__(self, value=""):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


def _desktop_calc_fake():
    """Build a logic-only ValveSizingApp with default inputs and unit vars."""
    import sys

    sys.path.insert(0, str(APP_DIR))
    import app_desktop

    app = object.__new__(app_desktop.ValveSizingApp)
    base_inputs = {
        "liquid_flow_m3h": 25.0, "liquid_p1": 8.0, "liquid_p2": 5.0,
        "liquid_temp_c": 25.0, "liquid_density": 998.0, "liquid_pv": 0.023,
        "liquid_pc": 220.64, "liquid_mu": 0.00089, "liquid_fl": 0.85,
        "liquid_fd": 0.31, "liquid_pipe_in_mm": 50.0, "liquid_pipe_out_mm": 50.0,
        "gas_flow_nm3h": 800.0, "gas_p1": 8.0, "gas_p2": 6.0, "gas_temp_c": 20.0,
        "gas_mw": 18.0, "gas_xt": 0.69, "gas_composition": "Doğal Gaz",
        "gas_pipe_in_mm": 80.0, "gas_pipe_out_mm": 80.0,
        "steam_flow_kgh": 2500.0, "steam_p1": 12.0, "steam_p2": 8.0, "steam_temp_c": 220.0,
    }
    app.inputs = {k: _Var(v) for k, v in base_inputs.items()}
    app.liquid_preset_label = _Var("Su")
    for prefix in ("liquid", "gas", "steam"):
        setattr(app, f"{prefix}_temp_unit", _Var("C"))
        setattr(app, f"{prefix}_pres_unit", _Var("bar_a"))
        setattr(app, f"{prefix}_flow_unit", _Var("m3h" if prefix == "liquid" else "nm3h" if prefix == "gas" else "kgh"))
    app.design_margin = _Var(15.0)
    app.flow_characteristic = _Var("equal_percentage")
    app.z_calculated_display = _Display()
    app.k_calculated_display = _Display()
    app.viscosity_calculated_display = _Display()
    app.gas_status_text = _Display()
    app.steam_k_display = _Display("1.30")
    app.steam_z_display = _Display("1.00")
    app.steam_status_text = _Display()
    app._vendor_meta_for_service = lambda *_args: {}
    return app


def test_desktop_liquid_us_units_match_engine_units():
    from config import GAS_PRESETS
    from units import NM3H_TO_SCFH
    from vendor_catalog import get_vendor_definition

    app = _desktop_calc_fake()
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result_engine, _ = app._calc_liquid(vendor)

    app.liquid_flow_unit.set("gpm")
    app.liquid_pres_unit.set("psi_a")
    app.liquid_temp_unit.set("F")
    app.inputs["liquid_flow_m3h"].set(25.0 * 4.4028675)
    app.inputs["liquid_p1"].set(8.0 * 14.5037738)
    app.inputs["liquid_p2"].set(5.0 * 14.5037738)
    app.inputs["liquid_temp_c"].set(77.0)
    app.inputs["liquid_pv"].set(0.023 * 14.5037738)
    app.inputs["liquid_pc"].set(220.64 * 14.5037738)
    result_us, _ = app._calc_liquid(vendor)
    assert abs(result_us["required_cv"] - result_engine["required_cv"]) < 0.01

    app = _desktop_calc_fake()
    app._gas_composition_rows = lambda: GAS_PRESETS["Doğal Gaz"]["components"]
    result_gas_engine, _ = app._calc_gas(vendor)
    app.gas_flow_unit.set("scfh")
    app.inputs["gas_flow_nm3h"].set(800.0 * NM3H_TO_SCFH)
    result_gas_scfh, _ = app._calc_gas(vendor)
    assert abs(result_gas_scfh["required_cv"] - result_gas_engine["required_cv"]) < 0.05


def test_desktop_unit_change_converts_existing_values():
    from units import BAR_TO_PSI, NM3H_TO_SCFH

    app = _desktop_calc_fake()
    app._unit_previous = {"liquid_flow_unit": "m3h", "liquid_pres_unit": "bar_a", "gas_flow_unit": "nm3h"}
    app._live_enabled = True
    app._refresh_unit_labels = lambda: None
    calls = []
    app._calculate = lambda **kwargs: calls.append(kwargs)

    app.liquid_flow_unit.set("gpm")
    app._on_unit_change("liquid", "flow", "liquid_flow_unit")
    assert abs(app.inputs["liquid_flow_m3h"].get() - 110.0717) < 1e-3

    app.liquid_pres_unit.set("psi_a")
    app._on_unit_change("liquid", "pres", "liquid_pres_unit")
    assert abs(app.inputs["liquid_p1"].get() - 8.0 * BAR_TO_PSI) < 0.01
    assert abs(app.inputs["liquid_p2"].get() - 5.0 * BAR_TO_PSI) < 0.01
    assert abs(app.inputs["liquid_pv"].get() - 0.023 * BAR_TO_PSI) < 1e-3
    assert abs(app.inputs["liquid_pc"].get() - 220.64 * BAR_TO_PSI) < 0.1

    app.gas_flow_unit.set("scfh")
    app._on_unit_change("gas", "flow", "gas_flow_unit")
    assert abs(app.inputs["gas_flow_nm3h"].get() - 800.0 * NM3H_TO_SCFH) < 0.1
    assert len(calls) == 3


def test_desktop_pv_pc_use_absolute_pressure_under_gauge_selection():
    from units import pressure_to_bar_a

    app = _desktop_calc_fake()
    app.liquid_pres_unit = _Var("bar_g")
    app.inputs["liquid_pv"].set(0.0317)
    app.inputs["liquid_pc"].set(220.64)

    pressures = app._liquid_pressures_bar_a()
    assert pressures["liquid_p1"] == pytest.approx(pressure_to_bar_a(8.0, "bar_g"))
    assert pressures["liquid_pv"] == pytest.approx(0.0317)
    assert pressures["liquid_pc"] == pytest.approx(220.64)
    assert app._field_label_text("Buhar basinci", "pres_abs", "liquid") == "Buhar basinci [bar(a)]"


def test_desktop_gas_properties_use_absolute_pressure_when_gauge_selected():
    from config import GAS_PRESETS
    from fluid_properties import evaluate_gas_mixture
    from units import pressure_from_bar_a

    app = _desktop_gas_fake(
        {
            "gas_composition": "Doğal Gaz",
            "gas_p1": pressure_from_bar_a(8.0, "bar_g"),
            "gas_temp_c": 20.0,
            "gas_mw": 18.0,
        },
        [],
        False,
    )
    app.gas_pres_unit = _Var("bar_g")
    z_value, k_value, mu_value = app._calculate_gas_properties(raise_on_error=True)
    expected = evaluate_gas_mixture(GAS_PRESETS["Doğal Gaz"]["components"], "molar", 8.0, 20.0)
    assert z_value == pytest.approx(expected.z, rel=1e-6)
    assert k_value == pytest.approx(expected.specific_heat_ratio, rel=1e-6)
    assert mu_value == pytest.approx(expected.viscosity_pa_s, rel=1e-6)
    assert app.inputs["gas_mw"].get() == pytest.approx(expected.average_molecular_weight, rel=1e-6)


def test_desktop_gas_actual_mass_unit_round_trip():
    from units import gas_flow_from_nm3h

    app = _desktop_calc_fake()
    app._live_enabled = True
    app._refresh_unit_labels = lambda: None
    app._calculate = lambda **_kwargs: None
    app._gas_z_value = 0.92
    app._unit_previous = {"gas_flow_unit": "nm3h"}

    app.gas_flow_unit.set("m3h")
    app._on_unit_change("gas", "flow", "gas_flow_unit")
    actual = gas_flow_from_nm3h(800.0, "m3h", pressure_bar_a=8.0, temperature_c=20.0, z=0.92)
    assert app.inputs["gas_flow_nm3h"].get() == pytest.approx(actual, rel=1e-4)

    app.gas_flow_unit.set("kgh")
    app._on_unit_change("gas", "flow", "gas_flow_unit")
    app.gas_flow_unit.set("nm3h")
    app._on_unit_change("gas", "flow", "gas_flow_unit")
    assert app.inputs["gas_flow_nm3h"].get() == pytest.approx(800.0, rel=1e-3)


def test_desktop_multicase_gas_case_includes_case_properties():
    app = _desktop_calc_fake()
    case = app._multicase_operating_case("gas", "Normal", 800.0, 8.0, 6.0, "nm3h", "bar_a", 20.0)
    assert case.extra_props["z"] > 0.0
    assert case.extra_props["molecular_weight"] > 0.0
    assert case.extra_props["specific_heat_ratio"] > 0.0
    assert case.extra_props["viscosity_pa_s"] > 0.0


def test_desktop_gas_model_defaults_to_auto_for_legacy_fakes():
    app = _desktop_calc_fake()
    assert app._gas_model_key() == "auto"
    app.gas_model = _Var("real")
    assert app._gas_model_key() == "real"


def test_desktop_gas_conversion_uses_cached_numeric_z():
    app = _desktop_calc_fake()
    app.z_calculated_display = _Display("--")
    app._gas_z_value = 0.92
    assert app._gas_z_for_conversion() == 0.92


def test_desktop_preset_properties_refresh_on_temperature():
    app = _desktop_calc_fake()
    app._live_enabled = True
    app.liquid_source = _Var("Preset")
    app.liquid_preset_label = _Var("Su")
    app._on_live_change = lambda: ""
    app._on_liquid_conditions_change()
    pv_25 = app.inputs["liquid_pv"].get()

    app.inputs["liquid_temp_c"].set(150.0)
    app._on_liquid_conditions_change()

    assert app.inputs["liquid_pv"].get() > pv_25 * 10
    assert app.inputs["liquid_density"].get() < 950.0


def test_desktop_reset_resyncs_unit_history():
    app = _desktop_calc_fake()
    app.liquid_flow_unit.set("gpm")
    app.inputs["liquid_flow_m3h"].set(110.0)
    app._unit_previous = {
        f"{prefix}_{kind}_unit": getattr(app, f"{prefix}_{kind}_unit").get()
        for prefix in ("liquid", "gas", "steam")
        for kind in ("temp", "pres", "flow")
    }
    app._unit_previous["liquid_flow_unit"] = "m3h"
    app._var_defaults = {"liquid_flow_unit": "m3h", "input:liquid_flow_m3h": 25.0}
    app._toggle_service = lambda: None
    app._on_live_change = lambda: ""

    app._reset_to_defaults()

    assert app.liquid_flow_unit.get() == "m3h"
    assert app.inputs["liquid_flow_m3h"].get() == 25.0
    assert app._unit_previous["liquid_flow_unit"] == "m3h"


def test_desktop_project_load_applies_units_and_resyncs(tmp_path, monkeypatch):
    import app_desktop
    from project_io import dump_project_json

    app = _desktop_calc_fake()
    app.service_type = _Var("liquid")
    app.vendor_key = _Var("fisher_globe_eqpct")
    app.liquid_source = _Var("Preset")
    app._unit_previous = {
        f"{prefix}_{kind}_unit": getattr(app, f"{prefix}_{kind}_unit").get()
        for prefix in ("liquid", "gas", "steam")
        for kind in ("temp", "pres", "flow")
    }
    app._refresh_unit_labels = lambda: None
    app._toggle_service = lambda: None
    calls = []
    app._calculate = lambda **kwargs: calls.append(kwargs)
    path = tmp_path / "project.json"
    path.write_text(
        dump_project_json(
            "Gas",
            {
                "gas_flow_nm3h": 800.0,
                "gas_p1": 8.0,
                "gas_p2": 6.0,
                "gas_temp_unit": "F",
                "gas_pres_unit": "psi_a",
                "gas_flow_unit": "scfh",
                "vendor_key": "fisher_globe_eqpct",
                "liquid_source": "Preset",
                "liquid_preset_label": "Su",
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_desktop.filedialog, "askopenfilename", lambda **_kwargs: str(path))
    monkeypatch.setattr(app_desktop.messagebox, "showinfo", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_desktop.messagebox, "showerror", lambda *_args, **_kwargs: None)

    app._load_project()

    assert app.service_type.get() == "gas"
    assert app.vendor_key.get() == "fisher_globe_eqpct"
    assert app.gas_flow_unit.get() == "scfh"
    assert app.gas_pres_unit.get() == "psi_a"
    assert app.gas_temp_unit.get() == "F"
    assert app.inputs["gas_flow_nm3h"].get() == 800.0
    assert app._unit_previous["gas_flow_unit"] == "scfh"
    assert calls == [{"show_errors": False}]


def test_desktop_invalid_project_load_leaves_state_unchanged(tmp_path, monkeypatch):
    import app_desktop
    from project_io import dump_project_json

    app = _desktop_calc_fake()
    app.service_type = _Var("gas")
    app.vendor_key = _Var("fisher_globe_eqpct")
    app.liquid_source = _Var("Preset")
    app._unit_previous = {
        f"{prefix}_{kind}_unit": getattr(app, f"{prefix}_{kind}_unit").get()
        for prefix in ("liquid", "gas", "steam")
        for kind in ("temp", "pres", "flow")
    }
    values_before = {key: var.get() for key, var in app.inputs.items()}
    units_before = dict(app._unit_previous)
    errors = []
    calls = []
    app._calculate = lambda **kwargs: calls.append(kwargs)
    path = tmp_path / "bad.json"
    payload = json.loads(
        dump_project_json("Liquid", {"liquid_flow_m3h": 25.0, "liquid_p1": 8.0, "liquid_p2": 5.0})
    )
    payload["schema_version"] = 999
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(app_desktop.filedialog, "askopenfilename", lambda **_kwargs: str(path))
    monkeypatch.setattr(app_desktop.messagebox, "showerror", lambda *_args, **_kwargs: errors.append(_args))
    monkeypatch.setattr(app_desktop.messagebox, "showinfo", lambda *_args, **_kwargs: None)

    app._load_project()

    assert errors and "Proje yuklenemedi" in errors[0][1]
    assert {key: var.get() for key, var in app.inputs.items()} == values_before
    assert app.service_type.get() == "gas"
    assert app.vendor_key.get() == "fisher_globe_eqpct"
    assert app._unit_previous == units_before
    assert calls == []


def test_desktop_collect_payload_round_trips():
    from project_io import dump_project_json, load_project_json

    app = _desktop_calc_fake()
    app.service_type = _Var("Gas")
    app.vendor_key = _Var("fisher_globe_eqpct")
    app.liquid_source = _Var("Preset")
    app.liquid_preset_label = _Var("Su")

    loaded = load_project_json(dump_project_json("Gas", app._collect_payload()))

    assert loaded["service"] == "gas"
    assert loaded["data"]["gas_flow_nm3h"] == 800.0
    assert loaded["data"]["vendor_key"] == "fisher_globe_eqpct"
    for prefix in ("liquid", "gas", "steam"):
        for kind in ("temp", "pres", "flow"):
            assert f"{prefix}_{kind}_unit" in loaded["data"]


def test_desktop_steam_lbh_unit_matches_kgh():
    from vendor_catalog import get_vendor_definition

    app = _desktop_calc_fake()
    vendor = get_vendor_definition("fisher_globe_eqpct")
    result_engine, _ = app._calc_steam(vendor)
    app.steam_flow_unit.set("lbh")
    app.inputs["steam_flow_kgh"].set(2500.0 * 2.20462262)
    result_lbh, _ = app._calc_steam(vendor)
    assert abs(result_lbh["required_cv"] - result_engine["required_cv"]) < 0.05


def test_pyproject_packaging_metadata():
    import tomllib

    with (APP_DIR / "pyproject.toml").open("rb") as f:
        cfg = tomllib.load(f)
    proj = cfg["project"]
    assert proj["name"] == "control-valve-sizing"
    assert proj["requires-python"] == ">=3.11"
    assert "coolprop" in " ".join(proj["dependencies"])
    assert "streamlit" in " ".join(proj["dependencies"])
    assert cfg["build-system"]["build-backend"] == "setuptools.build_meta"
    assert "valve-sizing-web" in cfg["project"]["scripts"]
    assert "valve-sizing-desktop" in cfg["project"]["scripts"]
    assert "valve_sizing" in cfg["tool"]["setuptools"]["py-modules"]
    assert "app_web" in cfg["tool"]["setuptools"]["py-modules"]
    for m in ["api", "valve_3d", "datasheet_isa20", "joule_thomson", "multi_case", "packing_emissions", "safety_piping", "valve_curve"]:
        assert m in cfg["tool"]["setuptools"]["py-modules"]
    assert cfg["tool"]["setuptools"]["packages"] == ["webapp"]
    assert cfg["tool"]["setuptools"]["package-data"]["webapp"] == ["*.html", "*.css", "*.js", "vendor/*.js"]
    assert cfg["tool"]["coverage"]["report"]["fail_under"] == 94
    dockerfile = (APP_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "--limit-concurrency" in dockerfile
    assert "/api/health" in dockerfile
    assert "/_stcore/health" not in dockerfile
    dockerignore = (APP_DIR / ".dockerignore").read_text(encoding="utf-8")
    for entry in (".env", "ci_artifacts", "__pycache__", "test_*.py"):
        assert entry in dockerignore


def test_requirements_match_pyproject():
    import tomllib

    with (APP_DIR / "pyproject.toml").open("rb") as f:
        cfg = tomllib.load(f)
    def _requirements(name: str) -> set[str]:
        lines = (APP_DIR / name).read_text(encoding="utf-8").splitlines()
        return {line.strip() for line in lines if line.strip() and not line.startswith("#")}

    runtime = _requirements("requirements.txt")
    dev = _requirements("requirements-dev.txt")
    assert set(cfg["project"]["dependencies"]) == runtime
    assert set(cfg["project"]["optional-dependencies"]["dev"]) == dev


def test_desktop_gas_properties_raise_on_error():
    app = _desktop_gas_fake(
        {"gas_composition": "Özel (Custom)", "gas_p1": 8.0, "gas_temp_c": 20.0},
        [{"component": "Methane", "fraction_pct": 50.0}],
        raise_on_error=True,
    )
    import pytest

    with pytest.raises(ValueError, match="100% olmali"):
        app._calculate_gas_properties(raise_on_error=True)


def test_desktop_gas_properties_fallback_defaults():
    app = _desktop_gas_fake(
        {"gas_composition": "Özel (Custom)", "gas_p1": 8.0, "gas_temp_c": 20.0},
        [{"component": "Methane", "fraction_pct": 50.0}],
        raise_on_error=False,
    )
    z, k, mu = app._calculate_gas_properties(raise_on_error=False)
    assert z == 1.0
    assert k == 1.30
    assert mu == 1e-5


def test_desktop_has_new_dialog_methods():
    from app_desktop import ValveSizingApp

    assert hasattr(ValveSizingApp, "_open_joule_thomson_dialog")
    assert hasattr(ValveSizingApp, "_open_multicase_dialog")
    assert hasattr(ValveSizingApp, "_open_cavitation_dialog")
    assert hasattr(ValveSizingApp, "_open_packing_dialog")
    assert hasattr(ValveSizingApp, "_open_isa20_dialog")
    assert hasattr(ValveSizingApp, "_export_isa20")
    assert hasattr(ValveSizingApp, "_open_safety_piping_dialog")
    assert hasattr(ValveSizingApp, "_open_material_selection_dialog")
    assert hasattr(ValveSizingApp, "_open_characteristic_curve_dialog")
    assert hasattr(ValveSizingApp, "_open_actuator_dynamics_dialog")


def test_desktop_code_contains_new_tools():
    code = APP_FILE.read_text(encoding="utf-8")
    assert "Joule-Thomson ve Gaz Hidrat Analizi" in code
    assert "Coklu Calisma Durumu (Multi-Case Sizing)" in code
    assert "Kavitasyon Kademe Analizi (ISA-RP75.23)" in code
    assert "Salmastra ve Kacak Emisyon (ISO 15848-1)" in code
    assert "ISA-20 Sartname Veri Sayfasi (Datasheet)" in code
    assert "Boru Guvenligi ve PSV Tahliye Debisi (API 14E / API 520)" in code
    assert "Gelismis Malzeme ve Bonnet Secimi (NACE / API 941)" in code
    assert "Vana Karakteristik Eğrisi & Kontrol Analizi (IEC 60534-2-4)" in code
    assert "Aktorator Tepki Suresi ve Hava Tuketimi (ISA-75.25)" in code


def test_desktop_cavitation_dialog_multistage_trim():
    code = APP_FILE.read_text(encoding="utf-8")
    assert "design_multistage_cavitation_trim" in code
    assert "KADEME BASINC VE AKIS PROFILI TABLOSU" in code
    assert "Kademe Secimi" in code


def test_desktop_actuator_dynamics_dialog():
    code = APP_FILE.read_text(encoding="utf-8")
    assert "analyze_actuator_dynamics" in code
    assert "AKTUATOR TEPKI SURESI VE HAVA TUKETIMI ANALIZI" in code
    assert "Hacim Yukseltici (Booster)" in code


def test_desktop_liquid_pressures_convert_from_display_unit():
    sys.path.insert(0, str(APP_DIR))
    import app_desktop
    from units import pressure_from_bar_a

    expected = {"liquid_p1": 8.0, "liquid_p2": 5.0, "liquid_pv": 0.023, "liquid_pc": 220.64}
    app = object.__new__(app_desktop.ValveSizingApp)
    app.liquid_pres_unit = _Var("psi_a")
    app.inputs = {key: _Var(pressure_from_bar_a(value, "psi_a")) for key, value in expected.items()}
    actual = app._liquid_pressures_bar_a()
    for key, value in expected.items():
        assert abs(actual[key] - value) < 1e-9


def test_desktop_multicase_liquid_uses_selected_units():
    sys.path.insert(0, str(APP_DIR))
    import app_desktop

    app = object.__new__(app_desktop.ValveSizingApp)
    app.inputs = {"liquid_density": _Var(998.0)}
    case = app._multicase_operating_case("liquid", "Normal", 110.0, 116.0304, 72.5190, "gpm", "psi_a", 25.0)
    assert abs(case.flow - 24.98) < 0.01
    assert abs(case.p1_bar_a - 8.0) < 1e-3
    assert abs(case.p2_bar_a - 5.0) < 1e-3
    assert case.temperature_c == 25.0


def test_desktop_liquid_preset_properties_are_written_in_display_unit():
    sys.path.insert(0, str(APP_DIR))
    import app_desktop
    from fluid_properties import evaluate_liquid_preset
    from units import pressure_from_bar_a

    app = object.__new__(app_desktop.ValveSizingApp)
    app.inputs = {
        "liquid_p1": _Var(pressure_from_bar_a(8.0, "psi_a")),
        "liquid_p2": _Var(pressure_from_bar_a(5.0, "psi_a")),
        "liquid_pv": _Var(0.0),
        "liquid_pc": _Var(0.0),
        "liquid_temp_c": _Var(25.0),
        "liquid_density": _Var(0.0),
        "liquid_mu": _Var(0.0),
    }
    app.liquid_source = _Var("Preset")
    app.liquid_preset_label = _Var("Su")
    app.liquid_pres_unit = _Var("psi_a")
    app.liquid_temp_unit = _Var("C")
    app._update_liquid_properties()
    expected = evaluate_liquid_preset("Water", 8.0, 25.0)
    assert abs(app.inputs["liquid_pv"].get() - pressure_from_bar_a(expected["vapor_pressure_bar_a"], "psi_a")) < 1e-9
    assert abs(app.inputs["liquid_pc"].get() - pressure_from_bar_a(expected["critical_pressure_bar_a"], "psi_a")) < 1e-9


def test_version_is_consistent_across_metadata():
    from valve_sizing import __version__

    pyproject = tomllib.loads((APP_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__


def test_release_installers_include_version():
    iss = (APP_DIR / "installer.iss").read_text(encoding="utf-8")
    assert "OutputBaseFilename=ControlValveSizing_Setup_{#MyAppVersion}" in iss

    iss_web = (APP_DIR / "installer_web.iss").read_text(encoding="utf-8")
    assert "OutputBaseFilename=ControlValveSizing_Web_Setup_{#MyAppVersion}" in iss_web

    workflow = (APP_DIR / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "ControlValveSizing_macos_arm64_${VERSION}.dmg" in workflow
    assert "ControlValveSizing_Web_macos_arm64_${VERSION}.dmg" in workflow
    assert "installer.iss" in workflow
    assert "installer_web.iss" in workflow
    assert "build-web" in workflow
    assert "pattern: ControlValveSizing-*" in workflow

    dockerfile = (APP_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG APP_VERSION" in dockerfile
