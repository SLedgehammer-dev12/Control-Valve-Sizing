---
name: cv-qa
description: "Testing and QA workflow for control valve sizing project — 54 pytest tests, 86%% coverage target, ruff linting, CI pipeline. Covers test_valve_sizing (core engine edge cases), test_vendor_catalog (vendor validation), test_integration (Streamlit AppTest), test_desktop_integration (import/syntax), test_app_integration (standalone validation). USE FOR: adding tests, fixing test failures, increasing coverage, debugging CI failures, running lint checks."
license: MIT
metadata:
  project: control-valve-sizing
  test_count: "54"
  coverage_target: "80"
  version: "1.0"
---

# Testing & QA

## Test Files

| File | Tests | What it covers |
|---|---|---|
| `test_valve_sizing.py` | ~30 | Liquid/gas/steam sizing, edge cases (zero flow, negative density, P2>P1), choked detection, overflow, regime classification, fluid composition errors |
| `test_vendor_catalog.py` | 9 | Vendor key availability, Fl/Xt/Fd validity, size monotonicity |
| `test_integration.py` | 8 | Streamlit AppTest (render, liquid calc, gas switch), project JSON round-trip, report generation |
| `test_desktop_integration.py` | 7 | Desktop app syntax check, import verification, preset validation, project_io, reporting |
| `test_app_integration.py` | 1 | Standalone import + GAS_PRESETS validation (non-pytest) |

## Running Tests

```powershell
# Full suite
python -m pytest --tb=short -q

# With coverage (target: 80%% excluding app_desktop.py)
python -m pytest --cov=. --cov-report=term -q

# Single file
python -m pytest test_valve_sizing.py -v

# Smoke test (imports + sanity + pytest)
.\run_smoke_test.ps1
```

## Linting

```powershell
ruff check .          # ~28 pre-existing warnings (E402, E501, ARG005, N806)
ruff check --fix .    # auto-fix import sorting, whitespace
```

Line length: 150 (configured in pyproject.toml).

## Coverage Thresholds

- **Fail under**: 80%% overall (excluding `app_desktop.py` — Tkinter GUI not testable in CI)
- **Current**: 86%% (54 tests passing)
- **valve_sizing.py**: 98%%
- **vendor_catalog.py**: 100%%
- **config.py**: 100%%

## CI Pipeline

`.github/workflows/ci.yml` — GitHub Actions:
- Ubuntu, Python 3.11 + 3.12
- ruff check → pytest

## When adding tests
1. Test file naming: `test_<module>.py`
2. Use `pytest.raises(ValueError, match="...")` for error paths
3. Use vendor catalog for realistic input values: `get_vendor_definition("fisher_globe_eqpct")`
4. Core sizing tests go in `test_valve_sizing.py`
5. Ensure all existing tests still pass: `pytest -q`
6. Check coverage improvement: `pytest --cov=. --cov-report=term -q`
