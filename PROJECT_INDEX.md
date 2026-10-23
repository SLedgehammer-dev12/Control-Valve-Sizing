# Project Index: Control Valve Sizing (v3.3.4)

> Generated: 2026-10-21 | Staleness Threshold: 7 days | Tests: 666/666 PASS (95.32% cov) | Scenarios: 52/52 PASS

## 1. Architectural Overview

Dual-interface engineering application implementing IEC 60534, ISA, API, and ISO standards for industrial control valve sizing, severe service analysis, acoustic prediction, and procurement datasheet generation.

```
                    ┌────────────────────────────────────────────────────────┐
                    │                      User Interfaces                   │
                    │   Desktop (Tkinter): app_desktop.py (2,595 lines)      │
                    │   Web (Streamlit)  : app_web.py     (2,115 lines)      │
                    └───────────────┬────────────────────────┬───────────────┘
                                    │                        │
         ┌──────────────────────────┴────────────────────────┴──────────────────────────┐
         │                                Orchestration Layer                           │
         │  multi_case.py (Min/Norm/Max)          reporting.py (Markdown/HTML)         │
         │  project_io.py (JSON save/load)        datasheet_isa20.py (ISA Form 20)      │
         └───────────────┬───────────────────────────────────────────┬──────────────────┘
                         │                                           │
         ┌───────────────┴────────────────────────┐ ┌────────────────┴──────────────────┐
         │       Core Sizing & Physics Engine     │ │          Engineering & Safety     │
         │  valve_sizing.py (IEC 60534-2-1)       │ │  valve_noise.py (IEC 60534-8)     │
         │  fluid_properties.py (CoolProp HEOS)   │ │  safety_piping.py (API 14E / 520) │
         │  two_phase.py (HEM flashing model)     │ │  trim_guidance.py (ISA RP75.23)   │
         │  joule_thomson.py (JT drop & hydrate)  │ │  packing_emissions.py (ISO 15848) │
         └───────────────┬────────────────────────┘ │  valve_selection.py (ASME B16.34) │
                         │                          │  actuator_sizing.py (Piston/Diaph)│
                         │                          │  thermal_expansion.py (Piping)    │
                         │                          └───────────────────────────────────┘
         ┌───────────────┴──────────────────────────────────────────────────────────────┐
         │                               Foundational Layer                             │
         │  vendor_catalog.py (Fisher/Valmet/Samson/Arca)   units.py (Pint unit system) │
         │  config.py (Gas & fluid presets)                                             │
         └──────────────────────────────────────────────────────────────────────────────┘
```

## 2. Module Directory & Responsibility Matrix

| Module | Role / Domain | Core Public APIs & Dataclasses |
|---|---|---|
| `valve_sizing.py` | Core IEC 60534 sizing engine | `LiquidSizingInput`, `GasSizingInput`, `SteamSizingInput`, `SizingResult`, `size_liquid_valve()`, `size_gas_valve()`, `size_steam_valve()` |
| `fluid_properties.py` | CoolProp HEOS & thermodynamics | `evaluate_gas_mixture()`, `get_pure_fluid_state()`, `evaluate_steam_state()`, `normalize_composition()` |
| `vendor_catalog.py` | Vendor valve sizing coefficients | `VendorValveDefinition`, `ValveSize`, `get_vendor_definition()`, `get_vendor_options()` |
| `units.py` | Pint-based engineering units | `liquid_flow_to_m3h()`, `gas_flow_to_nm3h()`, `steam_flow_to_kgh()`, `pressure_to_bar_a()`, `temperature_to_c()` |
| `config.py` | Sector gas & liquid presets | `GAS_PRESETS`, `GAS_PRESET_NAMES`, `DEFAULT_GAS_ROWS` |
| `two_phase.py` | Flashing & two-phase flow | `calc_two_phase_cv()`, `evaluate_flashing_risk()`, `flashing_check()` |
| `valve_selection.py` | Pressure class & metallurgy | `recommend_pressure_class()`, `derated_mawp_bar()`, `recommend_alloy_material()`, `recommend_bonnet_type()` |
| `trim_guidance.py` | Cavitation & trim selection | `evaluate_cavitation_severity()`, `recommend_trim()` |
| `valve_noise.py` | IEC 60534-8 acoustic analysis | `calculate_aerodynamic_noise()`, `evaluate_noise_attenuation()`, `evaluate_aiv_risk()` |
| `actuator_sizing.py` | Spring-diaphragm & piston sizing | `size_spring_diaphragm_actuator()`, `size_piston_actuator()` |
| `thermal_expansion.py` | Piping expansion & loop sizing | `calc_pipe_expansion()`, `calc_expansion_loop_length()` |
| `multi_case.py` | Min/Norm/Max envelope sizing | `OperatingCase`, `MultiCaseAnalysis`, `size_multicase()` |
| `joule_thomson.py` | Isenthalpic JT expansion & hydrates | `calc_joule_thomson_drop()`, `evaluate_hydrate_formation_risk()` |
| `packing_emissions.py` | ISO 15848-1 stem packing | `recommend_packing_system()` |
| `safety_piping.py` | API 14E erosion & API 520 relief | `check_erosional_velocity()`, `calc_wide_open_relief_capacity()` |
| `datasheet_isa20.py` | ISA Form 20 specification sheet | `ISA20DataSheet`, `build_isa20_datasheet()` |
| `reporting.py` | Markdown & HTML generation | `build_report()`, `build_isa20_report()`, `build_isa20_html_report()` |
| `project_io.py` | Project JSON serialization | `dump_project_json()`, `load_project_json()` |
| `valve_curve.py` | Flow characteristic curves & controllability | `CharacteristicPoint`, `OperatingPointAnalysis`, `CharacteristicCurve`, `generate_characteristic_curve()`, `evaluate_operating_point()` |
| `valve_3d.py` | Parametric globe valve Mesh3d geometry | `build_valve_figure()` |
| `api.py` | FastAPI browser backend | `/api/size/*`, `/api/convert`, `/api/valve-mesh`, `app` |
| `webapp/` | Browser UI (HTML/CSS/JS + Three.js) | `index.html`, `app.js`, `styles.css`, local `vendor/` |
| `app_desktop.py` | Tkinter desktop GUI | `ValveSizingApp`, `main()` |
| `app_web.py` | Streamlit web application | `main()` |

## 3. Entry Points & Invocation Commands

- **Desktop UI**: `python app_desktop.py` or entry point `valve-sizing-desktop`
- **Browser UI**: `uvicorn api:app --reload --port 8501` → http://127.0.0.1:8501
- **Streamlit UI**: `streamlit run app_web.py` or entry point `valve-sizing-web`
- **Industrial Benchmarks (52 Scenarios)**: `python verify_50_scenarios.py`
- **IEC Standard Benchmarks (12 Scenarios)**: `python verify_scenarios.py`
- **Automated Test Suite**: `python -m pytest -q` (666 tests)
- **Coverage Check**: `python -m pytest --cov=. --cov-report=term -q` (target $\ge 94\%$, actual 95.32%)
- **Code Linter**: `ruff check .` (target line length: 150)

## 4. Key Architectural Patterns

1. **Immutable Dataclasses**: All calculation inputs (`LiquidSizingInput`, `GasSizingInput`, `SteamSizingInput`, `OperatingCase`) and outputs (`SizingResult`, `MultiCaseAnalysis`) are `frozen=True` dataclasses with subscript backward compatibility.
2. **Unified Candidate Sizing Loop**: `_size_iteration()` in `valve_sizing.py` handles piping geometry factors ($F_p$, $x_{tp}$), reducer pressure losses, and candidate valve stepping identically across Liquid, Gas, and Steam services.
3. **Steam Gas-Path Equivalence**: High-pressure steam is evaluated by deriving density via CoolProp/IAPWS-97, converting to actual volumetric flow, and routing through the compressible gas sizing equation.
4. **Cached Thermodynamic Evaluation**: All pure fluid lookups and multi-component Helmholtz energy equations of state use `@lru_cache` to eliminate re-computation latency.
5. **Acyclic Domain Architecture**: Core domain calculation modules maintain zero inter-dependencies among themselves ($F_o = 0$), ensuring maximum testability and zero circular import risks.

## 5. Dual Agent Ecosystem & Orchestration

This project harmonizes two state-of-the-art agent engineering libraries:
- **`DietrichGebert/ponytail`** (`vendor/ponytail`): Minimalist senior developer mindset, YAGNI enforcement, smallest working diffs, zero dead code.
- **`addyosmani/agent-skills`** (`vendor/agent-skills`): Comprehensive lifecycle engineering skills (spec, plan, build, verify, review, ship) and specialized subagent personas (`code-reviewer`, `security-auditor`, `test-engineer`, `web-performance-auditor`).
- **OpenCode & Antigravity Parity**: Both tools share the full skill catalog (`.agents/skills/` and `.opencode/skills/`), agent definitions (`.agents/agents/` and `.opencode/agents/`), rules (`.agents/rules/`), and commands (`.opencode/command/`).

