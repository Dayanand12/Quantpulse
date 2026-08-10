import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient

from infrastructure.config.settings import get_settings
from infrastructure.persistence.database import Base, create_session_factory


def _bar(day, index, open_, high, low, close, volume=1000.0):
    return {
        "date": dt.datetime.combine(day, dt.time(9, 15)) + dt.timedelta(minutes=index),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


def _write_sample_csv(path):
    day = dt.date(2026, 1, 5)
    # Same shape as tests/unit/test_batch_runner.py's fixture — 24 flat
    # warmup bars (snapshot_builder.py needs the day from market open),
    # then a bar that trips a low threshold and a bar that closes the
    # resulting trade via the default 2.0% target.
    rows = [_bar(day, i, 100.0, 100.0, 100.0, 100.0) for i in range(24)]
    rows.append(_bar(day, 24, 99.0, 99.0, 99.0, 99.0))
    rows.append(_bar(day, 25, 101.0, 101.0, 101.0, 101.0))
    rows.append(_bar(day, 26, 101.0, 103.5, 100.5, 103.0))
    lines = ["date,open,high,low,close,volume"]
    for r in rows:
        lines.append(
            f"{r['date'].isoformat()}+05:30,{r['open']},{r['high']},{r['low']},{r['close']},{r['volume']}"
        )
    path.write_text("\n".join(lines))


@pytest.fixture
def batch_app(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    historical_dir = tmp_path / "historical_data"
    historical_dir.mkdir()
    _write_sample_csv(historical_dir / "TEST_historical.csv")
    _write_sample_csv(historical_dir / "TEST2_historical.csv")

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HISTORICAL_DATA_DIR", str(historical_dir))
    get_settings.cache_clear()

    import backtest_server  # imports the ORM models onto Base before create_all

    Base.metadata.create_all(create_session_factory(f"sqlite:///{db_path}")().get_bind())

    app = backtest_server.create_app()
    yield app

    get_settings.cache_clear()


BASE_PAYLOAD = {
    "strategy": "test_json_threshold",
    "symbols": ["TEST", "TEST2"],
    "quantity": 50,
    "date_from": "2026-01-01",
    "date_to": "2026-01-10",
}


def test_run_batch_executes_every_panel_and_saves_distinct_rows(batch_app):
    with TestClient(batch_app) as client:
        res = client.post("/api/backtest/run-batch", json={
            **BASE_PAYLOAD,
            "panels": [
                {"label": "fires", "overrides": {"threshold": 100.5}},
                {"label": "never fires", "overrides": {"threshold": 500.0}},
            ],
        })

        assert res.status_code == 200, res.text
        body = res.json()

        assert body["symbols_used"] == ["TEST", "TEST2"]
        assert len(body["panels"]) == 2

        fires, never_fires = body["panels"]
        assert fires["label"] == "fires"
        assert fires["total_trades"] == 2  # one per symbol
        assert fires["metrics"]["total_trades"] == 2
        assert "saved_result_id" in fires

        assert never_fires["label"] == "never fires"
        assert never_fires["total_trades"] == 0

        # Distinct overrides -> distinct stored rows for the same strategy.
        results = client.get("/api/backtest/results", params={"strategy": "test_json_threshold"}).json()
        assert len(results) == 2
        saved_ids = {p["saved_result_id"] for p in body["panels"]}
        assert saved_ids == {r["id"] for r in results}


def test_run_batch_rerunning_same_overrides_updates_the_same_row(batch_app):
    with TestClient(batch_app) as client:
        payload = {**BASE_PAYLOAD, "panels": [{"label": "fires", "overrides": {"threshold": 100.5}}]}

        first = client.post("/api/backtest/run-batch", json=payload).json()
        second = client.post("/api/backtest/run-batch", json=payload).json()

        assert first["panels"][0]["saved_result_id"] == second["panels"][0]["saved_result_id"]
        results = client.get("/api/backtest/results", params={"strategy": "test_json_threshold"}).json()
        assert len(results) == 1


def test_run_batch_rejects_unknown_override_parameter(batch_app):
    with TestClient(batch_app) as client:
        res = client.post("/api/backtest/run-batch", json={
            **BASE_PAYLOAD,
            "panels": [{"label": "bad", "overrides": {"not_a_real_param": 1.0}}],
        })

    assert res.status_code == 400


def test_run_batch_rejects_unknown_strategy(batch_app):
    with TestClient(batch_app) as client:
        res = client.post("/api/backtest/run-batch", json={
            **BASE_PAYLOAD,
            "strategy": "does_not_exist",
            "panels": [{"label": "a", "overrides": {}}],
        })

    assert res.status_code == 400


def test_run_batch_rejects_more_than_six_panels(batch_app):
    with TestClient(batch_app) as client:
        res = client.post("/api/backtest/run-batch", json={
            **BASE_PAYLOAD,
            "panels": [{"label": f"p{i}", "overrides": {}} for i in range(7)],
        })

    assert res.status_code == 422


def test_run_batch_with_save_false_does_not_persist(batch_app):
    with TestClient(batch_app) as client:
        res = client.post("/api/backtest/run-batch", json={
            **BASE_PAYLOAD,
            "save": False,
            "panels": [{"label": "fires", "overrides": {"threshold": 100.5}}],
        })

        assert res.status_code == 200
        assert "saved_result_id" not in res.json()["panels"][0]

        results = client.get("/api/backtest/results", params={"strategy": "test_json_threshold"}).json()
        assert results == []
