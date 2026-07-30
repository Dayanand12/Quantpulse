# live/deployment_runner.py
"""Runs every deployment's ExecutionManager.evaluate() on a shared cadence,
each gated by its own configured active window (deployment.config.
start_time/end_time — see core/domain/models.py::StrategyConfig) instead
of one window shared by every deployment. Evaluating outside a
deployment's own window would act on stale/no data for entries, and would
also stop managing its open positions' SL/target/trailing — same
trade-off as before, just scoped per deployment now. Each deployment's
evaluate() is isolated in its own try/except: a bug in one strategy
shouldn't stop other deployments from trading.
"""

import datetime as dt
import time


def _parse_hhmm(value: str) -> dt.time:
    hour, minute = value.split(":")
    return dt.time(int(hour), int(minute))


def _is_within_window(config, current_time: dt.time) -> bool:
    """config: core.domain.models.StrategyConfig"""
    start = _parse_hhmm(config.start_time)
    end = _parse_hhmm(config.end_time)
    return start <= current_time <= end


def run_deployments(deployment_runtimes):
    """deployment_runtimes: List[core.container.DeploymentRuntime]"""

    print(f"🚀 Running {len(deployment_runtimes)} deployment(s)...")

    while True:
        current_time = dt.datetime.now().time()

        for runtime in deployment_runtimes:
            if not _is_within_window(runtime.deployment.config, current_time):
                continue

            try:
                runtime.execution_manager.evaluate()
            except Exception as e:
                print(
                    f"⚠️ Deployment {runtime.deployment.id} "
                    f"({runtime.deployment.strategy_name}) error:",
                    e,
                )

        time.sleep(3)
