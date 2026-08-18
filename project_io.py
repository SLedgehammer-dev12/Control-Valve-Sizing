"""Project save/load utilities for control valve sizing.

Serialises service type and input data to/from JSON, including validation
of payload structure, schema versioning, and date-stamped metadata."""

from __future__ import annotations

import json
from datetime import UTC, datetime

PROJECT_TYPE = "control_valve_sizing"

SCHEMA_VERSION = 1

SERVICE_REQUIRED_KEYS: dict[str, set[str]] = {
    "liquid": {"liquid_flow_m3h", "liquid_p1", "liquid_p2"},
    "gas": {"gas_flow_nm3h", "gas_p1", "gas_p2"},
    "steam": {"steam_flow_kgh", "steam_p1", "steam_p2"},
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
    if not isinstance(version, int) or version < 1:
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
    if isinstance(service, str) and service.lower() not in {"liquid", "gas", "steam"}:
        raise ValueError("Project service degeri Liquid, Gas veya Steam olmalidir.")
    payload["service"] = service.lower() if isinstance(service, str) else service
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Proje data alanı bir JSON nesnesi olmalidir.")
    migrate_project_payload(payload)
    required = SERVICE_REQUIRED_KEYS.get(payload["service"], set())
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Proje verisinde eksik alanlar: {', '.join(sorted(missing))}.")


def load_project_json(text: str) -> dict:
    """Parse JSON string, validate, migrate, and return project payload."""
    payload = json.loads(text)
    validate_project_payload(payload)
    return migrate_project_payload(payload)
