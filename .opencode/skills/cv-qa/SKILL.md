---
name: cv-qa
description: "Testing and QA workflow for control valve sizing project — 666 pytest tests, 94% coverage floor, ruff/mypy, CI pipeline. Covers test_valve_sizing (core engine), test_api (FastAPI), test_integration (Streamlit AppTest), test_desktop_integration (desktop logic), test_units (conversions), and domain modules. USE FOR: adding tests, fixing test failures, increasing coverage, debugging CI failures, running lint checks."
license: MIT
metadata:
  project: control-valve-sizing
  test_count: "666"
  coverage_target: "94"
  version: "1.0"
---

# Testing & QA

## Test Files

| File | Tests | What it covers |
|---|---|---|
| `test_valve_sizing.py` | core | Liquid/gas/steam sizing, edge cases, choked detection, overflow |
| `test_units.py` | core | Unit maps, gauge/absolute pressure, gas/liquid/steam conversions |
| `test_api.py` | API | FastAPI validation, security headers/CSP, mesh contract, unit endpoints |
| `test_integration.py` | UI | Streamlit AppTest, project JSON round-trip, report generation |
| `test_desktop_integration.py` | UI | Desktop logic, unit conversion, project load/reset, packaging |
| Other `test_*.py` | domain | Multi-case, noise, safety, thermal, JT, packing, datasheet, scenarios |

## Running Tests

```powershell
# Full suite
python -m pytest --tb=short -q

# With coverage (target: 80% excluding app_desktop.py)
python -m pytest --cov=. --cov-report=term -q

# Single file
python -m pytest test_valve_sizing.py -v

# Smoke test (imports + sanity + pytest)
.\run_smoke_test.ps1
```

## Linting

```powershell
ruff check .          # should be clean
ruff check --fix .    # auto-fix import sorting, whitespace
```

Line length: 150 (configured in pyproject.toml).

## Coverage Thresholds

- **Fail under**: 94% overall (excluding `app_desktop.py` — Tkinter GUI not testable in CI)
- **Current**: ~95.32% (666 tests passing)
- **valve_sizing.py**: 100%
- **vendor_catalog.py**: 100%%
- **config.py**: 100%%

## CI Pipeline

`.github/workflows/ci.yml` — GitHub Actions:
- Ubuntu, Python 3.11 + 3.12
- ruff check → mypy → pytest

## When adding tests
1. Test file naming: `test_<module>.py`
2. Use `pytest.raises(ValueError, match="...")` for error paths
3. Use vendor catalog for realistic input values: `get_vendor_definition("fisher_globe_eqpct")`
4. Core sizing tests go in `test_valve_sizing.py`
5. Ensure all existing tests still pass: `pytest -q`
6. Check coverage improvement: `pytest --cov=. --cov-report=term -q`
