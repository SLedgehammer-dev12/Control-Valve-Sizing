"""PyInstaller runtime hook for CoolProp on Windows.

CoolProp's native DLL (CoolProp.dll) must be findable by Windows when the
Cython extension (.pyd) is loaded. PyInstaller extracts extension modules to
_MEIPASS/<package>/ but the sibling DLL may not be on the DLL search path.
This hook adds the bundled CoolProp directory and delvewheel ``*.libs``
directories to both os.environ['PATH'] and os.add_dll_directory() so
LoadLibrary(CoolProp.dll) succeeds.
"""
import contextlib
import glob
import os
import sys

if sys.platform == "win32":
    meipass = getattr(sys, "_MEIPASS", "")
    # CoolProp 8.x keeps its MSVC runtime in _MEIPASS/coolprop.libs (delvewheel).
    dll_dirs = [os.path.join(meipass, "CoolProp"), *glob.glob(os.path.join(meipass, "*.libs"))]
    for dll_dir in dll_dirs:
        if os.path.isdir(dll_dir):
            os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
            with contextlib.suppress(Exception):
                os.add_dll_directory(dll_dir)
