# run_backtest_ui.py
"""One command instead of two terminals: starts the backtest API
(backtest_server.py) and the frontend dev server together, waits for
both to actually be reachable, then opens the browser straight to the
Backtest page. Ctrl+C stops both.

    python run_backtest_ui.py
"""

import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """proc.terminate() alone only signals the top PID — on Windows,
    `npm.cmd` is a batch-file wrapper that spawns node.exe as a CHILD
    process, so terminate() leaves the actual Vite/node.exe server running
    as an orphan (this happened for real while building this script —
    stray node.exe processes kept holding ports 5173/5174 across runs).
    taskkill /T kills the whole tree; there's no single-call equivalent
    via the subprocess module on Windows."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()

BACKEND_PORT = 5050
FRONTEND_DIR = "frontend"

# subprocess.Popen(["npm", ...]) fails on Windows without shell=True —
# npm is npm.cmd (a batch file), not a directly-executable binary.
NPM_CMD = "npm.cmd" if sys.platform == "win32" else "npm"


def _wait_for_http(url: str, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _relay_and_watch_for_port(proc: subprocess.Popen, found_port: list) -> None:
    """Prints the frontend dev server's own output live (so you still see
    its logs/errors) while watching for Vite's "Local: http://localhost:PORT/"
    line — Vite picks a different port than 5173 if that one's already in
    use (see the port-collision we hit while building this), so the actual
    port isn't knowable in advance. Vite colors that line, and the ANSI
    codes land BETWEEN the colon and the port digits and between the
    digits and the trailing slash (e.g. "...localhost:\x1b[1m5174\x1b[22m/"),
    which silently breaks a naive regex against the raw line — strip
    escape codes first, on the CLEANED copy only (the raw line still gets
    printed so colors show in a real terminal)."""
    for line in proc.stdout:
        print(f"[frontend] {line}", end="", flush=True)
        clean = _ANSI_ESCAPE.sub("", line)
        match = re.search(r"http://localhost:(\d+)/", clean)
        if match and not found_port:
            found_port.append(int(match.group(1)))


def main() -> None:
    print("Starting backtest API on port", BACKEND_PORT, "...", flush=True)
    backend = subprocess.Popen([sys.executable, "run_backtest_server.py"])

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
    relay_thread = threading.Thread(target=_relay_and_watch_for_port, args=(frontend, found_port), daemon=True)
    relay_thread.start()

    try:
        if not _wait_for_http(f"http://127.0.0.1:{BACKEND_PORT}/api/backtest/watchlist"):
            print("Backend didn't come up in time — check the output above.", file=sys.stderr)

        # Wait for Vite to announce its port (printed in its own startup
        # banner), not a fixed guess.
        deadline = time.time() + 30
        while not found_port and time.time() < deadline:
            time.sleep(0.5)

        if found_port:
            url = f"http://localhost:{found_port[0]}/backtest"
            print(f"\nOpening {url}\n", flush=True)
            webbrowser.open(url)
        else:
            print("Frontend didn't announce its port in time — open it manually once it's ready.", file=sys.stderr, flush=True)

        print("Both running. Ctrl+C to stop both.\n", flush=True)
        backend.wait()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        backend.terminate()
        _kill_process_tree(frontend)
        try:
            backend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()


if __name__ == "__main__":
    main()
