# live/deployment_runner.py
"""Runs every deployment's ExecutionManager.evaluate() on a shared cadence.

Mirrors the market-hours window backend/filter_engine.py's screener loop
already used when it drove execution directly (09:20-11:30) — evaluating
outside that window would act on stale/no data. Each deployment's
evaluate() is isolated in its own try/except: a bug in one strategy
shouldn't stop other deployments from trading.
"""

import datetime as dt
import time


def run_deployments(deployment_runtimes):
    """deployment_runtimes: List[core.container.DeploymentRuntime]"""

    print(f"🚀 Running {len(deployment_runtimes)} deployment(s)...")

    while True:
        current_time = dt.datetime.now().time()

        if dt.time(9, 20) <= current_time <= dt.time(11, 30):
            for runtime in deployment_runtimes:
                try:
                    runtime.execution_manager.evaluate()
                except Exception as e:
                    print(
                        f"⚠️ Deployment {runtime.deployment.id} "
                        f"({runtime.deployment.strategy_name}) error:",
                        e,
                    )

        time.sleep(3)
