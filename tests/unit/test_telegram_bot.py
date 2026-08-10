import datetime as dt
from typing import Dict, Optional

from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_backtest_result_repository import SqlBacktestResultRepository
from infrastructure.persistence.sql_batch_job_repository import SqlBatchJobRepository
from core.domain.backtest_result import BacktestRunParams
from core.domain.batch_job import BatchJob, BatchJobScenario
from runners.backtesting.telegram_bot import handle_update, list_batch_ready_strategies, parse_caption

ALLOWED_USER_ID = 12345


class FakeTelegramClient:
    """Duck-types TelegramClient's three methods handle_update actually
    calls — records everything instead of touching the network, and
    serves a canned file's bytes for download_file()."""

    def __init__(self, file_content: bytes = b""):
        self.file_content = file_content
        self.messages: list[tuple[int, str]] = []
        self.documents: list[tuple[int, str, bytes, Optional[str]]] = []

    def download_file(self, file_id: str) -> bytes:
        return self.file_content

    def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))

    def send_document(self, chat_id: int, filename: str, content: bytes, caption: Optional[str] = None) -> None:
        self.documents.append((chat_id, filename, content, caption))


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
    from io import BytesIO
    import pandas as pd
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return buffer.getvalue()


def _repos(tmp_path):
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(session_factory().get_bind())
    return SqlBatchJobRepository(session_factory), SqlBacktestResultRepository(session_factory)


_next_update_id = [1]


def _update(message: dict) -> dict:
    _next_update_id[0] += 1
    return {"update_id": _next_update_id[0], "message": message}


def _document_message(caption: str = "", from_id: int = ALLOWED_USER_ID, chat_id: int = 999) -> dict:
    message = {
        "chat": {"id": chat_id},
        "from": {"id": from_id},
        "document": {"file_id": "abc123", "file_name": "scenarios.xlsx"},
    }
    if caption:
        message["caption"] = caption
    return message


def _text_message(text: str, from_id: int = ALLOWED_USER_ID, chat_id: int = 999) -> dict:
    return {"chat": {"id": chat_id}, "from": {"id": from_id}, "text": text}


def test_parse_caption_strategy_only():
    strategy, symbols = parse_caption("vwap_reclaim")
    assert strategy == "vwap_reclaim"
    assert symbols is None


def test_parse_caption_strategy_and_symbols():
    strategy, symbols = parse_caption("vwap_reclaim RELIANCE,TCS")
    assert strategy == "vwap_reclaim"
    assert symbols == ["RELIANCE", "TCS"]


def test_parse_caption_normalizes_case_and_whitespace():
    strategy, symbols = parse_caption("  VWAP_Reclaim   reliance, tcs ")
    assert strategy == "vwap_reclaim"
    assert symbols == ["RELIANCE", "TCS"]


def test_rejects_message_from_unauthorized_user(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_document_message("test_json_threshold", from_id=999999)),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert client.messages == [(999, "Not authorized.")]
    assert client.documents == []


def test_no_allowed_user_id_configured_means_anyone_is_allowed(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient(_workbook([{"Label": "a", "threshold": 100.5}]))
    pending: Dict[int, str] = {}

    handle_update(
        _update(_document_message("test_json_threshold", from_id=999999)),
        client, None, job_repo, result_repo, pending,
    )

    assert not any("Not authorized" in text for _, text in client.messages)


def test_missing_caption_asks_for_one_and_remembers_the_file(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(_update(_document_message()), client, ALLOWED_USER_ID, job_repo, result_repo, pending)

    assert len(client.messages) == 1
    assert "strategy name" in client.messages[0][1].lower()
    assert pending == {999: "abc123"}


def test_followup_text_after_captionless_file_completes_the_upload(tmp_path):
    # The real bug this covers: a user sends the file with no caption
    # (Telegram doesn't make the caption field obvious), then types the
    # strategy name as a separate message right after, the way you'd talk
    # to any other bot. That second message has no document at all, so it
    # must be matched back to the file via `pending`, not ignored.
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient(_workbook([{"Label": "a", "threshold": 100.5}]))
    pending: Dict[int, str] = {}

    handle_update(_update(_document_message()), client, ALLOWED_USER_ID, job_repo, result_repo, pending)
    assert pending == {999: "abc123"}

    handle_update(
        _update(_text_message("not_a_real_strategy")), client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert pending == {}  # consumed, whether or not the strategy name was valid
    assert any("Unknown strategy" in text for _, text in client.messages)


def test_plain_text_with_nothing_pending_is_silently_ignored(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(_update(_text_message("hello")), client, ALLOWED_USER_ID, job_repo, result_repo, pending)

    assert client.messages == []


def test_list_batch_ready_strategies_includes_json_strategies_and_excludes_others():
    names = list_batch_ready_strategies()

    assert "test_json_threshold" in names  # has a conditions.json
    assert "test_always_short" not in names  # hand-written screen(), no conditions.json
    assert names == sorted(names)


def test_strategies_command_lists_names(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(_update(_text_message("/strategies")), client, ALLOWED_USER_ID, job_repo, result_repo, pending)

    assert len(client.messages) == 1
    assert "test_json_threshold" in client.messages[0][1]


def test_strategies_command_is_case_insensitive_and_works_without_slash(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(_update(_text_message("Strategies")), client, ALLOWED_USER_ID, job_repo, result_repo, pending)

    assert len(client.messages) == 1
    assert "test_json_threshold" in client.messages[0][1]


def test_strategies_command_does_not_consume_a_pending_upload(tmp_path):
    # A pending captionless file should still be waiting after "/strategies"
    # — that command must never get treated as the strategy-name reply.
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(_update(_document_message()), client, ALLOWED_USER_ID, job_repo, result_repo, pending)
    assert pending == {999: "abc123"}

    handle_update(_update(_text_message("/strategies")), client, ALLOWED_USER_ID, job_repo, result_repo, pending)

    assert pending == {999: "abc123"}  # untouched
    assert "test_json_threshold" in client.messages[-1][1]


def test_file_built_for_a_different_strategy_gets_a_specific_error_not_a_job(tmp_path):
    # The scenario this covers: caption names a real strategy, but the
    # file's columns are some OTHER strategy's parameter names (every row
    # fails validation the same way) — this should read as "wrong file
    # for this strategy," not create a job, and definitely not crash the
    # bot.
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient(_workbook([
        {"Label": "a", "not_a_real_param_for_this_strategy": 1.5},
        {"Label": "b", "not_a_real_param_for_this_strategy": 2.0},
    ]))
    pending: Dict[int, str] = {}

    handle_update(
        _update(_document_message("test_json_threshold")), client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(client.messages) == 1
    message = client.messages[0][1]
    assert "different strategy" in message
    assert "not_a_real_param_for_this_strategy" in message
    assert "threshold" in message  # test_json_threshold's real parameter, listed as a hint
    assert job_repo.list_for_strategy("test_json_threshold") == []  # no job created at all


def test_file_with_some_valid_and_some_invalid_rows_still_creates_a_job(tmp_path, monkeypatch):
    # Contrast with the all-invalid case above: a MIX of good and bad rows
    # is a stray typo, not a wrong file — still worth running the good ones.
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    import runners.backtesting.telegram_bot as telegram_bot_module
    monkeypatch.setattr(telegram_bot_module, "_default_csv_path", lambda symbol: str(csv_path))
    monkeypatch.setattr(telegram_bot_module, "get_tradeable_watchlist_symbols", lambda: ["TEST"])

    client = FakeTelegramClient(_workbook([
        {"Label": "typo", "not_a_real_param": 1.0},
        {"Label": "good", "threshold": 100.5},
    ]))
    pending: Dict[int, str] = {}

    handle_update(
        _update(_document_message("test_json_threshold")), client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    jobs = job_repo.list_for_strategy("test_json_threshold")
    assert len(jobs) == 1
    assert jobs[0].total_scenarios == 2
    assert any("started" in text for _, text in client.messages)


def test_unknown_strategy_replies_with_error(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_document_message("not_a_real_strategy")), client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(client.messages) == 1
    assert "Unknown strategy" in client.messages[0][1]


def test_strategy_without_conditions_json_replies_with_error(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_document_message("test_always_short")), client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(client.messages) == 1
    assert "conditions.json" in client.messages[0][1]


def test_valid_upload_with_caption_runs_job_and_sends_result_document(tmp_path, monkeypatch):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    import runners.backtesting.telegram_bot as telegram_bot_module
    monkeypatch.setattr(telegram_bot_module, "_default_csv_path", lambda symbol: str(csv_path))
    monkeypatch.setattr(telegram_bot_module, "get_tradeable_watchlist_symbols", lambda: ["TEST"])

    # process_upload fires the actual job on a spawned daemon thread it
    # doesn't hand back a reference to — capture it here so the test can
    # join() deterministically instead of sleep-polling for the
    # "finished" message, which flaked under full-suite load (plenty of
    # time in isolation, occasionally not enough amid everything else
    # pytest has running).
    spawned_threads: list = []
    real_thread = telegram_bot_module.threading.Thread

    def _capturing_thread(*args, **kwargs):
        t = real_thread(*args, **kwargs)
        spawned_threads.append(t)
        return t

    monkeypatch.setattr(telegram_bot_module.threading, "Thread", _capturing_thread)

    content = _workbook([{"Label": "fires", "threshold": 100.5}])
    client = FakeTelegramClient(content)
    pending: Dict[int, str] = {}

    handle_update(
        _update(_document_message("test_json_threshold RELIANCE")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(spawned_threads) == 1
    spawned_threads[0].join(timeout=30)
    assert not spawned_threads[0].is_alive()  # timed out would mean the job never finished

    assert any("started" in text for _, text in client.messages)
    assert any("done" in text for _, text in client.messages)
    assert len(client.documents) == 1
    chat_id, filename, doc_content, _ = client.documents[0]
    assert chat_id == 999
    assert filename == "test_json_threshold_backtest_comparison.xlsx"
    assert len(doc_content) > 0


def test_valid_upload_via_followup_text_runs_job(tmp_path, monkeypatch):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    import runners.backtesting.telegram_bot as telegram_bot_module
    monkeypatch.setattr(telegram_bot_module, "_default_csv_path", lambda symbol: str(csv_path))
    monkeypatch.setattr(telegram_bot_module, "get_tradeable_watchlist_symbols", lambda: ["TEST"])

    spawned_threads: list = []
    real_thread = telegram_bot_module.threading.Thread

    def _capturing_thread(*args, **kwargs):
        t = real_thread(*args, **kwargs)
        spawned_threads.append(t)
        return t

    monkeypatch.setattr(telegram_bot_module.threading, "Thread", _capturing_thread)

    content = _workbook([{"Label": "fires", "threshold": 100.5}])
    client = FakeTelegramClient(content)
    pending: Dict[int, str] = {}

    handle_update(_update(_document_message()), client, ALLOWED_USER_ID, job_repo, result_repo, pending)
    handle_update(
        _update(_text_message("test_json_threshold RELIANCE")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(spawned_threads) == 1
    spawned_threads[0].join(timeout=30)
    assert not spawned_threads[0].is_alive()
    assert any("started" in text for _, text in client.messages)
    assert any("done" in text for _, text in client.messages)


def _seed_result(result_repo, strategy_name="test_json_threshold"):
    params = BacktestRunParams(
        strategy_name=strategy_name,
        symbols="TEST",
        timeframe="minute",
        date_from=dt.date(2026, 1, 1),
        date_to=dt.date(2026, 6, 30),
        quantity=50,
        stoploss_pct=0.8,
        target_pct=2.0,
        trailing_pct=1.0,
        max_cycles_per_day=10,
        start_time="09:20",
        end_time="11:30",
        charges_enabled=True,
        strategy_params_json='{"parameters": {"threshold": 100.5}}',
    )
    result_repo.save_result(params, {"metrics": {"total_trades": 5, "profit_factor": 1.2}})


def test_template_command_with_no_argument_sends_usage(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(_update(_text_message("/template")), client, ALLOWED_USER_ID, job_repo, result_repo, pending)

    assert len(client.messages) == 1
    assert "Usage" in client.messages[0][1]
    assert client.documents == []


def test_template_command_unknown_strategy(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_text_message("/template not_a_real_strategy")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert "Unknown strategy" in client.messages[0][1]
    assert client.documents == []


def test_template_command_sends_blank_template_document(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_text_message("/template test_json_threshold")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(client.documents) == 1
    chat_id, filename, content, _ = client.documents[0]
    assert chat_id == 999
    assert filename == "test_json_threshold_scenario_template.xlsx"
    assert len(content) > 0


def test_results_command_with_no_stored_results_says_so(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_text_message("results test_json_threshold")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(client.messages) == 1
    assert "No stored results" in client.messages[0][1]
    assert client.documents == []


def test_results_command_sends_comparison_document(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    _seed_result(result_repo)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_text_message("results test_json_threshold")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(client.documents) == 1
    chat_id, filename, content, _ = client.documents[0]
    assert chat_id == 999
    assert filename == "test_json_threshold_backtest_comparison.xlsx"
    assert len(content) > 0


def test_export_is_an_alias_for_results(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    _seed_result(result_repo)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_text_message("/export test_json_threshold")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(client.documents) == 1


def test_template_and_results_commands_do_not_consume_a_pending_upload(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(_update(_document_message()), client, ALLOWED_USER_ID, job_repo, result_repo, pending)
    assert pending == {999: "abc123"}

    handle_update(
        _update(_text_message("/template test_json_threshold")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert pending == {999: "abc123"}  # untouched — the file is still waiting on a real strategy-name reply


def test_status_command_with_no_argument_sends_usage(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(_update(_text_message("/status")), client, ALLOWED_USER_ID, job_repo, result_repo, pending)

    assert len(client.messages) == 1
    assert "Usage" in client.messages[0][1]


def test_status_command_unknown_strategy(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_text_message("/status not_a_real_strategy")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert "Unknown strategy" in client.messages[0][1]


def test_status_command_with_no_jobs_yet(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_text_message("status test_json_threshold")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert "No batch jobs" in client.messages[0][1]


def test_status_command_reports_progress_of_the_most_recent_job(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[
            BatchJobScenario(label="a", overrides={"threshold": 100.5}, status="done", saved_result_id=1),
            BatchJobScenario(label="b", overrides={"threshold": 200.0}, status="running"),
            BatchJobScenario(label="c", overrides={"threshold": 300.0}, status="pending"),
        ],
    ))
    # list_for_strategy returns newest-first — this second job is the one
    # "status" should report on, not the first.
    job = job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[BatchJobScenario(label="d", overrides={"threshold": 50.0}, status="done", saved_result_id=2)],
    ))
    job.status = "done"
    job_repo.save(job)

    client = FakeTelegramClient()
    pending: Dict[int, str] = {}
    handle_update(
        _update(_text_message("status test_json_threshold")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(client.messages) == 1
    message = client.messages[0][1]
    assert f"Job #{job.id}" in message
    assert "1/1 processed" in message
    assert "1 done" in message


def test_progress_is_an_alias_for_status(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    job_repo.create(BatchJob(
        strategy_name="test_json_threshold",
        shared_config={"capital": 100_000, "charges": True},
        scenarios=[BatchJobScenario(label="a", overrides={"threshold": 100.5}, status="running")],
    ))
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(
        _update(_text_message("/progress test_json_threshold")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert len(client.messages) == 1
    assert "0/1 processed" in client.messages[0][1]


def test_status_command_does_not_consume_a_pending_upload(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()
    pending: Dict[int, str] = {}

    handle_update(_update(_document_message()), client, ALLOWED_USER_ID, job_repo, result_repo, pending)
    assert pending == {999: "abc123"}

    handle_update(
        _update(_text_message("/status test_json_threshold")),
        client, ALLOWED_USER_ID, job_repo, result_repo, pending,
    )

    assert pending == {999: "abc123"}
