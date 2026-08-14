    # run_all.py
"""Runs paper trading AND backtesting together, sharing one frontend.

Starts three things:
  - backtest_server.py (port 5050) — standalone, no Zerodha session needed
  - ONE frontend dev server (port 5173) — serves both the live pages and
    /backtest at once; Vite's proxy (frontend/vite.config.ts) already
    splits /api/backtest/* to port 5050 and everything else to port
    5000, so a single frontend process covers both
  - the live paper-trading app (run_live.main(), port 5000) — blocks
    this process, same as run_dev.py

Running run_dev.py and run_backtest_ui.py at the same time doesn't work
— each tries to start its OWN frontend dev server and they collide on
port 5173. Use THIS script when you want both live trading and
backtesting up together. Use run_dev.py alone for live-only, or
run_backtest_ui.py alone for backtest-only — those two still work
unchanged for when you only need one.

PAPER TRADING ONLY: same as run_dev.py — every order is simulated via
PaperBroker, nothing is ever sent to the real broker.

    python run_all.py
"""

import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

BACKTEST_PORT = 5050
FRONTEND_DIR = "frontend"

# npm is npm.cmd (a batch file) on Windows — subprocess.Popen needs that
# exact name, "npm" alone fails without shell=True.
NPM_CMD = "npm.cmd" if sys.platform == "win32" else "npm"
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """proc.terminate() alone only signals the top PID — npm.cmd spawns
    node.exe (Vite) as a CHILD process on Windows, so terminate() would
    leave it running as an orphan (see run_backtest_ui.py, where this
    was caught for real during testing). taskkill /T kills the tree."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()


def _wait_for_http(url: str, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


def _relay_and_watch_for_port(proc: subprocess.Popen, found_port: list) -> None:
    """Prints the frontend's own output live while watching for Vite's
    "Local: http://localhost:PORT/" banner — Vite picks a different port
    than 5173 if that one's taken, so it isn't knowable in advance. ANSI
    color codes land BETWEEN the colon and the port digits in that line,
    which breaks a naive regex unless stripped first (caught for real
    while building run_backtest_ui.py)."""
    for line in proc.stdout:
        print(f"[frontend] {line}", end="", flush=True)
        clean = _ANSI_ESCAPE.sub("", line)
        match = re.search(r"http://localhost:(\d+)/", clean)
        if match and not found_port:
            found_port.append(int(match.group(1)))


def main() -> None:
    print("=" * 60)
    print(" QuantPulse — PAPER TRADING + BACKTESTING")
    print(" Both running together, one shared frontend.")
    print(" Live: real Zerodha data, simulated orders only.")
    print("=" * 60, flush=True)

    print(f"\nStarting backtest API on port {BACKTEST_PORT} ...", flush=True)
    backtest = subprocess.Popen([sys.executable, "run_backtest_server.py"])

    print("Starting frontend dev server...", flush=True)
    frontend = subprocess.Popen(
        [NPM_CMD, "run", "dev"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    found_port: list = []
    threading.Thread(target=_relay_and_watch_for_port, args=(frontend, found_port), daemon=True).start()

    if not _wait_for_http(f"http://127.0.0.1:{BACKTEST_PORT}/api/backtest/watchlist"):
        print("Backtest API didn't come up in time — check the output above.", file=sys.stderr, flush=True)

    deadline = time.time() + 30
    while not found_port and time.time() < deadline:
        time.sleep(0.5)

    if found_port:
        print(f"\nFrontend: http://localhost:{found_port[0]}/  (Backtest tab lives at /backtest)\n", flush=True)
    else:
        print("Frontend didn't announce its port in time — open it manually once it's ready.", file=sys.stderr, flush=True)

    print("Starting live paper-trading app on port 5000 (this may trigger a Zerodha login if needed)...\n", flush=True)

    try:
        import run_live
        run_live.main()  # blocks until Ctrl+C
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        backtest.terminate()
        _kill_process_tree(frontend)
        try:
            backtest.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backtest.kill()


if __name__ == "__main__":
    main()
