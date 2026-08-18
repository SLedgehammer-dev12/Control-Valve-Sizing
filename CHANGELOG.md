# Changelog

## [3.1.0] — 2026-08-18

### Added
- Sector-standard unit selectors for temperature, pressure and flow in web (Streamlit) and desktop (Tkinter) UIs:
  - Temperature: °C, °F, K
  - Pressure: bar(a)/bar(g), psi(a)/psi(g), kPa(a), MPa(a), atm(a) — gauge values converted with 1.01325 bar atmosphere
  - Liquid flow: m³/h, US gpm, L/min, m³/d, US bbl/d, kg/h
  - Gas flow: Nm³/h, Sm³/h, scfh, MMSCFD, m³/h (actual), kg/h
  - Steam flow: kg/h, t/h, lb/h, kg/s
- Live calculation: web app recomputes on every input/unit change (buttons removed); desktop app recomputes on unit change, flow/pressure/temperature edits, and project load
- Unit conversion helpers in `units.py`: `temperature_to_c/from_c`, `pressure_to_bar_a/from_bar_a`, `liquid_flow_*`, `gas_flow_*`, `steam_flow_*` with unit maps (`TEMPERATURE_UNITS`, `PRESSURE_UNITS`, `LIQUID_FLOW_UNITS`, `GAS_FLOW_UNITS`, `STEAM_FLOW_UNITS`)
- Project save/load now persists selected units (web + desktop)
- 36 new tests (unit converters round-trips, US/imperial unit parity checks, AppTest live-recalc with gpm/scfh)

### Changed
- `render_liquid_section` / `render_gas_section` / `render_steam_section` now convert inputs to engine units and render results live
- `app_desktop._calculate` accepts `show_errors` (live recalcs are silent); `_calc_liquid/_calc_gas/_calc_steam` convert inputs from selected units

## [3.0.0] — 2026-08-18

### Added
- IEC/ISA benchmark test suite (`test_benchmark_iec.py`) with verified reference results
- Aerodynamic noise (IEC 60534-8-4) and actuator sizing outputs shown in UI + report
- Opening / design margin: `design_margin_pct`, `flow_characteristic` (linear/eq-pct), rangeability check, `opening_percent`, `cv_ratio`, `rangeability_min_cv`
- Flashing / two-phase Cv estimation (`two_phase.py`, HEM) — `flashing_cv_estimate`, `vapor_density_ideal_gas`
- `LiquidSizingInput` fields: `temperature_c`, `specific_heat_j_kgk`, `latent_heat_j_kg`, `molecular_weight`
- Valve specification guidance (`valve_selection.py`): ANSI pressure class, leakage class (I-VI), fail-safe direction, `valve_spec` in results
- Trim guidance (`trim_guidance.py`): rule-based `recommend_trim` for flashing/cavitation/noise/multi-stage/low-opening/high-temperature
- Velocity & erosion checks: pipe velocity, Mach number, API 14E erosion velocity for all three services
- Energy gas presets in `config.py`: H2-NG blends (%5/%10/%20/%50), Sentez Gazi (Syngas), Hidrojen zengin (H2-CO2)
- Thermal expansion web UI section (pipe material/length/ΔT → expansion, thermal stress, loop length)
- Streamlit gas preset selector that loads preset compositions into the data editor
- Project schema versioning + migration/validation in `project_io.py` (`schema_version`, required keys, newer-schema rejection)
- Packaging metadata in `pyproject.toml` (`[project]`, console scripts, py-modules)
- Desktop gas calculation now exception-based: sizing run raises a graceful dialog instead of silently using defaults

### Changed
- FLP/xTP consistency: `fl_effective`, `x_choked_effective` aligned with IEC
- Liquid warnings restructured to a list (regime no longer overwrites velocity/flashing warnings)
- `validate_project_payload` / `load_project_json` now enforce schema version and per-service required keys

### Fixed
- Streamlit preset bug: selecting a gas preset now loads its composition (editor key is preset-scoped)
- Desktop gas path silently using fallback defaults on CoolProp failure during sizing

### Removed
- `select_valve_size` (superseded by `_size_iteration`)

## [2.0.0] — 2026-05-18

### Added
- `SizingResult` frozen dataclass with `__getitem__` backward compatibility
- Steam sizing IEC alignment via CoolProp density + `size_control_valve_g` candidate loop
- `_size_iteration()` shared candidate-valve loop helper
- `get_pure_fluid_state` LRU cache (maxsize=256)
- `.opencode/` skills: `cv-sizing`, `cv-fluid`, `cv-vendor`, `cv-qa`
- `.opencode/` agents: `cv-reviewer`, `cv-engineer`, `cv-documenter`
- `AGENTS.md` project context file
- `Dockerfile` for Streamlit deployment
- `.pre-commit-config.yaml` with ruff + whitespace hooks
- Coverage threshold (80%) in `pyproject.toml`
- 11 new edge-case tests (steam choked/overflow, liquid regimes, gas overflow, fluid errors, CoolProp fallback)

### Changed
- `SteamSizingInput` now includes `fl`, `fd`, `pipe_inlet_diameter_mm`, `pipe_outlet_diameter_mm`
- `app_desktop._calculate` refactored to dispatch pattern (`_calc_liquid`, `_calc_gas`, `_calc_steam`)
- `pyproject.toml` line length: 120 → 150
- `reporting.py` `build_report` signature: `dict` → `SizingResult`
- `app_web.py` `render_result` signature: `dict` → `SizingResult`

### Fixed
- `valve_sizing.py` zero-diameter bug (`value if value else fallback` → `value if value is not None else fallback`)
- Gas sizing `NameError` for undefined variables (`mw`, `flow_nm3h`, etc.)
- Steam sizing `NameError` for undefined variables (`mw`, `y`, etc.)
- `app_desktop.py` missing `critical_pressure_bar_a` and `viscosity_pa_s` in `LiquidSizingInput`
- `app_desktop.py` missing `specific_heat_ratio` and `viscosity_pa_s` in `GasSizingInput`

### Removed
- Duplicate `GAS_PRESETS` from `app_desktop.py` and `app_web.py` (centralized in `config.py`)
- `test_z_implementation.py` standalone script (converted to pytest tests)

## [1.0.0] — 2026-05-14

- Initial release: liquid/gas sizing with Tkinter + Streamlit UI
- CoolProp HEOS integration for gas mixture properties
- Fisher vendor catalog (4 valve types)
- Project JSON save/load
- Markdown report generation
