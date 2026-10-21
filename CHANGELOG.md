# Changelog

Sürüm bazlı what's new ve release notları için `docs/releases/` dizinine bakın.

## [3.3.4]

### Added
- Windows installer (`installer.iss`, Inno Setup): per-user install, Start Menu/Desktop shortcuts, versioned `ControlValveSizing_Setup_<version>.exe`.
- macOS DMG now contains an `/Applications` shortcut; DMG/volume names and app `Info.plist` version come from the release tag.
- Web Docker image published to GHCR with version + `latest` tags, non-root runtime, and a `/_stcore/health` healthcheck.
- Release workflow validates `vX.Y.Z` against `valve_sizing.__version__` and builds Windows setup/zip, macOS DMG, and the Docker image in parallel.
- Service tabs (desktop `ttk.Notebook`, web segmented buttons) stay in sync with the opening slider; centralized unit converter in desktop dialog/web sidebar.
- Tests for version metadata consistency and versioned release artifact names.

### Changed
- All release artifact filenames include the version; `version_info.txt` is generated from `valve_sizing.__version__` instead of being hardcoded.
- Desktop PyInstaller spec reads `CVS_VERSION` (falling back to `valve_sizing.__version__`) for Windows/macOS metadata.
- README and release notes document the new installers, Docker image, and GHCR visibility step.

### Fixed
- Release job now declares the `prepare` dependency explicitly so the version output is available when composing the release body.

## [3.3.3]

### Fixed
- Windows desktop build: bundle CoolProp 8.x `coolprop.libs` MSVC runtime DLLs and add them to the DLL search path, fixing `ImportError: DLL load failed while importing CoolProp`; add the missing `fpdf2` build dependency so the PDF report module loads.
- Release CI: verify the bundled `CoolProp.pyd` + `coolprop.libs` DLLs and run a headless `--self-test` on the frozen Windows exe before publishing.
- macOS app version: `CFBundleShortVersionString`/`CFBundleVersion` were stale at 3.3.1 in the previously shipped `.dmg`; rebuilt `.app` and `.dmg` now report **3.3.3** (`Info.plist` verified).
- Desktop tooltips: `ToolTip` class bound to non-existent `self.on_enter`/`self.on_leave` methods, which would raise `AttributeError` on widget construction; renamed to `_on_enter`/`_on_leave` so tooltips work on every input field.
- `valve_sizing.__version__` and `PROJECT_INDEX.json` version synced to 3.3.3.

### Added
- Desktop tooltips: `ToolTip` class and `tooltip_label()` helper; every Liquid/Gas/Steam input and sidebar option now has an explanatory hover tooltip.
- PDF "Key Highlights" strip: color-coded boxes for predicted noise (green ≤85 dBA, red above), actuator thrust margin (green/red by stroke adequacy), opening % (green in 20–85%) and choked-flow status.
- PDF working-point table: inherent characteristic curve values at 25/50/75/100% openings (Cv and Kv), complementing the curve chart.
- PDF report export: `build_pdf_report()` in `reporting.py` (fpdf2, Turkish glyph sanitization for core fonts) exposed as a web download button and a desktop `Dosya → Hesaplama Raporu Kaydet (PDF)` menu item.
- PDF characteristic curve: inherent valve characteristic drawn with fpdf2 primitives (no extra dependency), with required-Cv reference line and operating-point marker; `flow_characteristic` is now stored in all sizing results.
- UI reset to defaults: web sidebar button and desktop action-bar button (`Esc` in desktop); clears inputs, results and history.
- Desktop keyboard shortcuts: `Enter` = Hesapla, `Esc` = Varsayılana Sıfırla.
- Web UI 3D visualization: interactive installed-characteristic surface (opening % vs valve authority PR vs installed flow Q/Qmax) rendered with plotly, including the current operating-point marker; illustrates characteristic distortion per IEC 60534-8-4.
- Web UI 3D operating envelope: Min/Normal/Max operating points plotted in 3D (flow vs ΔP vs opening %) for the recommended valve in the multi-case analysis, colored by opening.
- Project JSON validation: required numeric fields must be finite numbers and unit selector keys are validated against the supported unit maps, so corrupt or hand-edited project files cannot break widget state on load.

### Assets
- `ControlValveSizing_windows_x86_64.zip` (~73.6 MB)
- `ControlValveSizing_macos_arm64_3.3.3.dmg` (~143 MB)

## [Unreleased]

### Fixed

### Added
- 52 industrial benchmark verification scenarios (`verify_50_scenarios.py` + `test_50_scenarios.py`): 52 real-world scenarios across 5 key sectors (Power & Steam, Upstream/Midstream Oil & Gas, Petrochem & Refining, Clean Energy & Cryogenics, Chemical & Heavy Industry) with 100% pass rate
- Multi-case operating envelope sizing (`multi_case.py` + `test_multi_case.py`) per IEC 60534: Min / Normal / Max operational cases, rangeability check, travel % analysis, and operating envelope summary
- Joule-Thomson isenthalpic expansion and hydrate risk evaluation (`joule_thomson.py` + `test_joule_thomson.py`): downstream temperature T2, Towler-Mokhatab (2005) hydrate equilibrium curves, minimum preheater temperature
- Valve stem packing and fugitive emissions selection (`packing_emissions.py`): ISO 15848-1 Class AH/BH, API 641, TA-Luft (VDI 2440), Live-loaded PTFE chevron, die-formed graphite, and Bellows Seal for toxic/lethal media
- Piping safety and downstream PSV relief load sizing (`safety_piping.py` + `test_safety_piping.py`): API RP 14E erosional velocity limits and API 520 / ISA-75.01 control valve wide-open failure discharge capacity
- ISA Form 20 (ISA-S20.50) control valve specification datasheet generator (`datasheet_isa20.py`): procurement-ready technical datasheets in Markdown and HTML format
- Acoustic mitigation options (`valve_noise.py`): Whisper trim (-18 dBA), acoustic insulation jacket (-10 dBA), diffuser plate (-14 dBA), and Acoustic-Induced Vibration (AIV > 110 dBA) fatigue alerts
- Advanced bonnet and metallurgy selection (`valve_selection.py`): Cryogenic extended bonnet (-196 °C / -46 °C), radiation finned, high-temperature bonnets; NACE MR0175, API 941 Nelson curves (Cr-Mo WC6/WC9), Duplex 2205, Monel 400
- Dual UI integration (`app_desktop.py` & `app_web.py`): new panels and dialogs for acoustic mitigation, piping safety checks, multi-case expanders, and ISA-20 datasheet export

## [3.2.0] — 2026-08-20

### Added
- Calculation verification suite (`verify_scenarios.py` + `test_scenario_verification.py`): 12 independent scenarios cross-check the sizing engine against analytic IEC/ISA formulas, the `fluids` library and CoolProp densities
  - Liquid: subcritical, choked, flashing (HEM self-consistency), velocity/erosion
  - Gas: IEC published CO2 example, analytic choked air, H2-NG %20 CoolProp blend
  - Steam: superheated 12→8 bar(a), near-saturated 6→3 bar(a)
  - Cross-checks: SI↔US unit equivalence, 15% design margin, Fisher vendor catalog selection
  - `python verify_scenarios.py` prints a console report and exits non-zero on failure

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

## [1.1.0] — 2026-07-01

### Fixed
- Project save/load: service name made case-insensitive — desktop (`"liquid"`) and web (`"Liquid"`) projects now load interchangeably
- `get_pure_fluid_state` LRU cache added (256) — CoolProp calls no longer repeated
- Cavitation index aligned with IEC 60534-8-4 (`sigma = (P1-Pv)/(P1-P2)`, single formula)
- Steam warning: CoolProp fallback warning no longer suppressed on overflow, merged instead
- Gas mixture fallback: removed fake loop that always returned `k_avg = 1.4`
- Ideal gas viscosity: constant `1.5e-5` → temperature-corrected `mu_ref * sqrt(T/300)`
- Flash vapor fraction: crude `DeltaT_sat = DeltaP * 2.0` → Clausius-Clapeyron (`dT/dP = RT^2/Ph_fg`)
- Chemicals error logging: silent swallowing → `logger.debug()`
- Chemicals cache limit: unbounded growth → max 512 entries
- `get_vendor_definition`: bare `KeyError` → `ValueError("Bilinmeyen vendor...")`
- `cavitation_severity`: English → Turkish labels
- `select_valve_size`: `DeprecationWarning` added
- `.dockerignore` added
- `pyproject.toml`: removed invalid `test_app_integration.py` reference

### Added
- Valve noise (IEC 60534-8): `noise_db` field on Liquid/Gas/Steam results; `valve_noise.py` wired into engine
- Actuator sizing: automatic `actuator_thrust_n` after valve selection; `actuator_sizing.py` wired into engine
- Web UI: reference pressure removed, inlet pressure is single source; fluid properties computed at correct pressure

## [1.0.0] — 2026-06-05

- Initial release: liquid/gas sizing with Tkinter + Streamlit UI
- CoolProp HEOS integration for gas mixture properties
- Fisher vendor catalog (4 valve types)
- Project JSON save/load
- Markdown report generation
