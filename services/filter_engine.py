import sys
import os
import time
import datetime as dt
from threading import Lock

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(ROOT_DIR, ".."))
sys.path.append(PROJECT_ROOT)

from services.state_store import stage_results

stage_lock = Lock()


def safe_get(data, key):
    return data.get(key)


def stage1_filter(data):
    if None in (
        safe_get(data, "ltp"),
        safe_get(data, "vwap"),
        safe_get(data, "ema9"),
        safe_get(data, "ema21"),
        safe_get(data, "rsi")
    ):
        return False

    return (
        data["ltp"] < data["vwap"] and
        data["ema9"] < data["ema21"] and
        data["rsi"] < 48
    )


def stage2_filter(data):
    if None in (
        safe_get(data, "volume_ratio"),
        safe_get(data, "atr_pct"),
        safe_get(data, "adx")
    ):
        return False

    return (
        data["volume_ratio"] >= 1.7 and
        data["atr_pct"] >= 0.8 and
        data["adx"] >= 22
    )


def stage3_filter(data):
    if data.get("distance_to_or_low") is None:
        return False

    # Backtested across the full watchlist, 2024-10 to 2026-08 (22 months,
    # 5-minute bars): the original 0-0.2% band assumed price would still
    # be sitting just above the opening-range low when stage1/stage2's
    # momentum conditions confirm — in practice momentum only confirms
    # AFTER price has already broken through that zone (median ~1-3%
    # through it, either side). The 0-0.2% band produced 3 trades total
    # (net LOSS after charges, -₹111); widening to ±2% produced 28 trades,
    # 71% win rate, profit factor 4.96, +₹10,236 net. See
    # runners/backtesting/ for how to re-validate this if you change it.
    return -2.0 <= data["distance_to_or_low"] <= 2.0


def reset_stages():
    with stage_lock:
        stage_results["ORB"]["stage1"]["stocks"] = []
        stage_results["ORB"]["stage2"]["stocks"] = []
        stage_results["ORB"]["stage3"]["stocks"] = []


def start_engine(live_engine):

    print("🚀 Live ORB Screener Running...")

    while True:

        try:
            snapshot = live_engine.get_snapshot()
            now = dt.datetime.now()
            current_time = now.time()

            # Reset before market open
            if current_time < dt.time(9, 16):
                reset_stages()
                time.sleep(5)
                continue

            # Active window
            if not (dt.time(9, 20) <= current_time <= dt.time(11, 30)):
                time.sleep(3)
                continue

            s1, s2, s3_ranked = [], [], []

            for symbol, data in snapshot.items():

                if stage1_filter(data):
                    s1.append(symbol)

                    if stage2_filter(data):
                        s2.append(symbol)

                        if stage3_filter(data):
                            s3_ranked.append(
                                (symbol, data["volume_ratio"])
                            )

            s3_ranked = sorted(
                s3_ranked,
                key=lambda x: x[1],
                reverse=True
            )[:5]

            s3 = [x[0] for x in s3_ranked]

            with stage_lock:
                stage_results["ORB"]["stage1"]["stocks"] = s1
                stage_results["ORB"]["stage2"]["stocks"] = s2
                stage_results["ORB"]["stage3"]["stocks"] = s3

            time.sleep(3)

        except Exception as e:
            print("⚠️ Screener Error:", e)
            time.sleep(3)