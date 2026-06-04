# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Control Valve Sizing desktop app.

Build: pyinstaller app_desktop.spec
"""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

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
        "email",
        "http",
        "urllib",
        "pydoc",
        "test",
        "turtle",
        "venv",
        "ensurepip",
        "asyncio.test_utils",
    ],
    noarchive=False,
)

# Collect CoolProp native .pyd files
a.binaries += collect_dynamic_libs("CoolProp")
a.binaries += collect_dynamic_libs("fluids")
a.binaries += collect_dynamic_libs("chemicals")
a.binaries += collect_dynamic_libs("scipy")
a.binaries += collect_dynamic_libs("numpy")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ControlValveSizing",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="app_icon.ico",
)
