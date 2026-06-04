---
name: cv-fluid
description: "Fluid property calculations via CoolProp HEOS — liquid presets, gas mixture evaluation, pure fluid state lookup. Covers normalize_composition, evaluate_gas_mixture (with LRU cache via _evaluate_mixture_state), get_pure_fluid_state (cached), get_liquid_preset, list_coolprop_fluids, and CompositionSummary dataclass. USE FOR: adding gas presets, modifying liquid presets, debugging CoolProp errors, updating fluid property calculations, adding new fluid components."
license: MIT
metadata:
  project: control-valve-sizing
  module: fluid_properties.py
  version: "1.1"
---

# Fluid Properties via CoolProp

Module: `fluid_properties.py` (~190 lines). Wraps CoolProp HEOS for gas mixture and pure fluid state evaluation.

## Key Functions

### `normalize_composition(rows, basis) → CompositionSummary`
- Validates composition (sum = 100%, valid components)
- Converts mass ↔ mole fractions
- Returns `CompositionSummary` with `mole_fractions`, `mass_fractions`, `average_molecular_weight`
- **Fluid properties are None** — use `evaluate_gas_mixture` to fill them

### `evaluate_gas_mixture(rows, basis, pressure_bar_a, temperature_c) → CompositionSummary`
- Calls `normalize_composition` then `_evaluate_mixture_state`
- Fills all fluid properties: `z`, `density_kg_m3`, `viscosity_pa_s`, `cp_j_kgk`, `cv_j_kgk`, `specific_heat_ratio`
- **Cached**: `_evaluate_mixture_state` uses `@lru_cache(maxsize=256)` with hashable tuple keys

### `get_pure_fluid_state(fluid, pressure_bar_a, temperature_c) → dict`
- **Cached**: `@lru_cache(maxsize=256)`
- Returns: `density_kg_m3`, `z`, `molecular_weight`, `critical_pressure_bar_a`, `specific_heat_ratio`, `vapor_pressure_bar_a`, `viscosity_pa_s`, `cp_j_kgk`, `cv_j_kgk`

### `get_liquid_preset(name) → dict`
- Returns copy of `LIQUID_PRESETS[name]`: `density_kg_m3`, `vapor_pressure_bar_a`, `critical_pressure_bar_a`, `viscosity_pa_s`
- Raises `ValueError` for unknown preset

### `list_coolprop_fluids() → list[str]`
- Cached with `@lru_cache(maxsize=1)`

## CompositionSummary Fields

```python
CompositionSummary(
    basis: str,                    # "molar" or "mass"
    total_percent: float,
    mole_fractions: dict[str, float],
    mass_fractions: dict[str, float],
    average_molecular_weight: float,
    z: float | None,               # compressibility
    density_kg_m3: float | None,
    viscosity_pa_s: float | None,
    cp_j_kgk: float | None,
    cv_j_kgk: float | None,
    specific_heat_ratio: float | None,
    mixture_string: str,            # "Methane&Ethane" for CoolProp HEOS
)
```

## Liquid Presets

`LIQUID_PRESETS` dict keys: `Water`, `ThermalOil`, `LNG`, `Methanol`, `EthyleneGlycol`

Each preset has `label` (Turkish display name) + density, vapor pressure, critical pressure, viscosity.

## Caching Strategy

| Function | Cache | Key |
|---|---|---|
| `list_coolprop_fluids` | `@lru_cache(1)` | — |
| `get_molar_mass` | `@lru_cache(512)` | fluid name |
| `get_pure_fluid_state` | `@lru_cache(256)` | (fluid, P, T) |
| `_evaluate_mixture_state` | `@lru_cache(256)` | (mixture_string, tuple(mole_fractions), P, T) |

## When adding a fluid
1. For liquid presets: add to `LIQUID_PRESETS` dict with all 4 properties
2. For gas components: the component name must be a valid CoolProp fluid name (`list_coolprop_fluids()`)
3. Add test to `test_valve_sizing.py` or `test_fluid_properties.py`
