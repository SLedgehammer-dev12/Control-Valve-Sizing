# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Control Valve Sizing Web Application (FastAPI/Three.js).

Build: pyinstaller app_web.spec
Produces a one-dir build on Windows and a .app bundle on macOS (arm64 Apple Silicon).
"""

import os
import re
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs


def _read_app_version() -> str:
    """Read the release version from CVS_VERSION or valve_sizing.__version__."""
    version = os.environ.get("CVS_VERSION", "").strip().lstrip("v")
    if not version:
        with open("valve_sizing.py", encoding="utf-8") as handle:
            match = re.search(r'__version__\s*=\s*"([^"]+)"', handle.read())
        version = match.group(1) if match else "0.0.0"
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"Invalid app version: {version!r}")
    return version


APP_VERSION = _read_app_version()


def _write_version_info(version: str) -> str:
    """Generate the PyInstaller Windows version resource for the release version."""
    major, minor, patch = (int(part) for part in version.split("."))
    path = os.path.join("build", "version_info_web_generated.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'Control Valve Sizing Team'),
          StringStruct('FileDescription', 'Control Valve Sizing Web Application (FastAPI + Three.js)'),
          StringStruct('FileVersion', '{version}.0'),
          StringStruct('InternalName', 'ControlValveSizing_Web'),
          StringStruct('LegalCopyright', 'MIT License'),
          StringStruct('OriginalFilename', 'ControlValveSizing_Web.exe'),
          StringStruct('ProductName', 'Control Valve Sizing Web'),
          StringStruct('ProductVersion', '{version}.0')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def _as_binary_toc(entries):
    """Normalize collect_dynamic_libs output to PyInstaller's BINARY TOC."""
    out = []
    for item in entries:
        if len(item) == 3:
            out.append(item)
        elif len(item) == 2:
            src, dest_dir = item
            out.append((os.path.join(dest_dir, os.path.basename(src)), src, "BINARY"))
    return out


def _collect_delvewheel_libs():
    """Collect delvewheel dependency dirs (e.g. coolprop.libs) next to the bundle."""
    try:
        import CoolProp
    except Exception:
        return []

    site_dir = os.path.dirname(os.path.dirname(CoolProp.__file__))
    out = []
    if not os.path.isdir(site_dir):
        return out
    for entry in os.listdir(site_dir):
        if entry.lower() != "coolprop.libs":
            continue
        lib_dir = os.path.join(site_dir, entry)
        for fname in os.listdir(lib_dir):
            if fname.endswith(".dll"):
                out.append((os.path.join(entry, fname), os.path.join(lib_dir, fname), "BINARY"))
    return out


def _collect_coolprop_binaries():
    """Collect CoolProp native library binaries explicitly."""
    try:
        import CoolProp
    except Exception:
        return []

    cp_dir = os.path.dirname(CoolProp.__file__)
    out = []
    for root, _dirs, files in os.walk(cp_dir):
        for fname in files:
            if fname.endswith((".dll", ".pyd", ".so", ".dylib")):
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, cp_dir)
                dest = os.path.join("CoolProp", rel)
                out.append((dest, src, "BINARY"))
    return out


a = Analysis(
    ["app_web_launcher.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("webapp", "webapp"),
    ],
    hiddenimports=[
        # Web Framework
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "fastapi",
        "fastapi.staticfiles",
        "fastapi.responses",
        "starlette",
        "starlette.routing",
        "starlette.middleware",
        "starlette.staticfiles",
        "pydantic",
        # setuptools
        "setuptools",
        # Core & API
        "api",
        "valve_sizing",
        "fluid_properties",
        "vendor_catalog",
        "config",
        "project_io",
        "reporting",
        "units",
        # Engine modules
        "valve_curve",
        "valve_noise",
        "actuator_sizing",
        "thermal_expansion",
        "two_phase",
        "valve_selection",
        "trim_guidance",
        "datasheet_isa20",
        "joule_thomson",
        "multi_case",
        "packing_emissions",
        "safety_piping",
        # Fluids and thermodynamics
        "fluids",
        "fluids.control_valve",
        "fluids.core",
        "fluids.geometry",
        "fluids.piping",
        "CoolProp",
        "CoolProp.CoolProp",
        "chemicals",
        "chemicals.identifiers",
        "chemicals.critical",
        "chemicals.vapor_pressure",
        "iapws",
        "iapws.IAPWS97",
        "thermo",
        "thermo.chemical",
        "scipy",
        "scipy.optimize",
        "scipy.interpolate",
        "numpy",
        "numpy.core.multiarray",
    ],
    hookspath=["."],
    hooksconfig={},
    runtime_hooks=["rthook_coolprop.py"],
    excludes=[
        "tkinter.test",
        "pydoc",
        "test",
        "turtle",
        "venv",
        "ensurepip",
        "asyncio.test_utils",
    ],
    noarchive=False,
)

a.binaries += _collect_coolprop_binaries()
a.binaries += _collect_delvewheel_libs()
a.binaries += _as_binary_toc(collect_dynamic_libs("fluids"))
a.binaries += _as_binary_toc(collect_dynamic_libs("chemicals"))
a.binaries += _as_binary_toc(collect_dynamic_libs("scipy"))
a.binaries += _as_binary_toc(collect_dynamic_libs("numpy"))

pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="ControlValveSizing_Web",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon="app_icon.icns" if os.path.exists("app_icon.icns") else None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="ControlValveSizing_Web",
    )
    app = BUNDLE(
        coll,
        name="ControlValveSizing_Web.app",
        icon="app_icon.icns" if os.path.exists("app_icon.icns") else None,
        bundle_identifier="com.cvsizing.controlvalvesizing.web",
        info_plist={
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Control Valve Sizing Web Edition",
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="ControlValveSizing_Web",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        version=_write_version_info(APP_VERSION),
        icon="app_icon.ico" if os.path.exists("app_icon.ico") else None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="ControlValveSizing_Web",
    )
