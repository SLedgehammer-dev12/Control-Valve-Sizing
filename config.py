"""Shared configuration constants for gas presets and default composition rows.

Used by app_desktop, app_web, and standalone scripts to avoid duplicating
gas mixture definitions."""

from __future__ import annotations

GAS_PRESETS: dict[str, dict] = {
    "Doğal Gaz": {
        "components": [
            {"component": "Methane", "fraction_pct": 90.0},
            {"component": "Ethane", "fraction_pct": 6.0},
            {"component": "Nitrogen", "fraction_pct": 2.0},
            {"component": "CarbonDioxide", "fraction_pct": 2.0},
        ],
    },
    "Hava": {
        "components": [
            {"component": "Nitrogen", "fraction_pct": 78.08},
            {"component": "Oxygen", "fraction_pct": 20.95},
            {"component": "Argon", "fraction_pct": 0.93},
            {"component": "CarbonDioxide", "fraction_pct": 0.04},
        ],
    },
    "Nitrojen": {
        "components": [
            {"component": "Nitrogen", "fraction_pct": 100.0},
        ],
    },
    "CO2": {
        "components": [
            {"component": "CarbonDioxide", "fraction_pct": 100.0},
        ],
    },
    "Argon": {
        "components": [
            {"component": "Argon", "fraction_pct": 100.0},
        ],
    },
    "Hidrojen": {
        "components": [
            {"component": "Hydrogen", "fraction_pct": 100.0},
        ],
    },
    "Propan": {
        "components": [
            {"component": "Propane", "fraction_pct": 100.0},
        ],
    },
    "Oksijen": {
        "components": [
            {"component": "Oxygen", "fraction_pct": 100.0},
        ],
    },
    "Metan": {
        "components": [
            {"component": "Methane", "fraction_pct": 100.0},
        ],
    },
    "Bütan": {
        "components": [
            {"component": "Butane", "fraction_pct": 100.0},
        ],
    },
    "Etan": {
        "components": [
            {"component": "Ethane", "fraction_pct": 100.0},
        ],
    },
    "Helyum": {
        "components": [
            {"component": "Helium", "fraction_pct": 100.0},
        ],
    },
    "Klor": {
        "components": [
            {"component": "Chlorine", "fraction_pct": 100.0},
        ],
    },
    "Amonyak": {
        "components": [
            {"component": "Ammonia", "fraction_pct": 100.0},
        ],
    },
    "Propan-Bütan (%50-50)": {
        "components": [
            {"component": "Propane", "fraction_pct": 50.0},
            {"component": "Butane", "fraction_pct": 50.0},
        ],
    },
    "Hava-Propan (%95-5)": {
        "components": [
            {"component": "Nitrogen", "fraction_pct": 74.18},
            {"component": "Oxygen", "fraction_pct": 19.90},
            {"component": "Argon", "fraction_pct": 0.88},
            {"component": "CarbonDioxide", "fraction_pct": 0.04},
            {"component": "Propane", "fraction_pct": 5.0},
        ],
    },
    "H2-NG %5 (blend)": {
        "components": [
            {"component": "Methane", "fraction_pct": 85.5},
            {"component": "Ethane", "fraction_pct": 5.7},
            {"component": "Nitrogen", "fraction_pct": 1.9},
            {"component": "CarbonDioxide", "fraction_pct": 1.9},
            {"component": "Hydrogen", "fraction_pct": 5.0},
        ],
    },
    "H2-NG %10 (blend)": {
        "components": [
            {"component": "Methane", "fraction_pct": 81.0},
            {"component": "Ethane", "fraction_pct": 5.4},
            {"component": "Nitrogen", "fraction_pct": 1.8},
            {"component": "CarbonDioxide", "fraction_pct": 1.8},
            {"component": "Hydrogen", "fraction_pct": 10.0},
        ],
    },
    "H2-NG %20 (blend)": {
        "components": [
            {"component": "Methane", "fraction_pct": 72.0},
            {"component": "Ethane", "fraction_pct": 4.8},
            {"component": "Nitrogen", "fraction_pct": 1.6},
            {"component": "CarbonDioxide", "fraction_pct": 1.6},
            {"component": "Hydrogen", "fraction_pct": 20.0},
        ],
    },
    "H2-NG %50 (blend)": {
        "components": [
            {"component": "Methane", "fraction_pct": 45.0},
            {"component": "Ethane", "fraction_pct": 3.0},
            {"component": "Nitrogen", "fraction_pct": 1.0},
            {"component": "CarbonDioxide", "fraction_pct": 1.0},
            {"component": "Hydrogen", "fraction_pct": 50.0},
        ],
    },
    "Sentez Gazi (Syngas)": {
        "components": [
            {"component": "CarbonMonoxide", "fraction_pct": 45.0},
            {"component": "Hydrogen", "fraction_pct": 45.0},
            {"component": "CarbonDioxide", "fraction_pct": 10.0},
        ],
    },
    "Hidrojen zengin (H2-CO2)": {
        "components": [
            {"component": "Hydrogen", "fraction_pct": 80.0},
            {"component": "CarbonDioxide", "fraction_pct": 20.0},
        ],
    },
}

GAS_PRESET_NAMES = list(GAS_PRESETS.keys())

DEFAULT_GAS_ROWS = [
    {"component": "Methane", "fraction_pct": 90.0},
    {"component": "Ethane", "fraction_pct": 6.0},
    {"component": "Nitrogen", "fraction_pct": 2.0},
    {"component": "CarbonDioxide", "fraction_pct": 2.0},
]
