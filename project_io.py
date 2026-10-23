"""Project save/load utilities for control valve sizing.

Serialises service type and input data to/from JSON, including validation
of payload structure, schema versioning, and date-stamped metadata."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

from units import UNIT_MAPS

PROJECT_TYPE = "control_valve_sizing"

SCHEMA_VERSION = 1

SERVICE_REQUIRED_KEYS: dict[str, set[str]] = {
    "liquid": {"liquid_flow_m3h", "liquid_p1", "liquid_p2"},
    "gas": {"gas_flow_nm3h", "gas_p1", "gas_p2"},
    "steam": {"steam_flow_kgh", "steam_p1", "steam_p2"},
}

UNIT_VALIDATORS: dict[str, dict[str, str]] = {
    "liquid_temp_unit": UNIT_MAPS["temperature"],
    "liquid_pres_unit": UNIT_MAPS["pressure"],
    "liquid_flow_unit": UNIT_MAPS["liquid_flow"],
    "gas_temp_unit": UNIT_MAPS["temperature"],
    "gas_pres_unit": UNIT_MAPS["pressure"],
    "gas_flow_unit": UNIT_MAPS["gas_flow"],
    "steam_temp_unit": UNIT_MAPS["temperature"],
    "steam_pres_unit": UNIT_MAPS["pressure"],
    "steam_flow_unit": UNIT_MAPS["steam_flow"],
}


def build_project_payload(service: str, data: dict) -> dict:
    """Build a project payload dict with service type, data, and timestamp."""
    return {
        "project_type": PROJECT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "saved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "service": service,
        "data": data,
    }


def dump_project_json(service: str, data: dict) -> str:
    """Serialize a project payload to JSON string."""
    return json.dumps(build_project_payload(service, data), ensure_ascii=False, indent=2)


def migrate_project_payload(payload: dict) -> dict:
    """Return the payload migrated to the current schema version.

    v1 payloads (or legacy files without a schema_version) are accepted
    unchanged. Payloads from a newer schema raise ValueError so that the
    data is never silently misinterpreted.
    """
    version = payload.get("schema_version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("Proje dosyasi gecersiz bir schema_version iceriyor.")
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"Proje dosyasi bu programdan daha yeni bir schema kullaniyor (v{version}); "
            "once programi guncelleyin."
        )
    payload.setdefault("schema_version", SCHEMA_VERSION)
    return payload


def validate_project_payload(payload: dict) -> None:
    """Raise ValueError if payload is not a valid control valve sizing project."""
    if not isinstance(payload, dict):
        raise ValueError("Proje payload'i bir JSON nesnesi olmalidir.")
    if payload.get("project_type") != PROJECT_TYPE:
        raise ValueError("Bu dosya control valve sizing proje dosyasi degil.")
    service = payload.get("service")
    if not isinstance(service, str) or service.lower() not in {"liquid", "gas", "steam"}:
        raise ValueError("Project service degeri Liquid, Gas veya Steam olmalidir.")
    payload["service"] = service.lower()
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Proje data alanı bir JSON nesnesi olmalidir.")
    migrate_project_payload(payload)
    required = SERVICE_REQUIRED_KEYS.get(payload["service"], set())
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Proje verisinde eksik alanlar: {', '.join(sorted(missing))}.")
    for key in sorted(required):
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Proje verisinde '{key}' sayisal bir deger olmalidir.")
    for key, allowed in UNIT_VALIDATORS.items():
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, str):
            raise ValueError(f"Proje verisinde gecersiz birim: '{key}' = {value!r}.")
        if value in allowed:
            continue
        label_map = {label: unit_key for unit_key, label in allowed.items()}
        if value in label_map:
            data[key] = label_map[value]
            continue
        raise ValueError(f"Proje verisinde gecersiz birim: '{key}' = {value!r}.")


def load_project_json(text: str) -> dict:
    """Parse JSON string, validate, migrate, and return project payload."""
    payload = json.loads(text)
    validate_project_payload(payload)
    return migrate_project_payload(payload)
