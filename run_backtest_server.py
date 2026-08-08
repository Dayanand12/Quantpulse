# run_backtest_server.py
"""Starts the standalone backtest API (backtest_server.py) — no Zerodha
login required, unlike run_live.py. Default port 5050, matching
frontend/vite.config.ts's dev proxy for /api/backtest/*.

    python run_backtest_server.py
    python run_backtest_server.py --port 5051
"""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run("backtest_server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
