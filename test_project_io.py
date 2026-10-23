from __future__ import annotations

import pytest

from project_io import (
    MAX_PROJECT_JSON_BYTES,
    dump_project_json,
    load_project_json,
    migrate_project_payload,
    validate_project_payload,
)


def test_project_io_roundtrip():
    data = {
        "liquid_flow_m3h": 50.0,
        "liquid_p1": 10.0,
        "liquid_p2": 6.0,
        "liquid_density": 998.0,
    }
    json_str = dump_project_json("liquid", data)
    loaded = load_project_json(json_str)
    assert loaded["service"] == "liquid"
    assert loaded["data"]["liquid_flow_m3h"] == 50.0


def test_project_io_rejects_oversized_payload():
    huge_data = "a" * (MAX_PROJECT_JSON_BYTES + 1024)
    with pytest.raises(ValueError, match="512 KB"):
        load_project_json(huge_data)


def test_project_io_rejects_non_dict():
    with pytest.raises(ValueError, match="JSON nesnesi"):
        validate_project_payload("not-a-dict")  # type: ignore


def test_project_io_rejects_wrong_project_type():
    with pytest.raises(ValueError, match="control valve sizing proje dosyasi degil"):
        validate_project_payload({"project_type": "other", "service": "liquid", "data": {}})


def test_project_io_rejects_zero_or_negative_density():
    payload = {
        "project_type": "control_valve_sizing",
        "schema_version": 1,
        "service": "liquid",
        "data": {
            "liquid_flow_m3h": 50.0,
            "liquid_p1": 10.0,
            "liquid_p2": 6.0,
            "liquid_density": 0.0,
        },
    }
    with pytest.raises(ValueError, match="pozitif olmalidir"):
        validate_project_payload(payload)


def test_project_io_rejects_invalid_unit():
    payload = {
        "project_type": "control_valve_sizing",
        "schema_version": 1,
        "service": "liquid",
        "data": {
            "liquid_flow_m3h": 50.0,
            "liquid_p1": 10.0,
            "liquid_p2": 6.0,
            "liquid_flow_unit": "invalid_unit_key",
        },
    }
    with pytest.raises(ValueError, match="gecersiz birim"):
        validate_project_payload(payload)


def test_project_io_migrates_legacy_schema_without_version():
    payload = {
        "project_type": "control_valve_sizing",
        "service": "liquid",
        "data": {
            "liquid_flow_m3h": 25.0,
            "liquid_p1": 8.0,
            "liquid_p2": 5.0,
        },
    }
    migrated = migrate_project_payload(payload)
    assert migrated["schema_version"] == 1


def test_project_io_rejects_future_schema():
    payload = {
        "project_type": "control_valve_sizing",
        "schema_version": 999,
        "service": "liquid",
        "data": {},
    }
    with pytest.raises(ValueError, match="daha yeni bir schema"):
        migrate_project_payload(payload)
