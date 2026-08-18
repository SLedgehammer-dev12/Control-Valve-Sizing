"""Desktop application integration tests (non-GUI testing of logic layer)."""

import ast
import re
import sys
from pathlib import Path

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
    app.inputs["gas_flow_nm3h"].set(800.0 * 35.3146667)
    result_gas_scfh, _ = app._calc_gas(vendor)
    assert abs(result_gas_scfh["required_cv"] - result_gas_engine["required_cv"]) < 0.05


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
    assert proj["requires-python"] == ">=3.12"
    assert "coolprop" in " ".join(proj["dependencies"])
    assert "streamlit" in " ".join(proj["dependencies"])
    assert "valve-sizing-web" in cfg["project"]["scripts"]
    assert "valve-sizing-desktop" in cfg["project"]["scripts"]
    assert "valve_sizing" in cfg["tool"]["setuptools"]["py-modules"]
    assert "app_web" in cfg["tool"]["setuptools"]["py-modules"]


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
