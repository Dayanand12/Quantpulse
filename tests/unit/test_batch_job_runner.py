import datetime as dt

from core.domain.batch_job import BatchJob, BatchJobScenario
from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_backtest_result_repository import SqlBacktestResultRepository
from infrastructure.persistence.sql_batch_job_repository import SqlBatchJobRepository
from runners.backtesting.batch_job_runner import run_batch_job
from strategies.test_json_threshold import TestJsonThresholdStrategy


def _bar(day, index, open_, high, low, close, volume=1000.0):
    return {
        "date": dt.datetime.combine(day, dt.time(9, 15)) + dt.timedelta(minutes=index),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


def _write_sample_csv(path):
    # Same fixture shape as tests/unit/test_batch_runner.py — warmup bars
    # at a flat 100.0, then an entry bar and an exit bar.
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


def _write_multi_year_csv(path):
    # Same intraday shape as _write_sample_csv, repeated once per year —
    # each year produces exactly one trade when it's the only year in
    # range, so filtering by Date From/Date To is directly observable in
    # how many trades come back.
    lines = ["date,open,high,low,close,volume"]
    for year in (2023, 2024, 2025):
        day = dt.date(year, 1, 5)
        rows = [_bar(day, i, 100.0, 100.0, 100.0, 100.0) for i in range(24)]
        rows.append(_bar(day, 24, 99.0, 99.0, 99.0, 99.0))
        rows.append(_bar(day, 25, 101.0, 101.0, 101.0, 101.0))
        rows.append(_bar(day, 26, 101.0, 103.5, 100.5, 103.0))
        for r in rows:
            lines.append(
                f"{r['date'].isoformat()}+05:30,{r['open']},{r['high']},{r['low']},{r['close']},{r['volume']}"
            )
    path.write_text("\n".join(lines))


def _repos(tmp_path):
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(session_factory().get_bind())
    return SqlBatchJobRepository(session_factory), SqlBacktestResultRepository(session_factory)


def test_processes_every_pending_scenario_and_saves_results(tmp_path):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[
            BatchJobScenario(label="fires", overrides={"threshold": 100.5}),
            BatchJobScenario(label="never fires", overrides={"threshold": 500.0}),
        ],
    ))

    run_batch_job(
        job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(job.id)
    assert saved.status == "done"
    assert saved.finished_at is not None
    assert [s.status for s in saved.scenarios] == ["done", "done"]

    fires, never_fires = saved.scenarios
    assert fires.saved_result_id is not None
    assert never_fires.saved_result_id is not None
    assert fires.saved_result_id != never_fires.saved_result_id

    fires_result = result_repo.get_result(fires.saved_result_id)
    assert fires_result.result["metrics"]["total_trades"] == 1
    never_fires_result = result_repo.get_result(never_fires.saved_result_id)
    assert never_fires_result.result["metrics"]["total_trades"] == 0


def test_invalid_scenarios_are_left_untouched_not_run(tmp_path):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[
            BatchJobScenario(label="bad", overrides={}, status="invalid", error="unknown parameter(s): typo"),
            BatchJobScenario(label="good", overrides={"threshold": 100.5}),
        ],
    ))

    run_batch_job(
        job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(job.id)
    assert saved.status == "done"
    bad, good = saved.scenarios
    assert bad.status == "invalid"  # never touched
    assert bad.saved_result_id is None
    assert good.status == "done"
    assert good.saved_result_id is not None


def test_job_fails_cleanly_when_no_symbol_has_historical_data(tmp_path):
    job_repo, result_repo = _repos(tmp_path)

    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[BatchJobScenario(label="a", overrides={"threshold": 100.5})],
    ))

    run_batch_job(
        job, TestJsonThresholdStrategy, [("MISSING", str(tmp_path / "no_such_file.csv"))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(job.id)
    assert saved.status == "failed"
    assert saved.error is not None
    assert saved.finished_at is not None


def test_processes_more_scenarios_than_one_chunk(tmp_path):
    # BATCH_JOB_CHUNK_SIZE is 6 — 8 scenarios exercises the multi-chunk path.
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[BatchJobScenario(label=f"s{i}", overrides={"threshold": 100.5}) for i in range(8)],
    ))

    run_batch_job(
        job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(job.id)
    assert saved.status == "done"
    assert all(s.status == "done" for s in saved.scenarios)
    assert len(saved.scenarios) == 8
    # Identical overrides across scenarios -> same dedup identity -> the
    # SAME stored backtest_results row for every one of them.
    assert len({s.saved_result_id for s in saved.scenarios}) == 1


def test_per_scenario_config_overrides_actually_take_effect(tmp_path):
    # A scenario's config_overrides (here: trailing_pct) reaches the
    # actual StrategyConfig run_batch_backtests executes with, not just
    # this scenario's label — proven by the two runs landing on distinct
    # dedup identities (trailing_pct is part of that identity) even though
    # both use the identical strategy-parameter override.
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True, "trailing_pct": 0.001},
        scenarios=[
            BatchJobScenario(label="default trailing", overrides={"threshold": 100.5}),
            BatchJobScenario(
                label="wide trailing", overrides={"threshold": 100.5},
                config_overrides={"trailing_pct": 5.0},
            ),
        ],
    ))

    run_batch_job(
        job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(job.id)
    assert saved.status == "done"
    tight, wide = saved.scenarios
    assert tight.saved_result_id is not None
    assert wide.saved_result_id is not None
    # Different resolved settings -> different dedup identity -> different
    # stored rows, even though `overrides` (the strategy parameters) match.
    assert tight.saved_result_id != wide.saved_result_id


def test_scenarios_sharing_identical_settings_are_grouped_into_one_saved_result(tmp_path):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[
            BatchJobScenario(label="a", overrides={"threshold": 100.5}, config_overrides={"quantity": 75}),
            BatchJobScenario(label="b", overrides={"threshold": 100.5}, config_overrides={"quantity": 75}),
            BatchJobScenario(label="c", overrides={"threshold": 100.5}, config_overrides={"quantity": 100}),
        ],
    ))

    run_batch_job(
        job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(job.id)
    assert saved.status == "done"
    a, b, c = saved.scenarios
    assert a.saved_result_id == b.saved_result_id  # same quantity -> same identity
    assert c.saved_result_id != a.saved_result_id  # different quantity -> distinct row


def test_a_scenario_identical_to_an_already_stored_result_is_skipped_not_rerun(tmp_path):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    first_job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[BatchJobScenario(label="original", overrides={"threshold": 100.5})],
    ))
    run_batch_job(
        first_job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )
    original_result_id = job_repo.get(first_job.id).scenarios[0].saved_result_id
    assert original_result_id is not None

    # A second upload — same strategy/symbols/dates/parameters — should
    # recognize this as already tested rather than recomputing it.
    second_job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[
            BatchJobScenario(label="reupload of the same thing", overrides={"threshold": 100.5}),
            BatchJobScenario(label="genuinely new", overrides={"threshold": 200.0}),
        ],
    ))
    run_batch_job(
        second_job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(second_job.id)
    assert saved.status == "done"
    same_as_before, new_one = saved.scenarios
    assert same_as_before.status == "skipped"
    assert same_as_before.saved_result_id == original_result_id
    assert new_one.status == "done"
    assert new_one.saved_result_id is not None
    assert new_one.saved_result_id != original_result_id


def test_scenarios_within_the_same_job_are_not_skipped_against_each_other(tmp_path):
    # The pre-run dedup check only looks at results that existed BEFORE
    # this job started — two scenarios in the SAME upload that happen to
    # resolve identically should both still run (well, share one
    # run_batch_backtests call and converge on one saved row, same as
    # test_scenarios_sharing_identical_settings_are_grouped_into_one_saved_result),
    # not have the second one skip itself against the first.
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[
            BatchJobScenario(label="a", overrides={"threshold": 100.5}),
            BatchJobScenario(label="b", overrides={"threshold": 100.5}),
        ],
    ))

    run_batch_job(
        job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(job.id)
    a, b = saved.scenarios
    assert a.status == "done"
    assert b.status == "done"  # not "skipped" against its own sibling
    assert a.saved_result_id == b.saved_result_id


def test_capital_override_does_not_change_dedup_identity(tmp_path):
    # Capital only rescales a scenario's own metrics at save time — two
    # scenarios differing ONLY in capital should still collide onto the
    # same stored row, same as core/domain/backtest_result.py's
    # BacktestRunParams excluding capital from the identity.
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[
            BatchJobScenario(label="a", overrides={"threshold": 100.5}, config_overrides={"capital": 50_000}),
            BatchJobScenario(label="b", overrides={"threshold": 100.5}, config_overrides={"capital": 200_000}),
        ],
    ))

    run_batch_job(
        job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(job.id)
    a, b = saved.scenarios
    assert a.saved_result_id == b.saved_result_id


def test_one_row_per_year_produces_distinct_year_scoped_results(tmp_path):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_multi_year_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[
            BatchJobScenario(
                label="2023", overrides={"threshold": 100.5},
                config_overrides={"date_from": "2023-01-01", "date_to": "2023-12-31"},
            ),
            BatchJobScenario(
                label="2024", overrides={"threshold": 100.5},
                config_overrides={"date_from": "2024-01-01", "date_to": "2024-12-31"},
            ),
            BatchJobScenario(
                label="2025", overrides={"threshold": 100.5},
                config_overrides={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            ),
        ],
    ))

    run_batch_job(
        job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(job.id)
    assert saved.status == "done"
    y2023, y2024, y2025 = saved.scenarios
    assert y2023.status == "done" and y2024.status == "done" and y2025.status == "done"

    # Three distinct date ranges -> three distinct stored rows, each with
    # exactly the one trade that actually falls inside its own year.
    ids = {y2023.saved_result_id, y2024.saved_result_id, y2025.saved_result_id}
    assert len(ids) == 3
    for scenario, year in ((y2023, 2023), (y2024, 2024), (y2025, 2025)):
        result = result_repo.get_result(scenario.saved_result_id)
        assert result.result["metrics"]["total_trades"] == 1
        assert result.params.date_from == dt.date(year, 1, 1)
        assert result.params.date_to == dt.date(year, 12, 31)


def test_reupload_with_an_additional_year_only_runs_the_new_year(tmp_path):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_multi_year_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    first_job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[
            BatchJobScenario(
                label="2023", overrides={"threshold": 100.5},
                config_overrides={"date_from": "2023-01-01", "date_to": "2023-12-31"},
            ),
        ],
    ))
    run_batch_job(
        first_job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )
    year_2023_id = job_repo.get(first_job.id).scenarios[0].saved_result_id
    assert year_2023_id is not None

    second_job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[
            BatchJobScenario(
                label="2023 again", overrides={"threshold": 100.5},
                config_overrides={"date_from": "2023-01-01", "date_to": "2023-12-31"},
            ),
            BatchJobScenario(
                label="2024 new", overrides={"threshold": 100.5},
                config_overrides={"date_from": "2024-01-01", "date_to": "2024-12-31"},
            ),
        ],
    ))
    run_batch_job(
        second_job, TestJsonThresholdStrategy, [("TEST", str(csv_path))], job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(second_job.id)
    same_year, new_year = saved.scenarios
    assert same_year.status == "skipped"
    assert same_year.saved_result_id == year_2023_id
    assert new_year.status == "done"
    assert new_year.saved_result_id != year_2023_id


def test_multi_symbol_job_saves_one_result_per_symbol(tmp_path):
    csv_a = tmp_path / "TEST_historical.csv"
    csv_b = tmp_path / "TEST2_historical.csv"
    _write_sample_csv(csv_a)
    _write_sample_csv(csv_b)
    job_repo, result_repo = _repos(tmp_path)

    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[BatchJobScenario(label="fires", overrides={"threshold": 100.5})],
    ))

    run_batch_job(
        job, TestJsonThresholdStrategy, [("TEST", str(csv_a)), ("TEST2", str(csv_b))],
        job_repo=job_repo, result_repo=result_repo,
    )

    saved = job_repo.get(job.id)
    assert saved.status == "done"
    [scenario] = saved.scenarios
    assert scenario.status == "done"

    # One stored row PER SYMBOL, not one combined row for the scenario.
    all_results = result_repo.list_results("test_json_threshold")
    assert len(all_results) == 2
    by_symbol = {r.params.symbols: r for r in all_results}
    assert set(by_symbol.keys()) == {"TEST", "TEST2"}
    assert by_symbol["TEST"].result["metrics"]["total_trades"] == 1
    assert by_symbol["TEST2"].result["metrics"]["total_trades"] == 1
    # scenario.saved_result_id is just a representative pointer to ONE of
    # the two — the real way to browse per-symbol results is the stored
    # rows themselves (Analysis tab filters), not this single id.
    assert scenario.saved_result_id in {by_symbol["TEST"].id, by_symbol["TEST2"].id}


def test_reupload_with_an_additional_symbol_only_needs_the_new_symbol_to_be_missing(tmp_path):
    # Per-symbol dedup granularity: a scenario is only "skipped" when
    # EVERY one of its symbols already has a matching stored row. Adding
    # a new symbol to the watchlist means the scenario still has to run
    # (this doesn't do partial-symbol runs), but the ALREADY-tested
    # symbol's row is upserted back to the same id, not duplicated, and
    # the new symbol gets its own fresh row.
    csv_a = tmp_path / "TEST_historical.csv"
    csv_b = tmp_path / "TEST2_historical.csv"
    _write_sample_csv(csv_a)
    _write_sample_csv(csv_b)
    job_repo, result_repo = _repos(tmp_path)

    first_job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[BatchJobScenario(label="fires", overrides={"threshold": 100.5})],
    ))
    run_batch_job(
        first_job, TestJsonThresholdStrategy, [("TEST", str(csv_a))],
        job_repo=job_repo, result_repo=result_repo,
    )
    test_id_after_first_run = {
        r.params.symbols: r.id for r in result_repo.list_results("test_json_threshold")
    }["TEST"]

    second_job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[BatchJobScenario(label="fires again", overrides={"threshold": 100.5})],
    ))
    run_batch_job(
        second_job, TestJsonThresholdStrategy, [("TEST", str(csv_a)), ("TEST2", str(csv_b))],
        job_repo=job_repo, result_repo=result_repo,
    )

    [scenario] = job_repo.get(second_job.id).scenarios
    assert scenario.status == "done"  # TEST2 is new, so this couldn't be skipped

    all_results = {r.params.symbols: r for r in result_repo.list_results("test_json_threshold")}
    assert set(all_results.keys()) == {"TEST", "TEST2"}
    # TEST's row was upserted in place (same identity), not duplicated.
    assert all_results["TEST"].id == test_id_after_first_run
