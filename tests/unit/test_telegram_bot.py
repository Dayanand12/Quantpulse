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
    """Duck-types TelegramClient's methods handle_update actually calls —
    records everything instead of touching the network, and serves a
    canned file's bytes for download_file()."""

    def __init__(self, file_content: bytes = b""):
        self.file_content = file_content
        self.messages: list[tuple[int, str]] = []
        self.documents: list[tuple[int, str, bytes, Optional[str]]] = []
        self.edits: list[tuple[int, int, str, Optional[dict]]] = []
        self.answered_callback_ids: list[str] = []

    def download_file(self, file_id: str) -> bytes:
        return self.file_content

    def send_message(self, chat_id: int, text: str, reply_markup: Optional[dict] = None) -> None:
        self.messages.append((chat_id, text))

    def edit_message_text(
        self, chat_id: int, message_id: int, text: str, reply_markup: Optional[dict] = None
    ) -> None:
        self.edits.append((chat_id, message_id, text, reply_markup))

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> None:
        self.answered_callback_ids.append(callback_query_id)

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


def _callback_query_update(
    data: str, from_id: int = ALLOWED_USER_ID, chat_id: int = 999, message_id: int = 555,
    callback_id: str = "cb1",
) -> dict:
    _next_update_id[0] += 1
    return {
        "update_id": _next_update_id[0],
        "callback_query": {
            "id": callback_id,
            "from": {"id": from_id},
            "message": {"chat": {"id": chat_id}, "message_id": message_id},
            "data": data,
        },
    }


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


# -----------------------------------------------------------------------
# Inline-button menu
# -----------------------------------------------------------------------

def test_menu_command_shows_main_menu(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    handle_update(_update(_text_message("menu")), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    assert len(client.messages) == 1
    assert "inline_keyboard" not in client.messages[0][1]  # sanity: keyboard is a separate arg, not text


def test_callback_query_from_unauthorized_user_is_rejected(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    handle_update(
        _callback_query_update("menu", from_id=99999), client, ALLOWED_USER_ID, job_repo, result_repo, {},
    )

    assert client.answered_callback_ids == ["cb1"]  # spinner always cleared, even when unauthorized
    assert client.edits == []
    assert any("Not authorized" in text for _, text in client.messages)


def test_every_callback_query_gets_answered(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    handle_update(_callback_query_update("menu"), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    assert client.answered_callback_ids == ["cb1"]


def test_menu_callback_edits_message_with_main_menu_keyboard(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    handle_update(_callback_query_update("menu"), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    assert len(client.edits) == 1
    chat_id, message_id, text, reply_markup = client.edits[0]
    assert chat_id == 999
    assert message_id == 555
    assert reply_markup is not None
    labels = [btn["text"] for row in reply_markup["inline_keyboard"] for btn in row]
    assert "🧪 Run Backtest" in labels
    assert "📊 View Results" in labels
    assert "🔴 Live Status" in labels
    assert "🔄 Restart Backtest Server" in labels


def test_run_callback_lists_runnable_strategies(tmp_path, monkeypatch):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    import runners.backtesting.telegram_bot as telegram_bot_module
    monkeypatch.setattr(telegram_bot_module, "list_runnable_strategies", lambda: ["vwap_reclaim", "orb_reversal"])

    handle_update(_callback_query_update("run"), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    _, _, _, reply_markup = client.edits[0]
    callback_datas = [btn["callback_data"] for row in reply_markup["inline_keyboard"] for btn in row]
    assert "run:s:vwap_reclaim" in callback_datas
    assert "run:s:orb_reversal" in callback_datas


def test_run_strategy_callback_shows_watchlist_picker(tmp_path, monkeypatch):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    import runners.backtesting.telegram_bot as telegram_bot_module
    from runners.backtesting.watchlist import TradeableWatchlist
    monkeypatch.setattr(
        telegram_bot_module, "get_named_watchlists",
        lambda: [TradeableWatchlist(id=1, name="Nifty50", symbols=["RELIANCE", "TCS"])],
    )

    handle_update(
        _callback_query_update("run:s:vwap_reclaim"), client, ALLOWED_USER_ID, job_repo, result_repo, {},
    )

    _, _, text, reply_markup = client.edits[0]
    assert "vwap_reclaim" in text
    callback_datas = [btn["callback_data"] for row in reply_markup["inline_keyboard"] for btn in row]
    assert "run:w:vwap_reclaim:all" in callback_datas
    assert "run:w:vwap_reclaim:1" in callback_datas


def test_run_watchlist_id_callback_executes_backtest_and_saves_per_symbol(tmp_path, monkeypatch):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    import runners.backtesting.telegram_bot as telegram_bot_module
    from runners.backtesting.watchlist import TradeableWatchlist
    monkeypatch.setattr(telegram_bot_module, "_default_csv_path", lambda symbol: str(csv_path))
    monkeypatch.setattr(
        telegram_bot_module, "get_named_watchlists",
        lambda: [TradeableWatchlist(id=7, name="Test List", symbols=["TEST"])],
    )

    spawned_threads: list = []
    real_thread = telegram_bot_module.threading.Thread

    def _capturing_thread(*args, **kwargs):
        t = real_thread(*args, **kwargs)
        spawned_threads.append(t)
        return t

    monkeypatch.setattr(telegram_bot_module.threading, "Thread", _capturing_thread)

    client = FakeTelegramClient()
    handle_update(
        _callback_query_update("run:w:test_json_threshold:7"), client, ALLOWED_USER_ID, job_repo, result_repo, {},
    )

    assert len(spawned_threads) == 1
    spawned_threads[0].join(timeout=30)
    assert not spawned_threads[0].is_alive()

    assert any("Running" in text for _, text in client.messages)
    assert any("Done" in text for _, text in client.messages)

    results = result_repo.list_results("test_json_threshold")
    assert len(results) == 1
    assert results[0].params.symbols == "TEST"


def test_results_callback_with_no_stored_results(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    handle_update(
        _callback_query_update("res:s:vwap_reclaim"), client, ALLOWED_USER_ID, job_repo, result_repo, {},
    )

    _, _, text, _ = client.edits[0]
    assert "No stored results" in text


def test_results_callback_with_stored_results_shows_summary(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    from core.domain.backtest_result import BacktestRunParams
    params = BacktestRunParams(
        strategy_name="vwap_reclaim", symbols="RELIANCE", timeframe="minute",
        date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 12, 31),
        quantity=50, stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1, max_cycles_per_day=10,
        start_time="09:20", end_time="11:30", charges_enabled=True,
    )
    result_repo.save_result(params, {"metrics": {"total_trades": 5, "win_rate": 60.0, "profit_factor": 1.5}})

    client = FakeTelegramClient()
    handle_update(
        _callback_query_update("res:s:vwap_reclaim"), client, ALLOWED_USER_ID, job_repo, result_repo, {},
    )

    _, _, text, reply_markup = client.edits[0]
    assert "1 stored result" in text
    assert "RELIANCE" in text
    callback_datas = [btn["callback_data"] for row in reply_markup["inline_keyboard"] for btn in row]
    assert "res:x:vwap_reclaim" in callback_datas


def test_results_export_callback_sends_document(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    from core.domain.backtest_result import BacktestRunParams
    params = BacktestRunParams(
        strategy_name="vwap_reclaim", symbols="RELIANCE", timeframe="minute",
        date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 12, 31),
        quantity=50, stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1, max_cycles_per_day=10,
        start_time="09:20", end_time="11:30", charges_enabled=True,
    )
    result_repo.save_result(params, {"metrics": {"total_trades": 5}})

    client = FakeTelegramClient()
    handle_update(
        _callback_query_update("res:x:vwap_reclaim"), client, ALLOWED_USER_ID, job_repo, result_repo, {},
    )

    assert len(client.documents) == 1


def test_live_callback_when_live_app_unreachable(tmp_path, monkeypatch):
    job_repo, result_repo = _repos(tmp_path)
    import runners.backtesting.telegram_bot as telegram_bot_module

    def _raise(*args, **kwargs):
        raise ConnectionError("refused")

    monkeypatch.setattr(telegram_bot_module.requests, "get", _raise)

    client = FakeTelegramClient()
    handle_update(_callback_query_update("live"), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    assert any("Can't reach the live app" in text for _, text in client.messages)


def test_live_callback_summarizes_running_deployments(tmp_path, monkeypatch):
    job_repo, result_repo = _repos(tmp_path)
    import runners.backtesting.telegram_bot as telegram_bot_module

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_get(url, timeout=5):
        if url.endswith("/api/health"):
            return _FakeResponse({"feed_stale": False})
        return _FakeResponse([
            {"strategy_name": "vwap_reclaim", "running": True, "status": {"open_position_count": 2, "realized_pnl": 150.0}},
            {"strategy_name": "orb_reversal", "running": False, "status": None},
        ])

    monkeypatch.setattr(telegram_bot_module.requests, "get", _fake_get)

    client = FakeTelegramClient()
    handle_update(_callback_query_update("live"), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    assert len(client.messages) == 1
    text = client.messages[0][1]
    assert "live" in text
    assert "vwap_reclaim" in text
    assert "orb_reversal" not in text  # not running -> not listed


def test_restart_callback_refuses_when_a_batch_job_is_running(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    job_repo.create(BatchJob(
        strategy_name="vwap_reclaim", shared_config={}, scenarios=[BatchJobScenario(label="a", overrides={})],
    ))
    running_job = job_repo.list_for_strategy("vwap_reclaim")[0]
    running_job.status = "running"
    job_repo.save(running_job)

    client = FakeTelegramClient()
    handle_update(_callback_query_update("restart"), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    _, _, text, _ = client.edits[0]
    assert "running" in text.lower()
    assert "vwap_reclaim" in text


def test_restart_callback_shows_confirm_prompt_when_nothing_running(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    handle_update(_callback_query_update("restart"), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    _, _, text, reply_markup = client.edits[0]
    assert "restart" in text.lower()
    callback_datas = [btn["callback_data"] for row in reply_markup["inline_keyboard"] for btn in row]
    assert "restart:go" in callback_datas
    assert "restart:no" in callback_datas


def test_restart_confirm_callback_actually_restarts(tmp_path, monkeypatch):
    job_repo, result_repo = _repos(tmp_path)
    import runners.backtesting.telegram_bot as telegram_bot_module

    restart_calls = []
    monkeypatch.setattr(telegram_bot_module, "_restart_backtest_server", lambda: restart_calls.append(True))

    client = FakeTelegramClient()
    handle_update(_callback_query_update("restart:go"), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    assert restart_calls == [True]
    assert any("Restarting" in text for _, text in client.messages)


def test_restart_confirm_callback_re_checks_for_a_job_started_in_the_gap(tmp_path, monkeypatch):
    job_repo, result_repo = _repos(tmp_path)
    import runners.backtesting.telegram_bot as telegram_bot_module

    restart_calls = []
    monkeypatch.setattr(telegram_bot_module, "_restart_backtest_server", lambda: restart_calls.append(True))

    job_repo.create(BatchJob(
        strategy_name="vwap_reclaim", shared_config={}, scenarios=[BatchJobScenario(label="a", overrides={})],
    ))
    running_job = job_repo.list_for_strategy("vwap_reclaim")[0]
    running_job.status = "running"
    job_repo.save(running_job)

    client = FakeTelegramClient()
    handle_update(_callback_query_update("restart:go"), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    assert restart_calls == []  # never actually restarted
    _, _, text, _ = client.edits[0]
    assert "vwap_reclaim" in text


def test_restart_cancel_callback_returns_to_menu(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    handle_update(_callback_query_update("restart:no"), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    _, _, text, reply_markup = client.edits[0]
    assert "Cancelled" in text
    labels = [btn["text"] for row in reply_markup["inline_keyboard"] for btn in row]
    assert "🧪 Run Backtest" in labels


# -----------------------------------------------------------------------
# "run <strategy> [symbols]" text command — the single/specific-symbol
# path the button flow can't offer (see _RUN_COMMANDS).
# -----------------------------------------------------------------------

def test_run_command_with_no_argument_shows_usage(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    handle_update(_update(_text_message("run")), client, ALLOWED_USER_ID, job_repo, result_repo, {})

    assert len(client.messages) == 1
    assert "Usage" in client.messages[0][1]


def test_run_command_with_unknown_strategy(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    handle_update(
        _update(_text_message("run not_a_real_strategy")), client, ALLOWED_USER_ID, job_repo, result_repo, {},
    )

    assert any("not_a_real_strategy" in text for _, text in client.messages)


def test_run_command_with_single_symbol_saves_exactly_that_symbol(tmp_path, monkeypatch):
    csv_path = tmp_path / "TEST_historical.csv"
    _write_sample_csv(csv_path)
    job_repo, result_repo = _repos(tmp_path)

    import runners.backtesting.telegram_bot as telegram_bot_module
    monkeypatch.setattr(telegram_bot_module, "_default_csv_path", lambda symbol: str(csv_path))

    spawned_threads: list = []
    real_thread = telegram_bot_module.threading.Thread

    def _capturing_thread(*args, **kwargs):
        t = real_thread(*args, **kwargs)
        spawned_threads.append(t)
        return t

    monkeypatch.setattr(telegram_bot_module.threading, "Thread", _capturing_thread)

    client = FakeTelegramClient()
    handle_update(
        _update(_text_message("run test_json_threshold TEST")), client, ALLOWED_USER_ID, job_repo, result_repo, {},
    )

    assert len(spawned_threads) == 1
    spawned_threads[0].join(timeout=30)
    assert not spawned_threads[0].is_alive()

    assert any("Running" in text for _, text in client.messages)
    assert any("Done" in text for _, text in client.messages)
    results = result_repo.list_results("test_json_threshold")
    assert len(results) == 1
    assert results[0].params.symbols == "TEST"


def test_run_command_with_no_symbols_falls_back_to_whole_watchlist(tmp_path, monkeypatch):
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

    client = FakeTelegramClient()
    handle_update(
        _update(_text_message("run test_json_threshold")), client, ALLOWED_USER_ID, job_repo, result_repo, {},
    )

    spawned_threads[0].join(timeout=30)
    results = result_repo.list_results("test_json_threshold")
    assert len(results) == 1
    assert results[0].params.symbols == "TEST"


def test_run_watchlist_picker_message_mentions_the_run_command(tmp_path):
    job_repo, result_repo = _repos(tmp_path)
    client = FakeTelegramClient()

    handle_update(
        _callback_query_update("run:s:vwap_reclaim"), client, ALLOWED_USER_ID, job_repo, result_repo, {},
    )

    _, _, text, _ = client.edits[0]
    assert "run vwap_reclaim" in text
