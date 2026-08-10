import datetime as dt
import json

import pytest

from core.domain.models import StrategyConfig
from runners.backtesting.batch_runner import (
    PanelSpec,
    merge_condition_overrides,
    run_batch_backtests,
)
from strategies.test_json_threshold import TestJsonThresholdStrategy


def _bar(day, index, open_, high, low, close, volume=1000.0):
    return {
        "date": dt.datetime.combine(day, dt.time(9, 15)) + dt.timedelta(minutes=index),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


def _write_sample_csv(path):
    day = dt.date(2026, 1, 5)
    # snapshot_builder.py needs the day's bars from market open (09:15) to
    # form things like the opening range/VWAP — same reasoning as
    # test_parameter_sweep.py's _FIRST_TRADEABLE_INDEX=24 filler bars, and
    # StrategyConfig's default start_time="09:20" needs bars past that gate.
    rows = [_bar(day, i, 100.0, 100.0, 100.0, 100.0) for i in range(24)]
    rows.append(_bar(day, 24, 99.0, 99.0, 99.0, 99.0))
    # entry bar for a threshold between the 100.0 warmup flat price and
    # this bar's 101.0 close (e.g. 100.5) — low enough to fire here,
    # high enough not to have already fired during warmup
    rows.append(_bar(day, 25, 101.0, 101.0, 101.0, 101.0))
    # high enough to blow through the default 2.0% target (103.02) so any
    # panel that entered on bar 25 closes here, regardless of which
    # threshold it ran with
    rows.append(_bar(day, 26, 101.0, 103.5, 100.5, 103.0))
    lines = ["date,open,high,low,close,volume"]
    for r in rows:
        lines.append(
            f"{r['date'].isoformat()}+05:30,{r['open']},{r['high']},{r['low']},{r['close']},{r['volume']}"
        )
    path.write_text("\n".join(lines))


def test_merge_condition_overrides_updates_the_parameters_block():
    merged, merged_json = merge_condition_overrides("test_json_threshold", {"threshold": 150.0})

    assert merged["parameters"]["threshold"] == 150.0
    assert merged["conditions"] == json.loads(merged_json)["conditions"]


def test_merge_condition_overrides_rejects_unknown_parameter():
    with pytest.raises(ValueError, match="typo_threshold"):
        merge_condition_overrides("test_json_threshold", {"typo_threshold": 1.0})


def test_merge_condition_overrides_rejects_strategy_without_conditions_json():
    with pytest.raises(ValueError, match="no conditions.json"):
        merge_condition_overrides("test_always_short", {"threshold": 1.0})


def test_run_batch_backtests_runs_every_panel_independently(tmp_path):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)

    panels = [
        PanelSpec(label="fires", overrides={"threshold": 100.5}),
        PanelSpec(label="never fires", overrides={"threshold": 500.0}),
    ]

    panel_results, symbols_used, symbols_missing_data = run_batch_backtests(
        TestJsonThresholdStrategy, "test_json_threshold", panels,
        symbols=[("TEST", str(csv_path))], config=StrategyConfig(),
    )

    assert symbols_used == ["TEST"]
    assert symbols_missing_data == []
    assert len(panel_results) == 2

    fires, never_fires = panel_results
    assert fires.label == "fires"
    assert len(fires.trades) == 1
    assert never_fires.label == "never fires"
    assert len(never_fires.trades) == 0

    # each panel's stored JSON reflects its own override, not the other's
    assert json.loads(fires.strategy_params_json)["parameters"]["threshold"] == 100.5
    assert json.loads(never_fires.strategy_params_json)["parameters"]["threshold"] == 500.0


def test_run_batch_backtests_skips_symbols_with_no_historical_data(tmp_path):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    missing_csv_path = tmp_path / "MISSING_historical.csv"

    panels = [PanelSpec(label="fires", overrides={"threshold": 100.5})]
    panel_results, symbols_used, symbols_missing_data = run_batch_backtests(
        TestJsonThresholdStrategy, "test_json_threshold", panels,
        symbols=[("TEST", str(csv_path)), ("MISSING", str(missing_csv_path))],
        config=StrategyConfig(),
    )

    assert symbols_used == ["TEST"]
    assert symbols_missing_data == ["MISSING"]
    assert len(panel_results[0].trades) == 1


def test_run_batch_backtests_aggregates_multiple_symbols_per_panel(tmp_path):
    csv_a = tmp_path / "A_historical.csv"
    csv_b = tmp_path / "B_historical.csv"
    _write_sample_csv(csv_a)
    _write_sample_csv(csv_b)

    panels = [PanelSpec(label="fires", overrides={"threshold": 100.5})]
    panel_results, symbols_used, _ = run_batch_backtests(
        TestJsonThresholdStrategy, "test_json_threshold", panels,
        symbols=[("A", str(csv_a)), ("B", str(csv_b))], config=StrategyConfig(),
    )

    assert set(symbols_used) == {"A", "B"}
    assert len(panel_results[0].trades) == 2
