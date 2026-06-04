---
name: cv-vendor
description: "Vendor valve catalog — Emerson Fisher representative sizing coefficients (Fl, Xt, Fd) and Cv series for globe and rotary valves. Covers VendorValveDefinition dataclass, FISHER_VENDOR_CATALOG, get_vendor_definition, get_vendor_options, and ValveSize. USE FOR: adding new vendor families, updating sizing coefficients, adding Cv series entries, debugging vendor selection logic."
license: MIT
metadata:
  project: control-valve-sizing
  module: vendor_catalog.py
  version: "1.0"
---

# Vendor Valve Catalog

Module: `vendor_catalog.py` (~131 lines). Contains Emerson Fisher representative sizing data.

## Data Structure

### VendorValveDefinition
```python
VendorValveDefinition(
    key: str,              # e.g. "fisher_globe_eqpct"
    vendor: str,           # "Emerson Fisher"
    family: str,           # "Representative Globe"
    style: str,            # "Cage-Guided Equal-Percentage"
    service: str,          # "liquid_gas_steam"
    source_note: str,      # Citation from Fisher Handbook
    source_url: str,       # Link to Fisher Handbook PDF
    fl: float | None,      # Liquid pressure recovery factor
    xt: float | None,      # Pressure drop ratio factor (gas/steam)
    fd: float | None,      # Valve style modifier
    opening_desc: str,     # e.g. "Rated travel representative values"
    sizes: tuple[ValveSize, ...],  # Cv-rated sizes
)
```

### ValveSize
```python
ValveSize(dn_mm: int, inch: str, cv_rated: float)
```

## Current Catalog (4 entries)

| Key | Style | FL | xT | Fd | Min DN | Max DN |
|---|---|---|---|---|---|---|
| `fisher_globe_eqpct` | Cage-Guided Equal-% | 0.85 | 0.69 | 0.31 | 25 | 200 |
| `fisher_globe_linear` | Cage-Guided Linear | 0.82 | 0.64 | 0.30 | 25 | 200 |
| `fisher_vnotch_90` | V-Notch Ball | 0.74 | 0.27 | 0.99 | 25 | 250 |
| `fisher_bfly_90` | HP Butterfly | 0.55 | 0.20 | 0.70 | 50 | 300 |

**Source**: Fisher Control Valve Handbook, Chapter 5.10.1-5.10.2 (representative values).

## API

```python
get_vendor_options() → list[str]          # all catalog keys
get_vendor_definition(key) → VendorValveDefinition  # raises KeyError if unknown
```

## How Sizing Uses Vendor Data

Both `app_desktop.py` and `app_web.py`:
1. User selects `vendor_key` → `get_vendor_definition(vendor_key)`
2. Vendor's `sizes` passed as `valve_series` to `size_*_valve()`
3. Vendor's `fl`, `xt`, `fd` used as defaults (UI can override via input fields)
4. Vendor info stored in `valve_meta` dict in `SizingResult`

## When adding a new valve family
1. Create `VendorValveDefinition` with all fields
2. Add to `FISHER_VENDOR_CATALOG` dict
3. Add test in `test_vendor_catalog.py` for the new key
4. Ensure `sizes` are sorted by `dn_mm` and `cv_rated` is monotonic
