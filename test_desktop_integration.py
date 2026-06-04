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
    data = dump_project_json("Liquid", {"test": 1})
    loaded = load_project_json(data)
    assert loaded["service"] == "Liquid"


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
