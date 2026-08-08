import datetime as dt

from runners.backtesting.historical_loader import load_equity_csv


def test_loads_ist_wall_clock_time_not_utc_shifted(tmp_path):
    # Kite's CSVs use tz-aware IST timestamps ("...+05:30"). A naive UTC
    # conversion (or a careless tz-strip) would shift 09:15 IST to 03:45 —
    # this is the exact bug caught during development.
    csv_path = tmp_path / "SAMPLE_historical.csv"
    csv_path.write_text(
        "date,open,high,low,close,volume\n"
        "2025-08-20 09:15:00+05:30,100.0,101.0,99.0,100.5,1000\n"
        "2025-08-20 09:20:00+05:30,100.5,102.0,100.0,101.5,1200\n"
    )

    df = load_equity_csv(str(csv_path))

    assert df["date"][0].time() == dt.time(9, 15)
    assert df["date"][0].tzinfo is None
    assert df["date"][1].time() == dt.time(9, 20)


def test_columns_and_dtypes(tmp_path):
    csv_path = tmp_path / "SAMPLE_historical.csv"
    csv_path.write_text(
        "date,open,high,low,close,volume\n"
        "2025-08-20 09:15:00+05:30,100.0,101.0,99.0,100.5,1000\n"
    )

    df = load_equity_csv(str(csv_path))

    assert df.columns == ["date", "open", "high", "low", "close", "volume"]
    assert df["close"][0] == 100.5


def test_sorts_by_date(tmp_path):
    csv_path = tmp_path / "SAMPLE_historical.csv"
    csv_path.write_text(
        "date,open,high,low,close,volume\n"
        "2025-08-20 09:20:00+05:30,101.0,101.0,101.0,101.0,100\n"
        "2025-08-20 09:15:00+05:30,100.0,100.0,100.0,100.0,100\n"
    )

    df = load_equity_csv(str(csv_path))

    assert df["date"].to_list() == sorted(df["date"].to_list())
    assert df["close"][0] == 100.0
