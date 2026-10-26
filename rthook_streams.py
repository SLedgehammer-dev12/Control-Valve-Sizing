"""PyInstaller runtime hook to sanitize standard streams in windowed (GUI) mode.

In Windows and macOS frozen applications built with console=False, standard
streams (sys.stdout, sys.stderr, sys.stdin) can be None. Libraries like uvicorn
and logging formatters crash with AttributeError: 'NoneType' object has no attribute 'isatty'.
This hook ensures all standard streams are valid stream objects before any application
or dependency module is imported.
"""

from __future__ import annotations

import io
import os
import sys

if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    except Exception:
        sys.stdout = io.StringIO()

if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    except Exception:
        sys.stderr = io.StringIO()

if sys.stdin is None:
    try:
        sys.stdin = open(os.devnull, encoding="utf-8")  # noqa: SIM115
    except Exception:
        sys.stdin = io.StringIO()
