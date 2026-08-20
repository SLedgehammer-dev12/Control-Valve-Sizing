# Control Valve Sizing — Agent Context

IEC 60534 / ISA-based control valve sizing application with dual UI (desktop Tkinter + web Streamlit).

## Project Layout

```
valve_sizing.py       — Core sizing engine (1100+ lines)
fluid_properties.py   — CoolProp HEOS integration (190 lines)
vendor_catalog.py     — Fisher catalog (131 lines)
config.py             — Gas presets (energy), default rows (44 lines)
project_io.py         — JSON save/load + schema versioning
reporting.py          — Markdown report generation
two_phase.py          — Flashing / two-phase Cv (HEM)
valve_selection.py    — ANSI class / leakage / fail-safe guidance
trim_guidance.py      — Rule-based trim recommendations
thermal_expansion.py  — Pipe thermal expansion / stress / loop length
valve_noise.py        — IEC 60534-8-4 aerodynamic noise
actuator_sizing.py    — Actuator sizing helpers
units.py              — Pint-based unit conversions + sector unit maps/converters
app_desktop.py        — Tkinter desktop UI
app_web.py            — Streamlit web UI
test_valve_sizing.py  — Core engine tests
test_vendor_catalog.py— Catalog validation
test_integration.py   — Streamlit + I/O tests
test_desktop_integration.py — Desktop import tests
test_fluid_advanced.py— Energy gas preset tests
test_benchmark_iec.py — IEC/ISA benchmark verification
```

## Dependency Chain

```
valve_sizing  ←  fluids (pip)
fluid_properties ← CoolProp (pip)
vendor_catalog ← valve_sizing (ValveSize)
two_phase ← valve_sizing (types, circular-import-free scalar API)
valve_selection / trim_guidance ← vendor_catalog, valve_sizing
app_desktop ← valve_sizing, fluid_properties, vendor_catalog, config, project_io, reporting
app_web ← valve_sizing, fluid_properties, vendor_catalog, config, project_io, reporting
```

## Code Conventions

- **Language**: Code in English, UI labels in Turkish, error messages in Turkish
- **Dataclasses**: All input/output types are `frozen=True` dataclasses
- **Private helpers**: Prefix with `_` (`_require_positive`, `_size_iteration`)
- **No inline comments**: No `#` comments in code
- **Docstrings**: `"""..."""` for modules and public functions only
- **Line length**: 150 characters (ruff configured)
- **Python version**: 3.12

## Commands

```powershell
# Run all tests
python -m pytest --tb=short -q

# With coverage
python -m pytest --cov=. --cov-report=term -q

# Lint
ruff check .

# Auto-fix lint
ruff check --fix .

# Web app
streamlit run app_web.py

# Desktop app
python app_desktop.py
```

## Key Architectural Decisions

1. **SizingResult dataclass** replaces raw dict returns — supports both `.attr` and `["key"]` access
2. **`_size_iteration()`** is the shared candidate-valve loop for all three services
3. **Steam uses gas path**: mass flow → density (CoolProp) → actual volume → `size_control_valve_g`
4. **CoolProp caching**: `get_pure_fluid_state` and `_evaluate_mixture_state` use `@lru_cache`
5. **Vendor catalog** is separate from sizing engine — `valve_series` passed as parameter
6. **`config.py`** centralizes `GAS_PRESETS` to avoid duplication across desktop/web/test files
7. **Sector units are centralized in `units.py`**: unit maps (`TEMPERATURE_UNITS`, `PRESSURE_UNITS`, `LIQUID_FLOW_UNITS`, `GAS_FLOW_UNITS`, `STEAM_FLOW_UNITS`) + converters; both UIs convert to engine units (bar(a), °C, m³/h, Nm³/h, kg/h) at calculation time
8. **Live calculation**: web recomputes on every rerun (no buttons); desktop traces flow/pressure/temperature vars and unit combos → silent `_calculate(show_errors=False)`

## Test Status

- **328 tests, 100% passing**
- **Coverage**: 91% (excluding `app_desktop.py` Tkinter GUI)
- **CI**: GitHub Actions (Ubuntu, Python 3.11/3.12, ruff + mypy + pytest)
- **Scenario verification**: `verify_scenarios.py` (12 independent cross-checks, 12/12 PASS) + `test_scenario_verification.py` wrappers
