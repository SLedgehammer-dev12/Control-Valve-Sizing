"""Standalone desktop launcher for Control Valve Sizing Web Application (FastAPI + Three.js).

Starts the local FastAPI backend server, auto-detects an available port,
and opens the user's default web browser. Provides an optional mini status
window with quick open and exit controls.
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

logger = logging.getLogger("cvs_web_launcher")


def _sanitize_standard_streams() -> None:
    """Ensure standard I/O streams are not None in windowed (GUI) executables.

    In Windows and macOS frozen applications built with console=False (pythonw subsystem),
    sys.stdout, sys.stderr, and sys.stdin are None by default. Libraries that inspect
    or configure logging (e.g. uvicorn, colorama, rich, click) fail with
    AttributeError: 'NoneType' object has no attribute 'isatty' or 'write'.
    """
    if sys.stdout is None:
        try:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        except Exception:
            import io

            sys.stdout = io.StringIO()

    if sys.stderr is None:
        try:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        except Exception:
            import io

            sys.stderr = io.StringIO()

    if sys.stdin is None:
        try:
            sys.stdin = open(os.devnull, encoding="utf-8")  # noqa: SIM115
        except Exception:
            import io

            sys.stdin = io.StringIO()


_sanitize_standard_streams()


def _find_free_port(start_port: int = 8501, max_tries: int = 50) -> int:
    """Find the first available TCP port on localhost starting from start_port."""
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port


def _wait_and_open_browser(url: str, ready_event: threading.Event, timeout: float = 15.0) -> None:
    """Poll the health endpoint until the server is ready, then open the default browser."""
    health_url = f"{url}/api/health"
    start_time = time.time()
    while time.time() - start_time < timeout:
        if ready_event.is_set():
            return
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as resp:
                if resp.status == 200:
                    webbrowser.open(url)
                    return
        except Exception:
            time.sleep(0.3)
    webbrowser.open(url)


def _run_mini_gui(url: str, stop_server_fn) -> None:
    """Optional minimal Tkinter status window for easy server management."""
    try:
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.title("Control Valve Sizing - Web Sunucusu")
        root.geometry("420x220")
        root.resizable(False, False)

        for icon_name in ("app_icon.ico", "app_icon.png"):
            if os.path.exists(icon_name):
                try:
                    root.iconbitmap(icon_name)
                    break
                except Exception:
                    pass

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)

        title_lbl = ttk.Label(
            frame,
            text="Control Valve Sizing (Web Versiyonu)",
            font=("Helvetica", 12, "bold"),
        )
        title_lbl.pack(pady=(0, 8))

        status_lbl = ttk.Label(
            frame,
            text="Yerel web sunucusu aktif ve çalışıyor.\nTarayıcınız otomatik olarak açıldı.",
            justify="center",
        )
        status_lbl.pack(pady=4)

        url_entry = ttk.Entry(frame, justify="center")
        url_entry.insert(0, url)
        url_entry.configure(state="readonly")
        url_entry.pack(fill="x", pady=8)

        btn_box = ttk.Frame(frame)
        btn_box.pack(pady=8)

        def on_open():
            webbrowser.open(url)

        def on_quit():
            stop_server_fn()
            root.destroy()

        open_btn = ttk.Button(btn_box, text="Tarayıcıda Aç", command=on_open)
        open_btn.pack(side="left", padx=5)

        quit_btn = ttk.Button(btn_box, text="Sunucuyu Kapat ve Çık", command=on_quit)
        quit_btn.pack(side="left", padx=5)

        root.protocol("WM_DELETE_WINDOW", on_quit)
        root.mainloop()
    except Exception as exc:
        logger.info("GUI initialization skipped (%s); running in console mode.", exc)


def _self_test() -> int:
    """Headless self-test for CI verification of frozen executable."""
    try:
        _sanitize_standard_streams()

        import uvicorn

        from api import app
        from fluid_properties import get_pure_fluid_state
        from valve_sizing import LiquidSizingInput, size_liquid_valve

        assert app is not None
        assert uvicorn is not None

        is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        cfg = uvicorn.Config(
            app=app,
            host="127.0.0.1",
            port=8501,
            log_level="info",
            access_log=False,
            use_colors=is_tty,
        )
        assert cfg is not None

        state = get_pure_fluid_state("Water", 5.0, 25.0)
        res = size_liquid_valve(
            LiquidSizingInput(
                flow_m3h=10.0,
                inlet_pressure_bar_a=5.0,
                outlet_pressure_bar_a=3.0,
                density_kg_m3=state["density_kg_m3"],
                vapor_pressure_bar_a=state["vapor_pressure_bar_a"],
                critical_pressure_bar_a=state["critical_pressure_bar_a"],
                viscosity_pa_s=state["viscosity_pa_s"],
                fl=0.9,
            )
        )
        assert res.required_cv > 0
        if sys.stdout is not None:
            sys.stdout.write("Control Valve Sizing Web self-test passed.\n")
            sys.stdout.flush()
        return 0
    except Exception as exc:
        if sys.stderr is not None:
            sys.stderr.write(f"Self-test failed: {exc}\n")
            sys.stderr.flush()
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Control Valve Sizing Web Application Launcher")
    parser.add_argument("--port", type=int, default=8501, help="Preferred port (default: 8501)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    parser.add_argument("--no-gui", action="store_true", help="Do not show status GUI window")
    parser.add_argument("--self-test", action="store_true", help="Run self-test and exit 0")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    import uvicorn

    from api import app

    port = _find_free_port(args.port)
    url = f"http://127.0.0.1:{port}"
    logger.info("Starting Control Valve Sizing Web Server at %s", url)
    print("\n========================================================")
    print("  Control Valve Sizing (Web Edition)")
    print(f"  Sunucu Adresi: {url}")
    print("  Durdurmak için Ctrl+C'ye basın veya pencereyi kapatın.")
    print("========================================================\n")

    is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
        use_colors=is_tty,
    )
    server = uvicorn.Server(config)

    shutdown_event = threading.Event()

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    if not args.no_browser:
        browser_thread = threading.Thread(
            target=_wait_and_open_browser,
            args=(url, shutdown_event),
            daemon=True,
        )
        browser_thread.start()

    def stop_server():
        shutdown_event.set()
        server.should_exit = True

    if not args.no_gui and not os.environ.get("CI"):
        _run_mini_gui(url, stop_server)
    else:
        try:
            while server_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            stop_server()

    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    sys.exit(main())
