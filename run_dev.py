#run_dev.py
"""Single-command dev launcher.

Starts the Vite frontend dev server (frontend/, npm run dev) as a
background subprocess, then runs the backend (run_live.main) in this
process. Ctrl+C stops both.

Usage:
    python run_dev.py
"""
import subprocess
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).parent / "frontend"


def main():
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
