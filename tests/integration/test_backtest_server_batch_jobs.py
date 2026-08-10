import datetime as dt
import time
from io import BytesIO

import pandas as pd
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


def _workbook(rows: list) -> bytes:
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return buffer.getvalue()


@pytest.fixture
def batch_app(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    historical_dir = tmp_path / "historical_data"
    historical_dir.mkdir()
    _write_sample_csv(historical_dir / "TEST_historical.csv")

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HISTORICAL_DATA_DIR", str(historical_dir))
    get_settings.cache_clear()

    import backtest_server

    Base.metadata.create_all(create_session_factory(f"sqlite:///{db_path}")().get_bind())

    app = backtest_server.create_app()
    yield app

    get_settings.cache_clear()


BASE_FORM = {
    "strategy": "test_json_threshold",
    "symbols": "TEST",
    "quantity": "50",
    "date_from": "2026-01-01",
    "date_to": "2026-01-10",
}


def _wait_for_job(client, job_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/backtest/batch-jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError(f"Job {job_id} did not finish within {timeout}s")


def test_upload_processes_every_scenario_in_the_background(batch_app):
    content = _workbook([
        {"Label": "fires", "threshold": 100.5},
        {"Label": "never fires", "threshold": 500.0},
    ])

    with TestClient(batch_app) as client:
        res = client.post(
            "/api/backtest/batch-jobs",
            data=BASE_FORM,
            files={"file": ("scenarios.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert res.status_code == 200, res.text
        created = res.json()
        assert created["status"] in ("pending", "running")
        assert created["total_scenarios"] == 2
        assert [s["status"] for s in created["scenarios"]] == ["pending", "pending"]

        job = _wait_for_job(client, created["id"])

        assert job["status"] == "done"
        assert job["processed_scenarios"] == 2
        fires, never_fires = job["scenarios"]
        assert fires["status"] == "done"
        assert fires["saved_result_id"] is not None
        assert never_fires["status"] == "done"
        assert never_fires["saved_result_id"] is not None

        results = client.get("/api/backtest/results", params={"strategy": "test_json_threshold"}).json()
        assert len(results) == 2


def test_upload_marks_invalid_row_without_running_it(batch_app):
    content = _workbook([
        {"Label": "typo", "not_a_real_param": 1.0},
        {"Label": "good", "threshold": 100.5},
    ])

    with TestClient(batch_app) as client:
        res = client.post(
            "/api/backtest/batch-jobs",
            data=BASE_FORM,
            files={"file": ("scenarios.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        created = res.json()
        bad, good = created["scenarios"]
        assert bad["status"] == "invalid"
        assert "not_a_real_param" in bad["error"]
        assert good["status"] == "pending"

        job = _wait_for_job(client, created["id"])

        bad, good = job["scenarios"]
        assert bad["status"] == "invalid"  # never touched by the runner
        assert bad["saved_result_id"] is None
        assert good["status"] == "done"
        assert good["saved_result_id"] is not None


def test_list_batch_jobs_for_strategy(batch_app):
    content = _workbook([{"Label": "a", "threshold": 100.5}])

    with TestClient(batch_app) as client:
        res = client.post(
            "/api/backtest/batch-jobs",
            data=BASE_FORM,
            files={"file": ("scenarios.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        job_id = res.json()["id"]
        _wait_for_job(client, job_id)

        jobs = client.get("/api/backtest/batch-jobs", params={"strategy": "test_json_threshold"}).json()

    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id


def test_get_unknown_batch_job_returns_400(batch_app):
    with TestClient(batch_app) as client:
        res = client.get("/api/backtest/batch-jobs/999999")

    assert res.status_code == 400


def test_upload_rejects_strategy_without_conditions_json(batch_app):
    content = _workbook([{"Label": "a", "threshold": 1.0}])

    with TestClient(batch_app) as client:
        res = client.post(
            "/api/backtest/batch-jobs",
            data={**BASE_FORM, "strategy": "test_always_short"},
            files={"file": ("scenarios.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

    assert res.status_code == 400


def test_template_endpoint_returns_a_valid_downloadable_workbook(batch_app):
    with TestClient(batch_app) as client:
        res = client.get("/api/backtest/batch-jobs/template", params={"strategy": "test_json_threshold"})

    assert res.status_code == 200
    assert res.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    df = pd.read_excel(BytesIO(res.content), sheet_name="Parameter Comparison")
    assert len(df) == 1
    assert df.iloc[0]["Label"] == "Scenario 1"
    assert df.iloc[0]["threshold"] == 100.0  # test_json_threshold.json's default


def test_template_endpoint_rejects_strategy_without_conditions_json(batch_app):
    with TestClient(batch_app) as client:
        res = client.get("/api/backtest/batch-jobs/template", params={"strategy": "test_always_short"})

    assert res.status_code == 400


def test_per_row_risk_settings_actually_change_the_saved_identity(batch_app):
    content = _workbook([
        {"Label": "default risk", "threshold": 100.5},
        {"Label": "wider trailing", "threshold": 100.5, "Trailing %": 5.0},
    ])

    with TestClient(batch_app) as client:
        res = client.post(
            "/api/backtest/batch-jobs",
            data=BASE_FORM,
            files={"file": ("scenarios.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        job = _wait_for_job(client, res.json()["id"])

        assert job["status"] == "done"
        default_risk, wider_trailing = job["scenarios"]
        assert default_risk["saved_result_id"] is not None
        assert wider_trailing["saved_result_id"] is not None
        # Different resolved Trailing % -> different dedup identity.
        assert default_risk["saved_result_id"] != wider_trailing["saved_result_id"]

        results = {
            r["id"]: r for r in client.get("/api/backtest/results", params={"strategy": "test_json_threshold"}).json()
        }
        assert results[wider_trailing["saved_result_id"]]["trailing_pct"] == 5.0
        assert results[default_risk["saved_result_id"]]["trailing_pct"] == 0.1


def test_upload_response_includes_config_overrides_per_scenario(batch_app):
    # Regression: _batch_job_to_dict originally omitted config_overrides
    # entirely, so the API response (and the frontend's per-row "Risk/
    # Sizing" column) never showed what a row had actually overridden,
    # even though the runner used it correctly under the hood.
    content = _workbook([{"Label": "custom", "threshold": 100.5, "Stop Loss %": 1.5}])

    with TestClient(batch_app) as client:
        res = client.post(
            "/api/backtest/batch-jobs",
            data=BASE_FORM,
            files={"file": ("scenarios.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        created = res.json()
        assert created["scenarios"][0]["config_overrides"] == {"stoploss_pct": 1.5}

        job = _wait_for_job(client, created["id"])
        assert job["scenarios"][0]["config_overrides"] == {"stoploss_pct": 1.5}


def test_reupload_of_export_plus_new_rows_only_runs_the_new_ones(batch_app):
    # The workflow this exists for: export your results, add a few new
    # scenarios to the same file, re-upload the whole thing — the rows
    # matching what's already stored should come back "skipped" pointing
    # at the SAME result id, not recomputed.
    with TestClient(batch_app) as client:
        first = client.post(
            "/api/backtest/batch-jobs",
            data=BASE_FORM,
            files={"file": (
                "scenarios.xlsx",
                _workbook([{"Label": "original", "threshold": 100.5}]),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )},
        )
        first_job = _wait_for_job(client, first.json()["id"])
        original_result_id = first_job["scenarios"][0]["saved_result_id"]
        assert original_result_id is not None

        second = client.post(
            "/api/backtest/batch-jobs",
            data=BASE_FORM,
            files={"file": (
                "scenarios.xlsx",
                _workbook([
                    {"Label": "same as before", "threshold": 100.5},
                    {"Label": "brand new", "threshold": 200.0},
                ]),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )},
        )
        second_job = _wait_for_job(client, second.json()["id"])

        same_as_before, brand_new = second_job["scenarios"]
        assert same_as_before["status"] == "skipped"
        assert same_as_before["saved_result_id"] == original_result_id
        assert brand_new["status"] == "done"
        assert brand_new["saved_result_id"] != original_result_id

        # Still only 2 distinct stored rows total — the reupload's
        # "same as before" row never created a duplicate.
        results = client.get("/api/backtest/results", params={"strategy": "test_json_threshold"}).json()
        assert len(results) == 2


def test_upload_rejects_empty_scenario_file(batch_app):
    content = _workbook([{"Label": None, "threshold": None}])

    with TestClient(batch_app) as client:
        res = client.post(
            "/api/backtest/batch-jobs",
            data=BASE_FORM,
            files={"file": ("scenarios.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

    assert res.status_code == 400
