# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Control Valve Sizing desktop app.

Build: pyinstaller app_desktop.spec
Produces a one-dir build (no UPX compression) on Windows and a .app
bundle on macOS (arm64). UPX is disabled and one-dir mode is used to
avoid antivirus / antimalware false positives on unsigned builds.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs


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
        "valve_noise",
        "actuator_sizing",
        "thermal_expansion",
        "two_phase",
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
    hookspath=[],
    hooksconfig={},
    excludes=[
        "tkinter.test",
        "unittest",
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
a.binaries += _as_binary_toc(collect_dynamic_libs("CoolProp"))
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
            "CFBundleShortVersionString": "3.2.0",
            "CFBundleVersion": "3.2.0",
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
        version="version_info.txt",
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