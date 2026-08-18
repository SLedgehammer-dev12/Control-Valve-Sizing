import pytest

from valve_sizing import ValveSize
from vendor_catalog import (
    ARCA_VENDOR_CATALOG,
    FISHER_VENDOR_CATALOG,
    METSO_VENDOR_CATALOG,
    SAMSON_VENDOR_CATALOG,
    VENDOR_CATALOG,
    get_vendor_definition,
    get_vendor_options,
)

ALL_CATALOGS = {"fisher": FISHER_VENDOR_CATALOG, "metso": METSO_VENDOR_CATALOG, "samson": SAMSON_VENDOR_CATALOG, "arca": ARCA_VENDOR_CATALOG}


def test_all_catalogs_have_entries():
    for name, cat in ALL_CATALOGS.items():
        assert len(cat) >= 2, f"{name} catalog has fewer than 2 entries"


def test_merged_catalog_equals_sum():
    total = sum(len(c) for c in ALL_CATALOGS.values())
    assert len(VENDOR_CATALOG) == total


def test_fisher_keys_preserved():
    assert len(FISHER_VENDOR_CATALOG) == 4
    assert "fisher_globe_eqpct" in FISHER_VENDOR_CATALOG
    assert "fisher_bfly_90" in FISHER_VENDOR_CATALOG


def test_metso_keys_present():
    assert len(METSO_VENDOR_CATALOG) >= 2
    assert "metso_globe_eqpct" in METSO_VENDOR_CATALOG


def test_samson_keys_present():
    assert len(SAMSON_VENDOR_CATALOG) >= 2
    assert "samson_globe_eqpct" in SAMSON_VENDOR_CATALOG


def test_arca_keys_present():
    assert len(ARCA_VENDOR_CATALOG) >= 2
    assert "arca_globe_eqpct" in ARCA_VENDOR_CATALOG


def test_get_vendor_options_returns_all():
    opts = get_vendor_options()
    assert len(opts) >= 10
    assert "fisher_globe_eqpct" in opts
    assert "metso_globe_eqpct" in opts
    assert "samson_globe_eqpct" in opts
    assert "arca_globe_eqpct" in opts
    assert "fisher_bfly_90" in opts


def test_get_vendor_definition_known():
    v = get_vendor_definition("fisher_globe_eqpct")
    assert v.vendor == "Emerson Fisher"
    assert v.style == "Cage-Guided Equal-Percentage"


def test_get_vendor_definition_metso():
    v = get_vendor_definition("metso_globe_eqpct")
    assert v.vendor == "Metso (Valmet)"
    assert v.fl == 0.85
    assert v.xt == 0.65


def test_get_vendor_definition_samson():
    v = get_vendor_definition("samson_globe_eqpct")
    assert v.vendor == "SAMSON"
    assert v.fl == 0.90
    assert v.xt == 0.70


def test_get_vendor_definition_arca():
    v = get_vendor_definition("arca_globe_eqpct")
    assert v.vendor == "ARCA"
    assert v.fl == 0.88
    assert v.xt == 0.68


def test_get_vendor_definition_unknown_raises():
    with pytest.raises(ValueError, match="Bilinmeyen vendor"):
        get_vendor_definition("nonexistent_vendor")


def test_all_vendors_have_valid_fl():
    for key, v in VENDOR_CATALOG.items():
        assert v.fl is None or 0.0 < v.fl <= 1.0, f"{key}: FL={v.fl} out of range"


def test_all_vendors_have_valid_xt():
    for key, v in VENDOR_CATALOG.items():
        assert v.xt is None or 0.0 < v.xt <= 1.0, f"{key}: xT={v.xt} out of range"


def test_all_vendors_have_valid_fd():
    for key, v in VENDOR_CATALOG.items():
        assert v.fd is None or 0.0 < v.fd <= 1.5, f"{key}: Fd={v.fd} out of range"


def test_all_vendor_sizes_are_monotonic():
    for key, v in VENDOR_CATALOG.items():
        cv_ratings = [s.cv_rated for s in v.sizes]
        assert cv_ratings == sorted(cv_ratings), f"{key}: Cv values not monotonic"


def test_all_vendors_have_at_least_3_sizes():
    for key, v in VENDOR_CATALOG.items():
        assert len(v.sizes) >= 3, f"{key}: only {len(v.sizes)} sizes"


def test_vendor_sizes_are_valvesize_instances():
    for v in VENDOR_CATALOG.values():
        for size in v.sizes:
            assert isinstance(size, ValveSize)


def test_all_vendors_have_distinct_keys():
    keys = list(VENDOR_CATALOG.keys())
    assert len(keys) == len(set(keys))


def test_vendors_have_pressure_and_leakage_class():
    for v in VENDOR_CATALOG.values():
        assert v.pressure_class.startswith("CL"), f"{v.key}: pressure_class={v.pressure_class}"
        assert v.leakage_class in {"II", "III", "IV", "V", "VI"}, f"{v.key}: leakage_class={v.leakage_class}"


def test_recommend_pressure_class_mapping():
    from valve_selection import recommend_pressure_class

    assert recommend_pressure_class(10.0) == "CL150"
    assert recommend_pressure_class(50.0) == "CL300"
    assert recommend_pressure_class(100.0) == "CL600"
    assert recommend_pressure_class(250.0) == "CL1500"
    assert recommend_pressure_class(500.0) == "CL2500"
    assert recommend_pressure_class(0.0) == "CL150"
    assert recommend_pressure_class(-5.0) == "CL150"


def test_recommend_fail_safe_branches():
    from valve_selection import recommend_fail_safe

    assert "fail-open" in recommend_fail_safe("liquid", "Cooling water")
    assert "fail-open" in recommend_fail_safe("liquid", "soğutma suyu")
    assert "fail-closed" in recommend_fail_safe("gas", "Fuel gas")
    assert "fail-closed" in recommend_fail_safe("gas", "yakıt hattı")
    assert "fail-closed" in recommend_fail_safe("steam")
    assert "fail-in-position" in recommend_fail_safe("liquid")


def test_recommend_leakage_class_by_service():
    from valve_selection import recommend_leakage_class

    assert recommend_leakage_class("gas") == "VI"
    assert recommend_leakage_class("steam") == "V"
    assert recommend_leakage_class("liquid") == "IV"
    assert recommend_leakage_class("liquid", is_choked=True) == "VI"


def test_build_valve_spec_contains_guidance():
    from valve_selection import build_valve_spec

    spec = build_valve_spec("liquid", 60.0, is_choked=True, regime="choked-cavitating")
    assert spec["pressure_class_recommended"] == "CL600"
    assert spec["leakage_class_recommended"] == "VI"
    assert "HAZOP" in spec["note"]


def test_fisher_handbook_coefficients_match_reference():
    eqpct = get_vendor_definition("fisher_globe_eqpct")
    linear = get_vendor_definition("fisher_globe_linear")
    vnotch = get_vendor_definition("fisher_vnotch_90")
    assert (eqpct.fl, eqpct.xt, eqpct.fd) == pytest.approx((0.85, 0.69, 0.31))
    assert (linear.fl, linear.xt, linear.fd) == pytest.approx((0.82, 0.64, 0.30))
    assert (vnotch.fl, vnotch.xt, vnotch.fd) == pytest.approx((0.74, 0.27, 0.99))


def test_veeball_cv_close_to_published_reference():
    v = get_vendor_definition("fisher_vnotch_90")
    by_dn = {s.dn_mm: s.cv_rated for s in v.sizes}
    published = {25: 33.1, 40: 70.8, 50: 122.0}
    for dn, cv in published.items():
        assert by_dn[dn] == pytest.approx(cv, rel=0.10), f"DN{dn} Cv off reference"


def test_vendor_source_urls_are_https():
    for v in VENDOR_CATALOG.values():
        assert v.source_url.startswith("https://"), f"{v.key}: non-HTTPS source"
        assert len(v.source_note) > 20, f"{v.key}: missing source note"
