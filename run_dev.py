#run_dev.py
"""Single-command dev launcher.

Starts the Vite frontend dev server (frontend/, npm run dev) as a
background subprocess, then runs the backend (run_live.main) in this
process. Ctrl+C stops both.

PAPER TRADING ONLY: the backend wires every deployment to PaperBroker
(runners/paper_trading/paper_broker.py) via PaperOrderRepository/
PaperPortfolioService (see core/container.py::build_container) — real
Zerodha market data drives the signals, but every order is simulated
in-memory and no order is ever sent to the broker. There is no live/real
order-placement path anywhere in this codebase.

Usage:
    python run_dev.py
"""
import subprocess
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).parent / "frontend"


def main():
    print("=" * 60)
    print(" QuantPulse — PAPER TRADING MODE")
    print(" Live Zerodha market data, simulated order execution only.")
    print("=" * 60)

    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend = subprocess.Popen([npm_cmd, "run", "dev"], cwd=FRONTEND_DIR)

    try:
        import run_live
        run_live.main()
    except KeyboardInterrupt:
        pass
    finally:
        if sys.platform == "win32":
            # npm.cmd is a cmd.exe wrapper around node.exe (Vite) — terminate()
            # only kills the wrapper and orphans the actual dev server, so kill
            # the whole process tree by PID instead.
            subprocess.run(
                ["taskkill", "/PID", str(frontend.pid), "/T", "/F"],
                capture_output=True,
            )
        else:
            frontend.terminate()
        try:
            frontend.wait(timeout=10)
        except subprocess.TimeoutExpired:
            frontend.kill()


if __name__ == "__main__":
    main()
