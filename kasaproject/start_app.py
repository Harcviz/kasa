#!/usr/bin/env python
"""
Helper script to launch the Django dev server and open the app in the browser.
Run with: python start_app.py
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8000
WAIT_SECONDS = 20


def wait_for_port(host: str, port: int, timeout: int = WAIT_SECONDS) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                time.sleep(0.5)
    return False


def resolve_python(project_root: Path) -> Path:
    venv_python = project_root / "venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


def main() -> None:
    project_root = Path(__file__).resolve().parent
    python_exe = resolve_python(project_root)
    manage_py = project_root / "manage.py"

    if not manage_py.exists():
        raise SystemExit("manage.py not found; run from the project root.")

    cmd = [str(python_exe), str(manage_py), "runserver", f"{HOST}:{PORT}"]
    print(f"Starting server: {' '.join(cmd)}")

    try:
        server_proc = subprocess.Popen(cmd, cwd=project_root)
    except FileNotFoundError as exc:
        raise SystemExit(f"Python executable not found: {python_exe}") from exc

    try:
        if wait_for_port(HOST, PORT):
            url = f"http://{HOST}:{PORT}/"
            print(f"Opening {url}")
            webbrowser.open(url)
        else:
            print(f"Server did not start listening on {HOST}:{PORT} within {WAIT_SECONDS}s.")
        server_proc.wait()
    except KeyboardInterrupt:
        print("Stopping server...")
        server_proc.terminate()
    finally:
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()


if __name__ == "__main__":
    main()
