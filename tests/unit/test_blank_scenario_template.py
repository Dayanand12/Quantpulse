from io import BytesIO

import pandas as pd

from runners.backtesting.batch_job_runner import DEFAULT_SCENARIO_SETTINGS
from runners.backtesting.report import build_blank_scenario_template


def test_blank_template_includes_shared_defaults_and_parameter_defaults():
    content = build_blank_scenario_template({"adx_threshold": 25.0, "volume_ratio_min": 1.5})

    df = pd.read_excel(BytesIO(content), sheet_name="Parameter Comparison")

    assert len(df) == 1
    row = df.iloc[0]
    assert row["Label"] == "Scenario 1"
    assert row["Timeframe"] == DEFAULT_SCENARIO_SETTINGS["timeframe"]
    assert row["Quantity"] == DEFAULT_SCENARIO_SETTINGS["quantity"]
    assert row["Stop Loss %"] == DEFAULT_SCENARIO_SETTINGS["stoploss_pct"]
    assert row["Trailing %"] == DEFAULT_SCENARIO_SETTINGS["trailing_pct"]
    assert row["adx_threshold"] == 25.0
    assert row["volume_ratio_min"] == 1.5


def test_blank_template_with_no_parameters_still_produces_the_shared_columns():
    content = build_blank_scenario_template({})

    df = pd.read_excel(BytesIO(content), sheet_name="Parameter Comparison")

    assert len(df) == 1
    assert set(df.columns) >= {
        "Label", "Timeframe", "Quantity", "Capital (₹)", "Stop Loss %",
        "Target %", "Trailing %", "Max Cycles/Day", "Start Time", "End Time",
        "Charges Enabled", "Date From", "Date To",
    }
    # Blank on purpose — duplicate/edit this row per year to sweep a date
    # range instead of one shared range for the whole job.
    assert pd.isna(df.iloc[0]["Date From"])
    assert pd.isna(df.iloc[0]["Date To"])


def test_blank_template_round_trips_through_the_scenario_parser():
    from runners.backtesting.batch_job_import import parse_scenarios_from_excel

    content = build_blank_scenario_template({"adx_threshold": 25.0})

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert len(scenarios) == 1
    s = scenarios[0]
    assert s.status == "pending"
    assert s.overrides == {"adx_threshold": 25.0}
    assert s.config_overrides["stoploss_pct"] == DEFAULT_SCENARIO_SETTINGS["stoploss_pct"]
