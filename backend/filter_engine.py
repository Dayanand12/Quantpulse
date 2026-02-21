import sys
import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))  # backend/
PROJECT_ROOT = os.path.abspath(os.path.join(ROOT_DIR, ".."))  # QuantPulse/

sys.path.append(PROJECT_ROOT)
import time
from backend.utils.yaml_loader import load_strategy_yaml
from backend.stage_manager import run_stage
from backend.state_store import stage_results

def start_engine():
    print("Filter Engine Running...")

    while True:
        for strategy in ["ORB", "VWAP", "BREAKOUT"]:
            config = load_strategy_yaml(strategy)

            # Stage 1
            s1 = run_stage(config["stocks"], config["stages"]["stage1"])
            stage_results[strategy]["stage1"] = {
                "status": "running",
                "stocks": s1
            }

            # Stage 2
            s2 = run_stage(s1, config["stages"]["stage2"])
            stage_results[strategy]["stage2"] = {
                "status": "running",
                "stocks": s2
            }

            # Stage 3
            s3 = run_stage(s2, config["stages"]["stage3"])
            stage_results[strategy]["stage3"] = {
                "status": "complete",
                "stocks": s3
            }

        time.sleep(3)

if __name__ == "__main__":
    start_engine()