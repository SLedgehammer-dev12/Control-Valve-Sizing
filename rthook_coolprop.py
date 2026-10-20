"""PyInstaller runtime hook for CoolProp on Windows.

CoolProp's native DLL (CoolProp.dll) must be findable by Windows when the
Cython extension (.pyd) is loaded. PyInstaller extracts extension modules to
_MEIPASS/<package>/ but the sibling DLL may not be on the DLL search path.
This hook adds the bundled CoolProp directory to both os.environ['PATH']
and os.add_dll_directory() so LoadLibrary(CoolProp.dll) succeeds.
"""
import contextlib
import os
import sys

if sys.platform == "win32":
    coolprop_dir = os.path.join(sys._MEIPASS, "CoolProp")
    if os.path.isdir(coolprop_dir):
        # Add to PATH for LoadLibrary
        os.environ["PATH"] = coolprop_dir + os.pathsep + os.environ.get("PATH", "")
        # Add to DLL search directory (Python 3.8+)
        with contextlib.suppress(Exception):
            os.add_dll_directory(coolprop_dir)
