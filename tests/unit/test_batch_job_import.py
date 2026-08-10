import datetime as dt
from io import BytesIO

import openpyxl
import pandas as pd

from runners.backtesting.batch_job_import import parse_scenarios_from_excel


def _workbook(rows: list[dict]) -> bytes:
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return buffer.getvalue()


def test_parses_valid_rows_into_pending_scenarios():
    content = _workbook([
        {"Label": "low adx", "adx_threshold": 15, "volume_ratio_threshold": 1.5},
        {"Label": "high adx", "adx_threshold": 35, "volume_ratio_threshold": 2.0},
    ])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold", "volume_ratio_threshold"})

    assert len(scenarios) == 2
    assert scenarios[0].label == "low adx"
    assert scenarios[0].overrides == {"adx_threshold": 15.0, "volume_ratio_threshold": 1.5}
    assert scenarios[0].status == "pending"
    assert scenarios[1].overrides == {"adx_threshold": 35.0, "volume_ratio_threshold": 2.0}


def test_missing_label_falls_back_to_row_number():
    content = _workbook([{"adx_threshold": 15}])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert scenarios[0].label == "Row 2"  # header is row 1, first data row is 2


def test_unknown_parameter_marks_whole_row_invalid():
    content = _workbook([
        {"Label": "typo", "adx_threshhold": 15},  # typo'd column name
        {"Label": "good", "adx_threshold": 25},
    ])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert len(scenarios) == 2
    bad, good = scenarios
    assert bad.status == "invalid"
    assert "adx_threshhold" in bad.error
    assert bad.overrides == {}  # the unknown column never lands in overrides
    assert good.status == "pending"
    assert good.overrides == {"adx_threshold": 25.0}


def test_non_numeric_value_marks_row_invalid():
    content = _workbook([{"Label": "bad value", "adx_threshold": "fifteen"}])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert scenarios[0].status == "invalid"
    assert "adx_threshold" in scenarios[0].error


def test_partially_valid_row_is_still_invalid_as_a_whole():
    # One good column, one bad — the row never RUNS with the bad column
    # silently dropped (a partial override is a different scenario than
    # the one actually intended); the valid column's value is still kept
    # on the scenario for debugging what was parsed before the problem.
    content = _workbook([{"Label": "mixed", "adx_threshold": 25, "nonexistent_param": 1.0}])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert len(scenarios) == 1
    assert scenarios[0].status == "invalid"
    assert scenarios[0].overrides == {"adx_threshold": 25.0}
    assert "nonexistent_param" in scenarios[0].error


def test_blank_trailing_row_is_silently_skipped():
    content = _workbook([
        {"Label": "real", "adx_threshold": 25},
        {"Label": None, "adx_threshold": None},
    ])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert len(scenarios) == 1
    assert scenarios[0].label == "real"


def test_risk_sizing_columns_are_read_per_row_into_config_overrides():
    content = _workbook([{
        "Label": "custom risk", "adx_threshold": 25,
        "Timeframe": "5minute", "Quantity": 100, "Stop Loss %": 1.2,
        "Target %": 3.0, "Trailing %": 0.5, "Max Cycles/Day": 5,
        "Start Time": "09:30", "End Time": "14:00", "Charges Enabled": "false",
        "Date From": "2024-01-01", "Date To": "2024-12-31",
    }])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert len(scenarios) == 1
    s = scenarios[0]
    assert s.status == "pending"
    assert s.overrides == {"adx_threshold": 25.0}
    assert s.config_overrides == {
        "timeframe": "5minute", "quantity": 100, "stoploss_pct": 1.2,
        "target_pct": 3.0, "trailing_pct": 0.5, "max_cycles_per_day": 5,
        "start_time": "09:30", "end_time": "14:00", "charges": False,
        "date_from": "2024-01-01", "date_to": "2024-12-31",
    }


def test_one_row_per_year_is_the_intended_use_case():
    content = _workbook([
        {"Label": "2023", "adx_threshold": 25, "Date From": "2023-01-01", "Date To": "2023-12-31"},
        {"Label": "2024", "adx_threshold": 25, "Date From": "2024-01-01", "Date To": "2024-12-31"},
        {"Label": "2025", "adx_threshold": 25, "Date From": "2025-01-01", "Date To": "2025-12-31"},
    ])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert [s.label for s in scenarios] == ["2023", "2024", "2025"]
    assert all(s.status == "pending" for s in scenarios)
    assert [s.config_overrides["date_from"] for s in scenarios] == [
        "2023-01-01", "2024-01-01", "2025-01-01",
    ]
    assert [s.config_overrides["date_to"] for s in scenarios] == [
        "2023-12-31", "2024-12-31", "2025-12-31",
    ]


def test_real_excel_date_cell_is_accepted_not_marked_invalid():
    # Same reasoning as the Start Time regression: typing a date into a
    # cell auto-formats it as a native Excel date — pandas hands the
    # parser a real datetime/pd.Timestamp, not the string "2024-01-01".
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Label", "adx_threshold", "Date From", "Date To"])
    ws.append(["2024", 25, dt.date(2024, 1, 1), dt.date(2024, 12, 31)])
    buffer = BytesIO()
    wb.save(buffer)

    scenarios = parse_scenarios_from_excel(buffer.getvalue(), {"adx_threshold"})

    assert scenarios[0].status == "pending"
    assert scenarios[0].config_overrides["date_from"] == "2024-01-01"
    assert scenarios[0].config_overrides["date_to"] == "2024-12-31"


def test_bad_date_marks_row_invalid():
    content = _workbook([{"Label": "bad", "adx_threshold": 25, "Date From": "01/01/2024"}])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert scenarios[0].status == "invalid"
    assert "Date From" in scenarios[0].error


def test_blank_config_cells_leave_config_overrides_empty():
    content = _workbook([{"Label": "defaults", "adx_threshold": 25, "Stop Loss %": None}])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert scenarios[0].config_overrides == {}


def test_bad_timeframe_marks_row_invalid():
    content = _workbook([{"Label": "bad tf", "adx_threshold": 25, "Timeframe": "2minute"}])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert scenarios[0].status == "invalid"
    assert "Timeframe" in scenarios[0].error


def test_real_excel_time_cell_is_accepted_not_marked_invalid():
    # Regression: typing "9:20" into a cell in real Excel (or authoring
    # via openpyxl directly) auto-formats it as a native TIME value —
    # pandas then hands the parser a real datetime.time object, not the
    # string "09:20". The parser used to str()-and-regex it blind, which
    # turned a perfectly normal time entry into a false "invalid" row.
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Label", "adx_threshold", "Start Time"])
    ws.append(["a", 25, dt.time(9, 20)])
    buffer = BytesIO()
    wb.save(buffer)

    scenarios = parse_scenarios_from_excel(buffer.getvalue(), {"adx_threshold"})

    assert len(scenarios) == 1
    assert scenarios[0].status == "pending"
    assert scenarios[0].config_overrides["start_time"] == "09:20"


def test_time_string_with_seconds_is_accepted():
    # pandas' own to_excel() round-trips a datetime.time value as the
    # string "09:20:00" (seconds included) rather than a time object —
    # a second real-world shape the parser needs to tolerate.
    content = _workbook([{"Label": "a", "adx_threshold": 25, "Start Time": "09:20:00"}])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert scenarios[0].status == "pending"
    assert scenarios[0].config_overrides["start_time"] == "09:20"


def test_bad_start_time_marks_row_invalid():
    content = _workbook([{"Label": "bad time", "adx_threshold": 25, "Start Time": "9:30"}])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert scenarios[0].status == "invalid"
    assert "Start Time" in scenarios[0].error


def test_bad_charges_value_marks_row_invalid():
    content = _workbook([{"Label": "bad bool", "adx_threshold": 25, "Charges Enabled": "maybe"}])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert scenarios[0].status == "invalid"
    assert "Charges Enabled" in scenarios[0].error


def test_known_export_columns_are_ignored_not_treated_as_parameters():
    content = _workbook([{
        "Label": "from export",
        "Result ID": 42,
        "Symbols": "RELIANCE,TCS",
        "Total Trades": 100,
        "Sharpe Ratio": 1.5,
        "adx_threshold": 25,
    }])

    scenarios = parse_scenarios_from_excel(content, {"adx_threshold"})

    assert len(scenarios) == 1
    assert scenarios[0].status == "pending"
    assert scenarios[0].overrides == {"adx_threshold": 25.0}
