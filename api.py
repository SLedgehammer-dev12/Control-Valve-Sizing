"""FastAPI backend for the browser control-valve sizing application."""

from __future__ import annotations

import logging
import math
import numbers
import os
import sys
from dataclasses import asdict, is_dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from config import GAS_PRESETS
from datasheet_isa20 import build_isa20_datasheet, generate_isa20_html, generate_isa20_markdown
from flow_2d_model import simulate_flow_2d
from fluid_properties import (
    GAS_COMPONENT_ALIASES,
    LIQUID_PRESETS,
    evaluate_gas_mixture,
    evaluate_liquid_preset,
    evaluate_steam_state,
    gas_component_options,
    get_pure_fluid_state,
    get_steam_properties_iapws,
    prepare_composition_rows,
)
from multi_case import OperatingCase, size_multicase
from project_io import build_project_payload, validate_project_payload
from reporting import build_report
from units import (
    DEFAULT_UNITS,
    GAS_FLOW_UNITS,
    LIQUID_FLOW_UNITS,
    PRESSURE_UNITS,
    STEAM_FLOW_UNITS,
    TEMPERATURE_UNITS,
    convert_unit,
    gas_flow_to_nm3h,
    liquid_flow_to_m3h,
    pressure_to_bar_a,
    steam_flow_to_kgh,
    temperature_to_c,
    validate_unit_key,
)
from valve_3d import build_valve_figure
from valve_curve import (
    calc_installed_flow_ratio,
    cv_at_opening,
    generate_characteristic_curve,
    generate_installed_characteristic,
)
from valve_sizing import (
    GasSizingInput,
    LiquidSizingInput,
    SizingResult,
    SteamSizingInput,
    __version__,
    _pack_result,
    size_gas_valve,
    size_liquid_valve,
    size_steam_valve,
)
from vendor_catalog import find_catalog_matches, get_vendor_definition, get_vendor_options

logger = logging.getLogger(__name__)

_CSP_IMPORTMAP_HASH = "sha256-xf3sU1w0Wr567uJ/u9YBdQqa41lxIgMCRWfThIuPGZw="

def _resolve_web_dir() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(Path(meipass) / "webapp")
        exe_dir = Path(sys.executable).parent
        candidates.append(exe_dir / "webapp")
        candidates.append(exe_dir / "_internal" / "webapp")
    candidates.append(Path(__file__).resolve().parent / "webapp")
    for cand in candidates:
        if cand.is_dir():
            return cand
    return candidates[0]


WEB_DIR = _resolve_web_dir()
CHARACTERISTICS = [
    {"key": "equal_percentage", "label": "Eşit Yüzde"},
    {"key": "linear", "label": "Doğrusal"},
    {"key": "quick_opening", "label": "Hızlı Açma"},
]
PART_COLORS = {
    "Gövde": "#94a3b8",
    "Giriş": "#94a3b8",
    "Çıkış": "#94a3b8",
    "Giriş flanşı": "#2563eb",
    "Çıkış flanşı": "#2563eb",
    "Bonnet": "#64748b",
    "Mil": "#475569",
    "El çarkı": "#ef4444",
}

_docs_enabled = os.getenv("CVS_ENABLE_DOCS") == "1"
app = FastAPI(
    title="Control Valve Sizing API",
    version=__version__,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > 1_000_000:
            response = JSONResponse(status_code=413, content={"detail": "İstek gövdesi çok büyük."})
        else:
            response = await call_next(request)
    else:
        response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    path = request.url.path
    if path.startswith("/vendor/"):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    elif path in {"/", "/index.html", "/app.js", "/flow_2d_viewer.js", "/styles.css", "/sw.js", "/manifest.json"}:
        response.headers.setdefault("Cache-Control", "no-cache")
    elif path in {"/api/meta", "/api/valve-mesh"}:
        response.headers.setdefault("Cache-Control", "public, max-age=3600")
    response.headers.setdefault(
        "Content-Security-Policy",
        (
            f"default-src 'self'; script-src 'self' '{_CSP_IMPORTMAP_HASH}'; "
            "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'; frame-src 'none'"
        ),
    )
    return response


@app.exception_handler(RequestValidationError)
async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [{"loc": error.get("loc"), "msg": error.get("msg"), "type": error.get("type")} for error in exc.errors()]
    return JSONResponse(status_code=400, content={"detail": details})


class LiquidRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    flow_value: float
    flow_unit: str = "m3h"
    pressure_unit: str = "bar_a"
    p1_value: float
    p2_value: float
    temperature_value: float = 25.0
    temperature_unit: str = "C"
    density_kg_m3: float
    vapor_pressure_value: float
    vapor_pressure_unit: str = "bar_a"
    critical_pressure_value: float
    critical_pressure_unit: str = "bar_a"
    viscosity_pa_s: float
    vendor: str = "fisher_globe_eqpct"
    design_margin_pct: float = 0.0
    flow_characteristic: str = "equal_percentage"
    pipe_inlet_diameter_mm: float | None = None
    pipe_outlet_diameter_mm: float | None = None
    authority_pr: float = 0.5
    target_dn_mm: float | None = None


class GasComponent(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    component: str = Field(..., min_length=1, max_length=64)
    fraction_pct: float = Field(..., ge=0, le=100)


class GasRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    flow_value: float
    flow_unit: str = "nm3h"
    pressure_unit: str = "bar_a"
    p1_value: float
    p2_value: float
    temperature_value: float = 20.0
    temperature_unit: str = "C"
    gas_preset: str = "Doğal Gaz"
    composition: list[GasComponent] | None = Field(default=None, max_length=20)
    composition_basis: str = "molar"
    gas_model: str = "auto"
    molecular_weight: float | None = None
    specific_heat_ratio: float | None = None
    z: float | None = None
    viscosity_pa_s: float | None = None
    vendor: str = "fisher_globe_eqpct"
    design_margin_pct: float = 0.0
    flow_characteristic: str = "equal_percentage"
    pipe_inlet_diameter_mm: float | None = None
    pipe_outlet_diameter_mm: float | None = None
    authority_pr: float = 0.5
    target_dn_mm: float | None = None


class SteamRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    flow_value: float
    flow_unit: str = "kgh"
    pressure_unit: str = "bar_a"
    p1_value: float
    p2_value: float
    temperature_value: float = 220.0
    temperature_unit: str = "C"
    vendor: str = "fisher_globe_eqpct"
    design_margin_pct: float = 0.0
    flow_characteristic: str = "equal_percentage"
    pipe_inlet_diameter_mm: float | None = None
    pipe_outlet_diameter_mm: float | None = None
    authority_pr: float = 0.5
    target_dn_mm: float | None = None


class GasPropertiesRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    gas_preset: str = "Doğal Gaz"
    composition: list[GasComponent] | None = Field(default=None, max_length=20)
    composition_basis: str = "molar"
    gas_model: str = "auto"
    pressure_value: float
    pressure_unit: str = "bar_a"
    temperature_value: float = 20.0
    temperature_unit: str = "C"


class LiquidPropertiesRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    preset: str
    pressure_value: float
    pressure_unit: str = "bar_a"
    temperature_value: float
    temperature_unit: str = "C"


class ConvertRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    kind: str
    values: list[float] = Field(..., max_length=1000)
    from_unit: str
    to_unit: str
    pressure_bar_a: float | None = None
    temperature_c: float | None = None
    z: float | None = None
    density_kg_m3: float | None = None
    gas_preset: str | None = None
    composition: list[GasComponent] | None = Field(default=None, max_length=20)
    composition_basis: str = "molar"
    gas_model: str = "auto"
    molecular_weight: float | None = None
    specific_heat_ratio: float | None = None
    viscosity_pa_s: float | None = None


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        return number if math.isfinite(number) else None
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _unit_or_400(kind: str, unit: str) -> str:
    try:
        return validate_unit_key(kind, unit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _number_or_400(value: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{name} sayısal olmalıdır.") from exc
    if not math.isfinite(number):
        raise HTTPException(status_code=400, detail=f"{name} sonlu bir sayı olmalıdır.")
    return number


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _require_positive(value: float, name: str) -> float:
    number = _number_or_400(value, name)
    if number <= 0:
        raise HTTPException(status_code=400, detail=f"{name} pozitif olmalıdır.")
    return number


def _absolute_pressure_or_400(value: float, unit: str, name: str) -> float:
    pressure = pressure_to_bar_a(_number_or_400(value, name), unit)
    if pressure <= 0:
        raise HTTPException(status_code=400, detail=f"{name} (mutlak) pozitif olmalıdır.")
    return pressure


def _temperature_or_400(value: float, unit: str) -> float:
    temperature = temperature_to_c(_number_or_400(value, "Sıcaklık"), unit)
    if temperature <= -273.15:
        raise HTTPException(status_code=400, detail="Sıcaklık mutlak sıfırın üzerinde olmalıdır.")
    return temperature


def _validate_gas_process(p1_bar: float, temperature_c: float) -> None:
    if not math.isfinite(p1_bar) or p1_bar <= 0:
        raise HTTPException(status_code=400, detail="Giriş basıncı (mutlak) pozitif olmalıdır.")
    if not math.isfinite(temperature_c) or temperature_c <= -273.15:
        raise HTTPException(status_code=400, detail="Sıcaklık mutlak sıfırın üzerinde olmalıdır.")


def _vendor(vendor_key: str):
    try:
        definition = get_vendor_definition(vendor_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    meta = {
        "vendor": definition.vendor,
        "family": definition.family,
        "style": definition.style,
        "service": definition.service,
        "FL": definition.fl,
        "xT": definition.xt,
        "Fd": definition.fd,
        "opening": definition.opening_desc,
        "source": definition.source_note,
        "source_url": definition.source_url,
        "pressure_class": definition.pressure_class,
        "leakage_class": definition.leakage_class,
    }
    return definition, meta


def _characteristic_or_400(value: str) -> str:
    allowed = {item["key"] for item in CHARACTERISTICS}
    if value not in allowed:
        raise HTTPException(status_code=400, detail=f"Geçersiz akış karakteristiği: {value}")
    return value


def _validate_pipes(pipe_in: float | None, pipe_out: float | None) -> None:
    for name, value in (("Giriş çapı", pipe_in), ("Çıkış çapı", pipe_out)):
        if value is not None and _number_or_400(value, name) <= 0:
            raise HTTPException(status_code=400, detail=f"{name} pozitif olmalıdır.")


def _gas_summary_from_preset(gas_preset: str, p1_bar: float, temperature_c: float, gas_model: str = "auto") -> dict[str, Any]:
    _validate_gas_process(p1_bar, temperature_c)
    preset = GAS_PRESETS.get(gas_preset)
    if preset is None:
        raise HTTPException(status_code=400, detail=f"Bilinmeyen gaz preset'i: {gas_preset}")
    try:
        summary = evaluate_gas_mixture(preset["components"], "molar", p1_bar, temperature_c, gas_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Gas properties calculation failed")
        raise HTTPException(status_code=400, detail="Gaz özellikleri hesaplanamadı.") from None
    return {
        "mode": "preset",
        "gas_preset": gas_preset,
        "average_molecular_weight": summary.average_molecular_weight,
        "z": summary.z or 1.0,
        "density_kg_m3": summary.density_kg_m3,
        "viscosity_pa_s": summary.viscosity_pa_s or 1e-5,
        "cp_j_kgk": summary.cp_j_kgk,
        "cv_j_kgk": summary.cv_j_kgk,
        "specific_heat_ratio": summary.specific_heat_ratio or 1.30,
        "mixture_string": summary.mixture_string,
        "phase": summary.phase,
        "fallback_used": summary.fallback_used,
        "model_used": summary.model_used,
        "property_warning": (
            "CoolProp HEOS kullanılamadı; ideal gaz varsayımları kullanıldı."
            if summary.fallback_used
            else None
        ),
    }


def _gas_manual_or_400(
    molecular_weight: float | None,
    specific_heat_ratio: float | None,
    z: float | None,
    viscosity_pa_s: float | None,
    p1_bar: float,
    temperature_c: float,
) -> dict[str, Any] | None:
    _validate_gas_process(p1_bar, temperature_c)
    values = (molecular_weight, specific_heat_ratio, z, viscosity_pa_s)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise HTTPException(
            status_code=400,
            detail="Manuel gaz özellikleri için moleküler ağırlık, k, Z ve viskozite birlikte girilmelidir.",
        )
    assert molecular_weight is not None
    assert specific_heat_ratio is not None
    assert z is not None
    assert viscosity_pa_s is not None
    mw = _number_or_400(molecular_weight, "Moleküler ağırlık")
    k = _number_or_400(specific_heat_ratio, "k")
    z_value = _number_or_400(z, "Z")
    mu = _number_or_400(viscosity_pa_s, "Viskozite")
    if mw <= 0 or k <= 0 or z_value <= 0 or mu <= 0:
        raise HTTPException(status_code=400, detail="Gaz özellikleri pozitif olmalıdır.")
    density = (p1_bar * 1e5 * mw) / (8314.0 * (temperature_c + 273.15) * z_value)
    return {
        "mode": "manual",
        "gas_preset": None,
        "average_molecular_weight": mw,
        "z": z_value,
        "density_kg_m3": density,
        "viscosity_pa_s": mu,
        "cp_j_kgk": None,
        "cv_j_kgk": None,
        "specific_heat_ratio": k,
        "mixture_string": None,
        "phase": None,
        "fallback_used": False,
        "model_used": "manual",
        "property_warning": None,
    }


def _gas_summary(
    gas_preset: str,
    p1_bar: float,
    temperature_c: float,
    molecular_weight: float | None = None,
    specific_heat_ratio: float | None = None,
    z: float | None = None,
    viscosity_pa_s: float | None = None,
    composition: list[dict[str, Any]] | None = None,
    composition_basis: str = "molar",
    gas_model: str = "auto",
) -> dict[str, Any]:
    manual = _gas_manual_or_400(
        molecular_weight, specific_heat_ratio, z, viscosity_pa_s, p1_bar, temperature_c
    )
    if composition is not None:
        if manual is not None:
            raise HTTPException(status_code=400, detail="Manuel gaz ozellikleri ile kompozisyon ayni anda kullanilamaz.")
        if not composition:
            raise HTTPException(status_code=400, detail="Gaz kompozisyonu bos olamaz.")
        basis = composition_basis.strip().lower()
        if basis not in {"molar", "mass"}:
            raise HTTPException(status_code=400, detail="Kompozisyon bazisi 'molar' veya 'mass' olmalidir.")
        try:
            normalized_rows, input_total = prepare_composition_rows(composition)
            summary = evaluate_gas_mixture(normalized_rows, basis, p1_bar, temperature_c, gas_model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "mode": "composition",
            "gas_preset": None,
            "composition_basis": basis,
            "input_total_percent": input_total,
            "normalized": abs(input_total - 100.0) > 1e-6,
            "components": normalized_rows,
            "mole_fractions": summary.mole_fractions,
            "mass_fractions": summary.mass_fractions,
            "average_molecular_weight": summary.average_molecular_weight,
            "z": summary.z or 1.0,
            "density_kg_m3": summary.density_kg_m3,
            "viscosity_pa_s": summary.viscosity_pa_s or 1e-5,
            "cp_j_kgk": summary.cp_j_kgk,
            "cv_j_kgk": summary.cv_j_kgk,
            "specific_heat_ratio": summary.specific_heat_ratio or 1.30,
            "mixture_string": summary.mixture_string,
            "phase": summary.phase,
            "fallback_used": summary.fallback_used,
            "model_used": summary.model_used,
            "property_warning": (
                "CoolProp HEOS kullanılamadı; ideal gaz varsayımları kullanıldı."
                if summary.fallback_used else None
            ),
        }
    if manual is not None:
        manual["model_used"] = "manual"
        return manual
    return _gas_summary_from_preset(gas_preset, p1_bar, temperature_c, gas_model)


def _reject_non_gas_phase(fluid: dict[str, Any]) -> None:
    phase = fluid.get("phase")
    labels = {"liquid": "sıvı", "supercritical_liquid": "süperkritik sıvı", "two_phase": "iki fazlı"}
    if phase in labels:
        raise HTTPException(
            status_code=400,
            detail=f"Seçilen P/T'de gaz {labels[phase]} fazında; gaz sizing için gaz veya süperkritik gaz fazı gerekir.",
        )


@lru_cache(maxsize=64)
def _valve_mesh_cached(dn_mm: int) -> tuple[dict[str, Any], ...]:
    figure = build_valve_figure(float(dn_mm))
    parts: list[dict[str, Any]] = []
    for trace in figure.data:
        x = list(trace.x) if trace.x is not None else []
        y = list(trace.y) if trace.y is not None else []
        z = list(trace.z) if trace.z is not None else []
        i = list(trace.i) if trace.i is not None else []
        j = list(trace.j) if trace.j is not None else []
        k = list(trace.k) if trace.k is not None else []
        positions: list[float] = []
        for px, py, pz in zip(x, y, z, strict=False):
            positions.extend((float(px), float(py), float(pz)))
        indices: list[int] = []
        for a, b, c in zip(i, j, k, strict=False):
            indices.extend((int(a), int(b), int(c)))
        name = str(trace.name or "Parça")
        parts.append(
            {
                "name": name,
                "color": PART_COLORS.get(name, "#94a3b8"),
                "positions": positions,
                "indices": indices,
            }
        )
    return tuple(parts)


def _valve_mesh(dn_mm: float) -> list[dict[str, Any]]:
    dn = int(round(_clamp(float(dn_mm), 15.0, 600.0)))
    return [dict(part) for part in _valve_mesh_cached(dn)]


def _visuals(result: SizingResult, characteristic: str, authority_pr: float) -> dict[str, Any]:
    rated_cv = float(result.rated_cv)
    design_cv = float(result.required_cv) * (1.0 + max(float(result.design_margin_pct), 0.0) / 100.0)
    curve = generate_characteristic_curve(rated_cv, design_cv, characteristic)
    installed = generate_installed_characteristic(
        rated_cv, design_cv, characteristic, valve_authority_pr=authority_pr
    )
    openings = list(range(0, 101, 5))
    authorities = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    flow_grid: list[list[float]] = []
    for pr in authorities:
        row: list[float] = []
        for pct in openings:
            cv = cv_at_opening(pct, rated_cv, characteristic)
            ratio = min(cv / rated_cv, 1.0) if rated_cv > 0 else 0.0
            row.append(round(calc_installed_flow_ratio(ratio, pr) * 100.0, 2))
        flow_grid.append(row)
    opening_pct = _clamp(float(result.opening_percent), 0.0, 100.0)
    op_cv = cv_at_opening(opening_pct, rated_cv, characteristic)
    op_ratio = min(op_cv / rated_cv, 1.0) if rated_cv > 0 else 0.0
    operating_flow = calc_installed_flow_ratio(op_ratio, authority_pr) * 100.0
    return {
        "curve": curve.to_dict(),
        "installed": installed.to_dict(),
        "surface": {
            "openings": openings,
            "authorities": authorities,
            "flow_pct": flow_grid,
            "operating": {
                "opening_pct": opening_pct,
                "authority_pr": authority_pr,
                "flow_pct": round(operating_flow, 2),
            },
        },
    }


def _response(
    result: SizingResult,
    fluid: dict[str, Any],
    vendor_meta: dict[str, Any],
    characteristic: str,
    authority_pr: float,
    pipe_inlet_diameter_mm: float | None = None,
    pipe_outlet_diameter_mm: float | None = None,
) -> dict[str, Any]:
    payload = _json_safe(asdict(result))
    extra = payload.pop("extra", {}) or {}
    payload.update(extra)
    if pipe_inlet_diameter_mm is not None:
        payload["pipe_inlet_diameter_mm"] = pipe_inlet_diameter_mm
    if pipe_outlet_diameter_mm is not None:
        payload["pipe_outlet_diameter_mm"] = pipe_outlet_diameter_mm
    payload["fluid"] = _json_safe(fluid)
    payload["vendor"] = _json_safe(vendor_meta)
    payload["visuals"] = _json_safe(_visuals(result, characteristic, authority_pr))
    return _json_safe(payload)


def _run_sizing(operation, *args, **kwargs) -> SizingResult:
    try:
        return operation(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Sizing operation failed")
        raise HTTPException(status_code=500, detail="Hesaplama hatası.") from None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


def _vendor_list() -> list[dict[str, Any]]:
    vendors = []
    for key in get_vendor_options():
        definition = get_vendor_definition(key)
        vendors.append(
            {
                "key": key,
                "label": f"{definition.vendor} · {definition.family} · {definition.style}",
                "vendor": definition.vendor,
                "region": definition.region,
                "family": definition.family,
                "style": definition.style,
                "service": definition.service,
                "fl": definition.fl,
                "xt": definition.xt,
                "fd": definition.fd,
                "sizes": [
                    {"dn_mm": size.dn_mm, "inch": size.inch, "cv_rated": size.cv_rated}
                    for size in definition.sizes
                ],
            }
        )
    return vendors


@app.get("/api/vendors")
def vendors() -> list[dict[str, Any]]:
    return _vendor_list()


@app.get("/api/catalog-matches")
def catalog_matches(
    required_cv: float,
    design_margin: float = 10.0,
    characteristic: str = "equal_percentage",
    region: str | None = None,
) -> list[dict[str, Any]]:
    matches = find_catalog_matches(
        required_cv=required_cv,
        design_margin_pct=design_margin,
        flow_characteristic=characteristic,
        region_filter=region,
    )
    return [
        {
            "vendor_key": m.vendor_key,
            "vendor_name": m.vendor_name,
            "region": m.region,
            "family": m.family,
            "style": m.style,
            "dn_mm": m.dn_mm,
            "dn_inch": m.dn_inch,
            "rated_cv": m.rated_cv,
            "required_cv": m.required_cv,
            "opening_pct": m.opening_pct,
            "status": m.status,
            "status_label": m.status_label,
            "pressure_class": m.pressure_class,
            "leakage_class": m.leakage_class,
            "fl": m.fl,
            "xt": m.xt,
        }
        for m in matches
    ]


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    vendors = _vendor_list()
    units = {
        "temperature": [{"key": key, "label": label} for key, label in TEMPERATURE_UNITS.items()],
        "pressure": [{"key": key, "label": label} for key, label in PRESSURE_UNITS.items()],
        "liquid_flow": [{"key": key, "label": label} for key, label in LIQUID_FLOW_UNITS.items()],
        "gas_flow": [{"key": key, "label": label} for key, label in GAS_FLOW_UNITS.items()],
        "steam_flow": [{"key": key, "label": label} for key, label in STEAM_FLOW_UNITS.items()],
    }
    return {
        "version": __version__,
        "vendors": vendors,
        "units": units,
        "default_units": DEFAULT_UNITS,
        "characteristics": CHARACTERISTICS,
        "liquid_presets": [
            {"key": key, **preset} for key, preset in LIQUID_PRESETS.items()
        ],
        "gas_presets": [{"name": name, **preset} for name, preset in GAS_PRESETS.items()],
        "gas_components": gas_component_options(),
        "gas_component_aliases": GAS_COMPONENT_ALIASES,
    }


@app.get("/api/valve-mesh")
def valve_mesh(dn: float = Query(50.0, ge=15.0, le=600.0)) -> dict[str, Any]:
    return {"dn_mm": int(round(dn)), "parts": _valve_mesh(dn)}


@app.post("/api/gas-properties")
def gas_properties(request: GasPropertiesRequest) -> dict[str, Any]:
    pressure_unit = _unit_or_400("pressure", request.pressure_unit)
    temperature_unit = _unit_or_400("temperature", request.temperature_unit)
    p1_bar = _absolute_pressure_or_400(request.pressure_value, pressure_unit, "Giriş basıncı")
    temperature_c = _temperature_or_400(request.temperature_value, temperature_unit)
    composition = [row.model_dump() for row in request.composition] if request.composition is not None else None
    return _json_safe(
        _gas_summary(
            request.gas_preset,
            p1_bar,
            temperature_c,
            composition=composition,
            composition_basis=request.composition_basis,
            gas_model=request.gas_model,
        )
    )


@app.post("/api/liquid-properties")
def liquid_properties(request: LiquidPropertiesRequest) -> dict[str, Any]:
    pressure_unit = _unit_or_400("pressure", request.pressure_unit)
    temperature_unit = _unit_or_400("temperature", request.temperature_unit)
    pressure_bar_a = _absolute_pressure_or_400(request.pressure_value, pressure_unit, "Giriş basıncı")
    temperature_c = _temperature_or_400(request.temperature_value, temperature_unit)
    try:
        return _json_safe(evaluate_liquid_preset(request.preset, pressure_bar_a, temperature_c))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/convert")
def convert(request: ConvertRequest) -> dict[str, Any]:
    if request.kind not in {"temperature", "pressure", "liquid_flow", "gas_flow", "steam_flow"}:
        raise HTTPException(status_code=400, detail=f"Bilinmeyen birim türü: {request.kind}")
    from_unit = _unit_or_400(request.kind, request.from_unit)
    to_unit = _unit_or_400(request.kind, request.to_unit)
    if not request.values:
        raise HTTPException(status_code=400, detail="Dönüştürülecek değer listesi boş.")
    values = [_number_or_400(value, "Değer") for value in request.values]
    density = request.density_kg_m3
    z = request.z
    if request.kind == "gas_flow" and (
        request.from_unit in {"m3h", "kgh"} or request.to_unit in {"m3h", "kgh"}
    ):
        p1_bar = request.pressure_bar_a
        temperature_c = request.temperature_c
        if p1_bar is None or temperature_c is None:
            raise HTTPException(
                status_code=400, detail="Gaz debi dönüşümü için giriş basıncı ve sıcaklık gereklidir."
            )
        summary = _gas_summary(
            request.gas_preset or "Doğal Gaz",
            p1_bar,
            temperature_c,
            request.molecular_weight,
            request.specific_heat_ratio,
            request.z,
            request.viscosity_pa_s,
            composition=[row.model_dump() for row in request.composition] if request.composition is not None else None,
            composition_basis=request.composition_basis,
            gas_model=request.gas_model,
        )
        density = summary["density_kg_m3"]
        z = summary["z"]
    try:
        converted = [
            convert_unit(
                request.kind,
                value,
                from_unit,
                to_unit,
                density_kg_m3=density,
                pressure_bar_a=request.pressure_bar_a,
                temperature_c=request.temperature_c,
                z=z if z is not None else 1.0,
            )
            for value in values
        ]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if any(not math.isfinite(value) for value in converted):
        raise HTTPException(status_code=400, detail="Dönüşüm sonucu geçersiz.")
    return {"values": _json_safe(converted)}


@app.post("/api/size/liquid")
def size_liquid(request: LiquidRequest) -> dict[str, Any]:
    flow_unit = _unit_or_400("liquid_flow", request.flow_unit)
    pressure_unit = _unit_or_400("pressure", request.pressure_unit)
    temperature_unit = _unit_or_400("temperature", request.temperature_unit)
    characteristic = _characteristic_or_400(request.flow_characteristic)
    _validate_pipes(request.pipe_inlet_diameter_mm, request.pipe_outlet_diameter_mm)
    definition, vendor_meta = _vendor(request.vendor)
    density = _require_positive(request.density_kg_m3, "Yoğunluk")
    viscosity = _require_positive(request.viscosity_pa_s, "Viskozite")
    p1_bar = _absolute_pressure_or_400(request.p1_value, pressure_unit, "Giriş basıncı")
    p2_bar = _absolute_pressure_or_400(request.p2_value, pressure_unit, "Çıkış basıncı")
    vapor_pressure_unit = _unit_or_400("pressure", request.vapor_pressure_unit)
    critical_pressure_unit = _unit_or_400("pressure", request.critical_pressure_unit)
    pv_bar = pressure_to_bar_a(
        _number_or_400(request.vapor_pressure_value, "Buhar basıncı"), vapor_pressure_unit
    )
    if pv_bar < 0:
        raise HTTPException(status_code=400, detail="Buhar basıncı negatif olamaz.")
    pc_bar = _absolute_pressure_or_400(
        request.critical_pressure_value, critical_pressure_unit, "Kritik basınç"
    )
    temperature_c = _temperature_or_400(request.temperature_value, temperature_unit)
    flow_m3h = liquid_flow_to_m3h(
        _require_positive(request.flow_value, "Debi"), flow_unit, density
    )
    margin = _clamp(_number_or_400(request.design_margin_pct, "Tasarım marjı"), 0.0, 100.0)
    authority = _clamp(_number_or_400(request.authority_pr, "Otorite"), 0.01, 1.0)
    data = LiquidSizingInput(
        flow_m3h=flow_m3h,
        inlet_pressure_bar_a=p1_bar,
        outlet_pressure_bar_a=p2_bar,
        density_kg_m3=density,
        vapor_pressure_bar_a=pv_bar,
        critical_pressure_bar_a=pc_bar,
        viscosity_pa_s=viscosity,
        fl=definition.fl or 0.9,
        fd=definition.fd or 1.0,
        pipe_inlet_diameter_mm=request.pipe_inlet_diameter_mm,
        pipe_outlet_diameter_mm=request.pipe_outlet_diameter_mm,
        temperature_c=temperature_c,
    )
    result = _run_sizing(
        size_liquid_valve,
        data,
        valve_series=list(definition.sizes),
        valve_meta=vendor_meta,
        design_margin_pct=margin,
        flow_characteristic=characteristic,
        target_dn_mm=request.target_dn_mm,
    )
    fluid = {
        "service": "liquid",
        "temperature_c": temperature_c,
        "density_kg_m3": density,
        "vapor_pressure_bar_a": pv_bar,
        "critical_pressure_bar_a": pc_bar,
        "viscosity_pa_s": viscosity,
        "flow_m3h": flow_m3h,
        "vendor_fl": definition.fl,
        "vendor_fd": definition.fd,
    }
    return _response(
        result, fluid, vendor_meta, characteristic, authority,
        pipe_inlet_diameter_mm=request.pipe_inlet_diameter_mm,
        pipe_outlet_diameter_mm=request.pipe_outlet_diameter_mm,
    )


@app.post("/api/size/gas")
def size_gas(request: GasRequest) -> dict[str, Any]:
    flow_unit = _unit_or_400("gas_flow", request.flow_unit)
    pressure_unit = _unit_or_400("pressure", request.pressure_unit)
    temperature_unit = _unit_or_400("temperature", request.temperature_unit)
    characteristic = _characteristic_or_400(request.flow_characteristic)
    _validate_pipes(request.pipe_inlet_diameter_mm, request.pipe_outlet_diameter_mm)
    definition, vendor_meta = _vendor(request.vendor)
    p1_bar = _absolute_pressure_or_400(request.p1_value, pressure_unit, "Giriş basıncı")
    p2_bar = _absolute_pressure_or_400(request.p2_value, pressure_unit, "Çıkış basıncı")
    temperature_c = _temperature_or_400(request.temperature_value, temperature_unit)
    fluid = _gas_summary(
        request.gas_preset,
        p1_bar,
        temperature_c,
        request.molecular_weight,
        request.specific_heat_ratio,
        request.z,
        request.viscosity_pa_s,
        composition=[row.model_dump() for row in request.composition] if request.composition is not None else None,
        composition_basis=request.composition_basis,
        gas_model=request.gas_model,
    )
    _reject_non_gas_phase(fluid)
    flow_nm3h = gas_flow_to_nm3h(
        _require_positive(request.flow_value, "Debi"),
        flow_unit,
        pressure_bar_a=p1_bar,
        temperature_c=temperature_c,
        z=float(fluid["z"] or 1.0),
        density_kg_m3=fluid["density_kg_m3"],
    )
    margin = _clamp(_number_or_400(request.design_margin_pct, "Tasarım marjı"), 0.0, 100.0)
    authority = _clamp(_number_or_400(request.authority_pr, "Otorite"), 0.01, 1.0)
    data = GasSizingInput(
        flow_nm3h=flow_nm3h,
        inlet_pressure_bar_a=p1_bar,
        outlet_pressure_bar_a=p2_bar,
        temperature_c=temperature_c,
        molecular_weight=float(fluid["average_molecular_weight"]),
        specific_heat_ratio=float(fluid["specific_heat_ratio"] or 1.30),
        viscosity_pa_s=float(fluid["viscosity_pa_s"] or 1e-5),
        z=float(fluid["z"] or 1.0),
        fl=definition.fl or 0.9,
        fd=definition.fd or 1.0,
        xt=definition.xt or 0.7,
        pipe_inlet_diameter_mm=request.pipe_inlet_diameter_mm,
        pipe_outlet_diameter_mm=request.pipe_outlet_diameter_mm,
    )
    result = _run_sizing(
        size_gas_valve,
        data,
        valve_series=list(definition.sizes),
        valve_meta=vendor_meta,
        design_margin_pct=margin,
        flow_characteristic=characteristic,
        target_dn_mm=request.target_dn_mm,
    )
    fluid.update({"service": "gas", "flow_nm3h": flow_nm3h, "p1_bar_a": p1_bar, "p2_bar_a": p2_bar})
    return _response(
        result, fluid, vendor_meta, characteristic, authority,
        pipe_inlet_diameter_mm=request.pipe_inlet_diameter_mm,
        pipe_outlet_diameter_mm=request.pipe_outlet_diameter_mm,
    )


@app.post("/api/size/steam")
def size_steam(request: SteamRequest) -> dict[str, Any]:
    flow_unit = _unit_or_400("steam_flow", request.flow_unit)
    pressure_unit = _unit_or_400("pressure", request.pressure_unit)
    temperature_unit = _unit_or_400("temperature", request.temperature_unit)
    characteristic = _characteristic_or_400(request.flow_characteristic)
    _validate_pipes(request.pipe_inlet_diameter_mm, request.pipe_outlet_diameter_mm)
    definition, vendor_meta = _vendor(request.vendor)
    p1_bar = _absolute_pressure_or_400(request.p1_value, pressure_unit, "Giriş basıncı")
    p2_bar = _absolute_pressure_or_400(request.p2_value, pressure_unit, "Çıkış basıncı")
    temperature_c = _temperature_or_400(request.temperature_value, temperature_unit)
    phase_state = evaluate_steam_state(p1_bar, temperature_c)
    if phase_state["is_wet"]:
        raise HTTPException(
            status_code=400,
            detail="Islak/iki fazlı buhar için sıvı-buhar iki fazlı model kullanılmalıdır; kızgın veya doymuş buhar girin.",
        )
    flow_kg_h = steam_flow_to_kgh(_require_positive(request.flow_value, "Debi"), flow_unit)
    k = 1.30
    z = 1.0
    property_warning = None
    iapws = get_steam_properties_iapws(p1_bar, temperature_c)
    if iapws is not None:
        k = float(iapws["specific_heat_ratio"])
        z = float(iapws["z"])
    else:
        property_warning = "IAPWS-IF97 kullanılamadı; k/Z CoolProp veya ideal varsayımlardan alındı."
        try:
            props = get_pure_fluid_state("Water", p1_bar, temperature_c)
            k = float(props["specific_heat_ratio"])
            z = float(props["z"])
        except Exception:
            pass
    margin = _clamp(_number_or_400(request.design_margin_pct, "Tasarım marjı"), 0.0, 100.0)
    authority = _clamp(_number_or_400(request.authority_pr, "Otorite"), 0.01, 1.0)
    data = SteamSizingInput(
        flow_kg_h=flow_kg_h,
        inlet_pressure_bar_a=p1_bar,
        outlet_pressure_bar_a=p2_bar,
        temperature_c=temperature_c,
        specific_heat_ratio=k,
        z=z,
        xt=definition.xt or 0.72,
        fl=definition.fl or 0.9,
        fd=definition.fd or 1.0,
        pipe_inlet_diameter_mm=request.pipe_inlet_diameter_mm,
        pipe_outlet_diameter_mm=request.pipe_outlet_diameter_mm,
    )
    result = _run_sizing(
        size_steam_valve,
        data,
        valve_series=list(definition.sizes),
        valve_meta=vendor_meta,
        design_margin_pct=margin,
        flow_characteristic=characteristic,
        target_dn_mm=request.target_dn_mm,
    )
    fluid = {
        "service": "steam",
        "flow_kg_h": flow_kg_h,
        "temperature_c": temperature_c,
        "specific_heat_ratio": k,
        "z": z,
        "phase": phase_state["phase"],
        "phase_label": phase_state["phase_label"],
        "phase_warnings": phase_state["warnings"],
        "property_warning": property_warning,
        "vendor_xt": definition.xt,
    }
    return _response(
        result, fluid, vendor_meta, characteristic, authority,
        pipe_inlet_diameter_mm=request.pipe_inlet_diameter_mm,
        pipe_outlet_diameter_mm=request.pipe_outlet_diameter_mm,
    )


class ProjectExportRequest(BaseModel):
    service: str
    data: dict[str, Any]


@app.post("/api/project/export")
def export_project(req: ProjectExportRequest) -> JSONResponse:
    try:
        service = req.service.lower()
        payload = build_project_payload(service, req.data)
        validate_project_payload(payload)
        return JSONResponse(content=payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/project/import")
def import_project(payload: dict[str, Any]) -> JSONResponse:
    try:
        validate_project_payload(payload)
        return JSONResponse(content=payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ISA20ReportRequest(BaseModel):
    tag_number: str = "CV-101"
    service_description: str = "Proses Kontrol Vanası"
    line_number: str = '3"-P-101-CS'
    pid_number: str = "PID-010"
    service_type: str = "Liquid"
    fluid_name: str = "Water"
    sizing_result: dict[str, Any]
    vendor_key: str = "fisher_globe_eqpct"
    body_material: str = "WCB"
    bonnet_type: str = "Standard"
    end_connections: str = "Flanged ASME B16.5 RF"


@app.post("/api/report/isa20")
def generate_isa20(req: ISA20ReportRequest) -> dict[str, Any]:
    try:
        sheet = build_isa20_datasheet(
            tag_number=req.tag_number,
            service_description=req.service_description,
            line_number=req.line_number,
            pid_number=req.pid_number,
            service_type=req.service_type,
            fluid_name=req.fluid_name,
            sizing_result=req.sizing_result,
            vendor_key=req.vendor_key,
            body_material=req.body_material,
            bonnet_type=req.bonnet_type,
            end_connections=req.end_connections,
        )
        return {
            "markdown": generate_isa20_markdown(sheet),
            "html": generate_isa20_html(sheet),
            "datasheet": _json_safe(asdict(sheet)),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class MarkdownReportRequest(BaseModel):
    service: str
    fluid_summary: dict[str, Any] | None = None
    sizing_result: dict[str, Any]


@app.post("/api/report/markdown")
def generate_markdown_report(req: MarkdownReportRequest) -> dict[str, str]:
    try:
        sizing_obj = _pack_result(req.sizing_result)
        report_md = build_report(req.service, req.fluid_summary, sizing_obj)
        return {"report_markdown": report_md}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class MultiCaseInputItem(BaseModel):
    name: str
    flow: float
    p1_bar_a: float
    p2_bar_a: float
    temperature_c: float
    extra_props: dict[str, Any] = Field(default_factory=dict)


class MultiCaseRequest(BaseModel):
    service: str = "liquid"
    cases: list[MultiCaseInputItem]
    base_fluid_data: dict[str, Any]
    vendor: str = "fisher_globe_eqpct"
    flow_characteristic: str = "equal_percentage"
    pipe_inlet_diameter_mm: float | None = None
    pipe_outlet_diameter_mm: float | None = None


@app.post("/api/size/multi-case")
def size_multicase_endpoint(req: MultiCaseRequest) -> dict[str, Any]:
    try:
        service = req.service.lower()
        definition, _ = _vendor(req.vendor)
        cases = [
            OperatingCase(
                name=c.name,
                flow=c.flow,
                p1_bar_a=c.p1_bar_a,
                p2_bar_a=c.p2_bar_a,
                temperature_c=c.temperature_c,
                extra_props=c.extra_props,
            )
            for c in req.cases
        ]
        analysis = size_multicase(
            service=service,
            cases=cases,
            base_fluid_data=req.base_fluid_data,
            valve_series=definition.sizes,
            flow_characteristic=req.flow_characteristic,
            pipe_inlet_mm=req.pipe_inlet_diameter_mm,
            pipe_outlet_mm=req.pipe_outlet_diameter_mm,
        )
        return _json_safe(asdict(analysis))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class Flow2DRequest(BaseModel):
    d1_mm: float = 50.0
    d2_mm: float = 50.0
    dn_mm: float = 50.0
    p1_bar: float = 8.0
    p2_bar: float = 5.0
    pv_bar: float = 0.023
    density_kg_m3: float = 998.0
    flow_rate_m3_h: float = 25.0
    opening_pct: float = 70.0
    fl: float = 0.90
    is_choked: bool = False
    fluid_type: str = "liquid"
    viscosity_pa_s: float = 0.001
    sonic_velocity_m_s: float = 1480.0
    nx: int = 140
    ny: int = 50
    valve_type: str = "globe"


@app.post("/api/flow-simulation-2d")
def get_flow_simulation_2d(req: Flow2DRequest) -> dict[str, Any]:
    try:
        sim = simulate_flow_2d(
            d1_mm=req.d1_mm,
            d2_mm=req.d2_mm,
            dn_mm=req.dn_mm,
            p1_bar=req.p1_bar,
            p2_bar=req.p2_bar,
            pv_bar=req.pv_bar,
            density_kg_m3=req.density_kg_m3,
            flow_rate_m3_h=req.flow_rate_m3_h,
            opening_pct=req.opening_pct,
            fl=req.fl,
            is_choked=req.is_choked,
            fluid_type=req.fluid_type,
            viscosity_pa_s=req.viscosity_pa_s,
            sonic_velocity_m_s=req.sonic_velocity_m_s,
            nx=req.nx,
            ny=req.ny,
            valve_type=req.valve_type,
        )
        return _json_safe(asdict(sim))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/", include_in_schema=False)
def _serve_index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/index.html", include_in_schema=False)
def _serve_index_html() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/app.js", include_in_schema=False)
def _serve_app_js() -> FileResponse:
    return FileResponse(WEB_DIR / "app.js", media_type="text/javascript")


@app.get("/flow_2d_viewer.js", include_in_schema=False)
def _serve_flow_2d_viewer_js() -> FileResponse:
    return FileResponse(WEB_DIR / "flow_2d_viewer.js", media_type="text/javascript")


@app.get("/styles.css", include_in_schema=False)
def _serve_styles() -> FileResponse:
    return FileResponse(WEB_DIR / "styles.css", media_type="text/css")


@app.get("/manifest.json", include_in_schema=False)
def _serve_manifest() -> FileResponse:
    return FileResponse(WEB_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def _serve_sw() -> FileResponse:
    return FileResponse(WEB_DIR / "sw.js", media_type="text/javascript")


vendor_dir = WEB_DIR / "vendor"
if vendor_dir.is_dir():
    app.mount("/vendor", StaticFiles(directory=str(vendor_dir)), name="vendor")
