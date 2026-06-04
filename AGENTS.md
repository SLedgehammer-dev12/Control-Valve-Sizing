# Control Valve Sizing — Agent Context

IEC 60534 / ISA-based control valve sizing application with dual UI (desktop Tkinter + web Streamlit).

## Project Layout

```
valve_sizing.py       — Core sizing engine (710 lines)
fluid_properties.py   — CoolProp HEOS integration (190 lines)
vendor_catalog.py     — Fisher valve catalog (131 lines)
config.py             — Gas presets, default rows (44 lines)
project_io.py         — JSON save/load (45 lines)
reporting.py          — Markdown report generation (66 lines)
app_desktop.py        — Tkinter desktop UI (740 lines)
app_web.py            — Streamlit web UI (530 lines)
test_valve_sizing.py  — Core engine tests (30 tests)
test_vendor_catalog.py— Catalog validation (9 tests)
test_integration.py   — Streamlit + I/O tests (8 tests)
test_desktop_integration.py — Desktop import tests (7 tests)
```

## Dependency Chain

```
valve_sizing  ←  fluids (pip)
fluid_properties ← CoolProp (pip)
vendor_catalog ← valve_sizing (ValveSize)
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

## Test Status

- **54 tests, 100% passing**
- **Coverage**: 86% (excluding `app_desktop.py` Tkinter GUI)
- **CI**: GitHub Actions (Ubuntu, Python 3.11/3.12, ruff + pytest)
