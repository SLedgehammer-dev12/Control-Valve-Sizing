---
name: cv-sizing
description: "Control valve sizing engine — IEC 60534 / ISA-based liquid/gas/steam Cv/Kv calculations. Covers dataclass input types (LiquidSizingInput, GasSizingInput, SteamSizingInput), sizing functions (size_liquid_valve, size_gas_valve, size_steam_valve), SizingResult output, candidate-valve iteration helper (_size_iteration), unit conversions (cv_to_kv, kv_to_cv), and valve selection (select_valve_size). USE FOR: adding new service types, modifying sizing formulas, debugging Cv/Kv calculations, understanding sizing logic, adding new parameters to dataclasses."
license: MIT
metadata:
  project: control-valve-sizing
  module: valve_sizing.py
  version: "2.0"
---

# Control Valve Sizing Engine

Core module: `valve_sizing.py` (~710 lines). Implements IEC 60534-2-1 and ISA sizing equations for three service types.

## Input Dataclasses

All inputs are frozen dataclasses. Always use keyword arguments — positional order is not guaranteed.

### LiquidSizingInput
```python
LiquidSizingInput(
    flow_m3h, inlet_pressure_bar_a, outlet_pressure_bar_a,
    density_kg_m3, vapor_pressure_bar_a, critical_pressure_bar_a,
    viscosity_pa_s, fl, fd=1.0,
    pipe_inlet_diameter_mm=None, pipe_outlet_diameter_mm=None,
)
```

### GasSizingInput
```python
GasSizingInput(
    flow_nm3h, inlet_pressure_bar_a, outlet_pressure_bar_a,
    temperature_c, molecular_weight, specific_heat_ratio,
    viscosity_pa_s, z=1.0, fl=0.9, fd=1.0, xt=0.7,
    pipe_inlet_diameter_mm=None, pipe_outlet_diameter_mm=None,
)
```

### SteamSizingInput
```python
SteamSizingInput(
    flow_kg_h, inlet_pressure_bar_a, outlet_pressure_bar_a,
    temperature_c, specific_heat_ratio=1.30, z=1.0,
    xt=0.72, fp=1.0, fl=0.9, fd=1.0,
    pipe_inlet_diameter_mm=None, pipe_outlet_diameter_mm=None,
)
```

## Sizing Functions

All return `SizingResult` (frozen dataclass with `__getitem__` backward compat):

```python
result = size_liquid_valve(data, valve_series=list(vendor.sizes), valve_meta=meta)
result = size_gas_valve(data, valve_series=list(vendor.sizes), valve_meta=meta)
result = size_steam_valve(data, valve_series=list(vendor.sizes), valve_meta=meta)
```

### SizingResult core fields
- `required_cv`, `required_kv`, `rated_cv`, `rated_kv` (float)
- `valve_dn_mm` (int), `valve_inch` (str)
- `delta_p_bar` (float), `is_choked` (bool)
- `warning` (str), `valve_meta` (dict)
- `sources`, `equations`, `method_panel` (list)
- `intermediate_values` (dict), `extra` (dict — service-specific)

Access via attribute (`result.required_cv`) or subscript (`result["required_cv"]`).

## Candidate-Valve Iteration

All three sizing functions use `_size_iteration()` — a shared helper that:
1. Iterates through valve sizes
2. Calls a service-specific `compute(d1, d2, d)` closure for each valve
3. Returns `(valve, details, overflow)`

This ensures reducer effects (FP, xTP), piping geometry (D1, D2, d), and overflow handling are consistent across liquid/gas/steam.

## Validation Helpers
- `_require_positive(name, value)` — raises ValueError if ≤ 0
- `_validate_pressure_drop(p1, p2)` — raises if p1 ≤ p2, returns ΔP

## Unit Constants
- `BAR_TO_PSI = 14.5037738`
- `CV_TO_KV = 0.865`
- `AIR_K = 1.4`, `AIR_MW = 28.97`
- `FF_A = 0.96`, `FF_B = 0.28` (liquid critical pressure factor)
- `EXPANSION_Y_MIN = 2/3`, `Y_DENOM = 3.0`

## When adding a new parameter
1. Add field to the appropriate dataclass (with default if optional)
2. Validate with `_require_positive` in the sizing function
3. Pass to `size_control_valve_l` or `size_control_valve_g` as needed
4. Include in `intermediate_values` for traceability
5. Update caller in `app_desktop.py` and `app_web.py`
6. Add test case in `test_valve_sizing.py`
