# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Control Valve Sizing desktop app.

Build: pyinstaller app_desktop.spec
Produces a one-dir build (no UPX compression) on Windows and a .app
bundle on macOS (arm64). UPX is disabled and one-dir mode is used to
avoid antivirus / antimalware false positives on unsigned builds.
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
    path = os.path.join("build", "version_info_generated.txt")
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
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'Control Valve Sizing'),
          StringStruct(u'FileDescription', u'Control Valve Sizing (IEC 60534 / ISA)'),
          StringStruct(u'FileVersion', u'{version}'),
          StringStruct(u'InternalName', u'ControlValveSizing'),
          StringStruct(u'LegalCopyright', u'Control Valve Sizing'),
          StringStruct(u'OriginalFilename', u'ControlValveSizing.exe'),
          StringStruct(u'ProductName', u'Control Valve Sizing'),
          StringStruct(u'ProductVersion', u'{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def _as_binary_toc(items):
    """Normalize (source, dest_dir) or (dest, source, type) entries to binary TOC."""
    out = []
    for item in items:
        if len(item) == 3:
            out.append(item)
        else:
            src, dest_dir = item
            out.append((os.path.join(dest_dir, os.path.basename(src)), src, "BINARY"))
    return out


def _collect_delvewheel_libs():
    """Collect delvewheel dependency dirs (e.g. coolprop.libs) next to the bundle.

    CoolProp 8.x Windows wheels ship MSVC runtime DLLs in a sibling
    ``coolprop.libs`` directory, not inside the ``CoolProp`` package. PyInstaller
    does not collect it automatically, so CoolProp.pyd fails to load at runtime.
    """
    import CoolProp

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
    """Collect CoolProp's native library binaries explicitly.

    PyInstaller's collect_dynamic_libs("CoolProp") often misses CoolProp.dll
    on Windows, causing "DLL load failed: The specified module could not be
    found" at runtime. We scan the CoolProp package directory (and its
    subdirectories, e.g. redist/ for Intel MKL DLLs) directly and include
    .dll/.pyd/.so/.dylib files next to the CoolProp package in the bundle so
    the .pyd can load its sibling DLL at runtime.
    """
    import CoolProp

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
    ["app_desktop.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # setuptools (needed by PyInstaller hooks)
        "setuptools",
        # Core engine
        "valve_sizing",
        "fluid_properties",
        "vendor_catalog",
        "config",
        "project_io",
        "reporting",
        "units",
        # Phase 2 + 3 modules
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
        # fluids library internals
        "fluids",
        "fluids.control_valve",
        "fluids.core",
        "fluids.geometry",
        "fluids.piping",
        # CoolProp
        "CoolProp",
        "CoolProp.CoolProp",
        # chemicals
        "chemicals",
        "chemicals.identifiers",
        "chemicals.critical",
        "chemicals.vapor_pressure",
        # iapws
        "iapws",
        "iapws.IAPWS97",
        # thermo
        "thermo",
        "thermo.chemical",
        "thermo.mixture",
        # pint
        "pint",
        "pint.quantity",
        "pint.unit",
        # Scipy (used by thermo / chemicals)
        "scipy",
        "scipy.optimize",
        "scipy.interpolate",
        # NumPy (dependency)
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

# Collect native dynamic libraries shipped by the numeric stack
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
        name="ControlValveSizing",
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
        icon="app_icon.icns",
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="ControlValveSizing",
    )
    app = BUNDLE(
        coll,
        name="ControlValveSizing.app",
        icon="app_icon.icns",
        bundle_identifier="com.cvsizing.controlvalvesizing",
        info_plist={
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Control Valve Sizing",
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="ControlValveSizing",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        version=_write_version_info(APP_VERSION),
        icon="app_icon.ico",
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="ControlValveSizing",
    )