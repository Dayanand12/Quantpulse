import sys
import os
import time
import datetime as dt
from pathlib import Path
from threading import Lock

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(ROOT_DIR, ".."))
sys.path.append(PROJECT_ROOT)

from core.domain.strategy_conditions import StagedConditionSet
from services.state_store import stage_results

stage_lock = Lock()

# The actual stage1/2/3 thresholds/conditions live in strategies/
# orb_reversal.json, not here — see core/domain/strategy_conditions.py.
# Edit that JSON to tune this funnel (e.g. the stage3 distance-to-OR-low
# band); nothing in this file needs to change for a threshold tweak.
# Loaded once at import time (this module, orb_reversal.py's screen(),
# and the Screener's own live loop below all share this one instance) —
# same restart-to-apply convention every other strategy file already has.
_CONDITIONS_PATH = Path(PROJECT_ROOT) / "strategies" / "orb_reversal.json"
_conditions = StagedConditionSet.from_file(_CONDITIONS_PATH)

# ConditionSet.evaluate() takes a symbol only to key per-symbol state for
# crossing conditions (crossed_above/crossed_below) — stage1/2/3 below use
# none, so this is inert; a constant placeholder keeps stage1_filter/
# stage2_filter/stage3_filter's existing (data) -> bool signatures exactly
# as every caller (orb_reversal.py, start_engine() below) already expects.
_NO_CROSSING_STATE_NEEDED = "_"


def stage1_filter(data):
    return _conditions.evaluate("stage1", _NO_CROSSING_STATE_NEEDED, data)


def stage2_filter(data):
    return _conditions.evaluate("stage2", _NO_CROSSING_STATE_NEEDED, data)


def stage3_filter(data):
    return _conditions.evaluate("stage3", _NO_CROSSING_STATE_NEEDED, data)


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