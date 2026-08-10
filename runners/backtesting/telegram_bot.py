# runners/backtesting/telegram_bot.py
"""Telegram bot front door for bulk backtest scenario uploads — the same
pipeline the web UI's POST /api/backtest/batch-jobs uses
(runners/backtesting/batch_job_import.py + batch_job_runner.py), just
triggered by sending an .xlsx to a Telegram bot instead of clicking
Upload on the Backtest page. Meant to run as a background thread inside
backtest_server.py (see its lifespan), started only when
Settings.telegram_bot_token is configured — opt-in, no effect otherwise.

Uses long polling (getUpdates), not a webhook — backtest_server.py runs
on a local machine with no public HTTPS endpoint to receive a webhook
push, and polling needs nothing more than outbound internet access.

The strategy name (and optional symbols) can arrive two ways: as the
FILE's caption ("vwap_reclaim" or "vwap_reclaim RELIANCE,TCS", typed into
Telegram's caption field before sending the file), or as a plain text
message sent right AFTER a captionless file — Telegram doesn't make
attaching a caption obvious, so a real user's first instinct is usually
to send the file bare and then type the name as a follow-up, same as
chatting with any other bot. `_pending_uploads` (chat_id -> file_id)
is what connects that follow-up text back to the file that's waiting on
it — see handle_update().

The web form's Timeframe/Quantity/Stop Loss/Target/Trailing/etc. fields
have no Telegram equivalent, so a job started this way falls back to
DEFAULT_SCENARIO_SETTINGS unless a row in the sheet overrides a field
itself — every one of those fields is already per-row-overridable (see
core/domain/batch_job.py), so this only really matters for a Telegram
upload that leaves them all blank.
"""

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.application.interfaces.backtest_result_repository import IBacktestResultRepository
from core.application.interfaces.batch_job_repository import IBatchJobRepository
from core.domain.batch_job import BatchJob
from infrastructure.config.settings import get_settings
from runners.backtesting.batch_job_import import parse_scenarios_from_excel
from runners.backtesting.batch_job_runner import DEFAULT_SCENARIO_SETTINGS, run_batch_job
from runners.backtesting.report import build_blank_scenario_template, export_stored_results_to_excel
from runners.backtesting.result_persistence import read_strategy_params_json, symbols_identity
from runners.backtesting.strategy_resolver import (
    UnknownStrategyError,
    list_strategy_names,
    resolve_strategy_class,
)
from runners.backtesting.watchlist import get_tradeable_watchlist_symbols

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org"
_POLL_TIMEOUT_SECONDS = 30

# Any of these (case-insensitive) lists usable strategy names — typed as
# a plain message, not attached to a file. Both a bare word and a "/"
# command work since it's easy to forget Telegram's slash-command
# convention when you're just typing into a chat.
_LIST_STRATEGIES_COMMANDS = {"strategies", "list"}
# "template vwap_reclaim" / "/template vwap_reclaim" -> a blank starter
# workbook for that strategy. "results vwap_reclaim" / "/results
# vwap_reclaim" (or "export ...") -> every stored run for that strategy,
# same file the "Download Blank Template"/"Export Excel" buttons on the
# Backtest/Analysis pages produce — this is that same round trip, just
# without opening a browser first.
_TEMPLATE_COMMANDS = {"template"}
_RESULTS_COMMANDS = {"results", "export"}
# "status vwap_reclaim" / "/status vwap_reclaim" -> progress of that
# strategy's most recent batch job — how many of how many scenarios are
# done, without waiting passively for the "started"/"done" messages.
_STATUS_COMMANDS = {"status", "progress"}


def _default_csv_path(symbol: str) -> str:
    return os.path.join(get_settings().historical_data_dir, f"{symbol}_historical.csv")


def list_batch_ready_strategies() -> List[str]:
    """Strategy names this bot can actually run a batch upload for — only
    ones with a conditions.json (same requirement process_upload() checks
    at upload time; listing them here means you find out BEFORE typing a
    caption, not after). A strategy whose module fails to import is
    skipped, not raised — same "don't take the whole list down" reasoning
    as backtest_server.py's /api/backtest/strategies."""
    names = []
    for name in list_strategy_names():
        try:
            resolve_strategy_class(name)
        except Exception:
            continue
        if read_strategy_params_json(name):
            names.append(name)
    return sorted(names)


def _parse_command(text: str) -> Tuple[str, str]:
    """"template vwap_reclaim" -> ("template", "vwap_reclaim").
    "/results vwap_reclaim" -> ("results", "vwap_reclaim"). Leading "/" is
    optional and stripped either way — see _LIST_STRATEGIES_COMMANDS's
    reasoning."""
    parts = text.strip().split(maxsplit=1)
    command = parts[0].lstrip("/").lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    return command, arg


class TelegramClient:
    """Thin wrapper over Telegram's Bot HTTP API — a real class (not bare
    module functions) so tests can substitute a fake one instead of
    touching the network, same reasoning as this codebase's repository
    interfaces (IBacktestResultRepository etc.)."""

    def __init__(self, token: str):
        self._token = token
        self._base = f"{_API_BASE}/bot{token}"

    def get_updates(self, offset: Optional[int], timeout: int) -> List[dict]:
        resp = requests.get(
            f"{self._base}/getUpdates",
            params={"offset": offset, "timeout": timeout},
            timeout=timeout + 10,
        )
        resp.raise_for_status()
        return resp.json()["result"]

    def download_file(self, file_id: str) -> bytes:
        resp = requests.get(f"{self._base}/getFile", params={"file_id": file_id}, timeout=30)
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]
        content = requests.get(f"{_API_BASE}/file/bot{self._token}/{file_path}", timeout=60)
        content.raise_for_status()
        return content.content

    def send_message(self, chat_id: int, text: str) -> None:
        requests.post(f"{self._base}/sendMessage", data={"chat_id": chat_id, "text": text}, timeout=30)

    def send_document(self, chat_id: int, filename: str, content: bytes, caption: Optional[str] = None) -> None:
        data: Dict[str, Any] = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        requests.post(
            f"{self._base}/sendDocument", data=data,
            files={"document": (filename, content)}, timeout=120,
        )


def parse_caption(caption: str) -> Tuple[str, Optional[List[str]]]:
    """"vwap_reclaim" -> ("vwap_reclaim", None) — whole watchlist.
    "vwap_reclaim RELIANCE,TCS" -> ("vwap_reclaim", ["RELIANCE", "TCS"])."""
    parts = caption.strip().split(maxsplit=1)
    strategy_name = parts[0].strip().lower()
    symbols = None
    if len(parts) > 1:
        symbols = [s.strip().upper() for s in parts[1].split(",") if s.strip()]
    return strategy_name, symbols


def process_upload(
    chat_id: int,
    caption: str,
    file_id: str,
    client: TelegramClient,
    job_repo: IBatchJobRepository,
    result_repo: IBacktestResultRepository,
) -> None:
    """The actual "we have a file and a strategy name" flow — download,
    validate, parse, kick off the background job. Reachable either from a
    file sent WITH a caption, or from a captionless file followed by a
    plain-text reply (see handle_update()); either way, by the time this
    runs there's a concrete file_id and a caption-shaped string to parse."""
    strategy_name, symbol_list = parse_caption(caption)

    try:
        strategy_cls = resolve_strategy_class(strategy_name)
    except UnknownStrategyError as e:
        client.send_message(chat_id, str(e))
        return

    raw_params_json = read_strategy_params_json(strategy_name)
    if not raw_params_json:
        client.send_message(
            chat_id, f"{strategy_name!r} has no conditions.json — bulk parameter scenarios need one."
        )
        return
    valid_parameter_names = set(json.loads(raw_params_json).get("parameters", {}).keys())

    try:
        content = client.download_file(file_id)
    except Exception as e:
        client.send_message(chat_id, f"Couldn't download that file from Telegram: {e}")
        return

    try:
        scenarios = parse_scenarios_from_excel(content, valid_parameter_names)
    except Exception as e:
        client.send_message(chat_id, f"Couldn't read that file as an Excel workbook: {e}")
        return

    if not scenarios:
        client.send_message(
            chat_id, "No scenarios found in that file — check it has a header row plus at least one data row."
        )
        return

    if all(s.status == "invalid" for s in scenarios):
        # Every single row failed validation — almost always means this
        # file was built for a DIFFERENT strategy (its parameter columns
        # don't match this one's conditions.json at all), not a stray
        # typo on one row. Say so plainly and don't create a job at all —
        # a job where nothing could ever run is just noise in the
        # history, and burying "wrong file" inside a job's per-row
        # "invalid" reasons makes you go find and read them to learn
        # that, instead of being told outright.
        reasons = list(dict.fromkeys(s.error for s in scenarios if s.error))[:3]
        client.send_message(
            chat_id,
            f"None of the {len(scenarios)} row(s) in that file work for {strategy_name!r} — this usually "
            f"means the file was built for a different strategy.\n\n"
            f"Reason(s): {'; '.join(reasons)}\n\n"
            f"{strategy_name}'s actual parameters are: {', '.join(sorted(valid_parameter_names)) or '(none)'}. "
            f"Send \"template {strategy_name}\" to get a fresh file that matches.",
        )
        return

    resolved_symbols = symbol_list or get_tradeable_watchlist_symbols()
    if not resolved_symbols:
        client.send_message(chat_id, "No symbols to backtest (empty watchlist and none given).")
        return

    shared_config = {**DEFAULT_SCENARIO_SETTINGS, "symbols": symbol_list}
    job = job_repo.create(BatchJob(strategy_name=strategy_name, shared_config=shared_config, scenarios=scenarios))

    invalid_count = sum(1 for s in scenarios if s.status == "invalid")
    client.send_message(
        chat_id,
        f"Job #{job.id} started for {strategy_name}: {len(scenarios)} scenario(s)"
        + (f", {invalid_count} invalid (skipped)" if invalid_count else "")
        + ". I'll message you when it's done.",
    )

    symbol_csv_pairs = [(s, _default_csv_path(s)) for s in resolved_symbols]
    symbols_id = symbols_identity(symbol_list, is_full_watchlist=not symbol_list)

    def _run_and_reply() -> None:
        run_batch_job(job, strategy_cls, symbol_csv_pairs, symbols_id, job_repo, result_repo)

        finished = job_repo.get(job.id)
        counts: Dict[str, int] = {"done": 0, "skipped": 0, "invalid": 0, "error": 0}
        for s in finished.scenarios:
            counts[s.status] = counts.get(s.status, 0) + 1
        summary = (
            f"Job #{job.id} ({strategy_name}) {finished.status}: "
            f"{counts['done']} done, {counts['skipped']} already tested, "
            f"{counts['invalid']} invalid, {counts['error']} errored."
        )
        if finished.error:
            summary += f"\n{finished.error}"
        client.send_message(chat_id, summary)

        try:
            results = result_repo.list_results(strategy_name)
            if results:
                report = export_stored_results_to_excel(results)
                client.send_document(chat_id, f"{strategy_name}_backtest_comparison.xlsx", report)
        except Exception as e:
            client.send_message(chat_id, f"Job finished but couldn't build the result report: {e}")

    threading.Thread(target=_run_and_reply, daemon=True).start()


def send_blank_template(chat_id: int, strategy_name: str, client: TelegramClient) -> None:
    """"template <strategy_name>" — the bot-side equivalent of the
    Backtest page's "Download Blank Template" button (runners/
    backtesting/report.py::build_blank_scenario_template): one example
    row of that strategy's actual conditions.json parameter defaults,
    ready to duplicate/edit and send back as an upload."""
    strategy_name = strategy_name.strip().lower()
    if not strategy_name:
        client.send_message(
            chat_id,
            'Usage: "template <strategy_name>", e.g. "template vwap_reclaim". '
            'Send "/strategies" to see available names.',
        )
        return

    try:
        resolve_strategy_class(strategy_name)
    except UnknownStrategyError as e:
        client.send_message(chat_id, str(e))
        return

    raw_params_json = read_strategy_params_json(strategy_name)
    if not raw_params_json:
        client.send_message(
            chat_id, f"{strategy_name!r} has no conditions.json — bulk parameter scenarios need one."
        )
        return

    parameter_defaults = json.loads(raw_params_json).get("parameters", {})
    content = build_blank_scenario_template(parameter_defaults)
    client.send_document(chat_id, f"{strategy_name}_scenario_template.xlsx", content)


def send_past_results(
    chat_id: int, strategy_name: str, client: TelegramClient, result_repo: IBacktestResultRepository
) -> None:
    """"results <strategy_name>" (or "export ...") — the bot-side
    equivalent of the Analysis page's "Export Excel"/"Download From Past
    Runs" button: every stored run for that strategy in one workbook, on
    demand, without waiting for a job to finish first."""
    strategy_name = strategy_name.strip().lower()
    if not strategy_name:
        client.send_message(
            chat_id,
            'Usage: "results <strategy_name>", e.g. "results vwap_reclaim". '
            'Send "/strategies" to see available names.',
        )
        return

    try:
        resolve_strategy_class(strategy_name)
    except UnknownStrategyError as e:
        client.send_message(chat_id, str(e))
        return

    results = result_repo.list_results(strategy_name)
    if not results:
        client.send_message(chat_id, f"No stored results yet for {strategy_name!r}.")
        return

    content = export_stored_results_to_excel(results)
    client.send_document(chat_id, f"{strategy_name}_backtest_comparison.xlsx", content)


def send_job_status(
    chat_id: int, strategy_name: str, client: TelegramClient, job_repo: IBatchJobRepository
) -> None:
    """"status <strategy_name>" (or "progress ...") — how far along that
    strategy's most recent batch job is, on demand, instead of only
    finding out via the "started"/"done" messages that arrive on their
    own. job_repo.list_for_strategy() already returns newest-first, so
    the most recent job is just its first element."""
    strategy_name = strategy_name.strip().lower()
    if not strategy_name:
        client.send_message(
            chat_id,
            'Usage: "status <strategy_name>", e.g. "status vwap_reclaim". '
            'Send "/strategies" to see available names.',
        )
        return

    try:
        resolve_strategy_class(strategy_name)
    except UnknownStrategyError as e:
        client.send_message(chat_id, str(e))
        return

    jobs = job_repo.list_for_strategy(strategy_name, limit=1)
    if not jobs:
        client.send_message(chat_id, f"No batch jobs sent yet for {strategy_name!r}.")
        return

    job = jobs[0]
    counts: Dict[str, int] = {"pending": 0, "running": 0, "done": 0, "skipped": 0, "invalid": 0, "error": 0}
    for s in job.scenarios:
        counts[s.status] = counts.get(s.status, 0) + 1

    lines = [
        f"Job #{job.id} ({strategy_name}) — {job.status}",
        f"{job.processed_scenarios}/{job.total_scenarios} processed: "
        f"{counts['done']} done, {counts['skipped']} already tested, "
        f"{counts['invalid']} invalid, {counts['error']} errored.",
    ]
    if job.status == "running" and counts["running"]:
        currently = next((s.label for s in job.scenarios if s.status == "running"), None)
        if currently:
            lines.append(f"Currently on: {currently}")
    if job.error:
        lines.append(job.error)
    client.send_message(chat_id, "\n".join(lines))


def handle_update(
    update: dict,
    client: TelegramClient,
    allowed_user_id: Optional[int],
    job_repo: IBatchJobRepository,
    result_repo: IBacktestResultRepository,
    pending_uploads: Dict[int, str],
) -> None:
    """One Telegram update, of whatever shape. `pending_uploads` (chat_id
    -> file_id) is mutated in place — a captionless document is
    remembered here so the NEXT plain-text message from the same chat can
    complete it, instead of requiring the caption on the same message."""
    message = update.get("message")
    if not message:
        return  # not a plain chat message (e.g. edited_message, channel_post) — nothing to do

    chat_id = message["chat"]["id"]
    from_id = message.get("from", {}).get("id")

    if allowed_user_id is not None and from_id != allowed_user_id:
        if "document" in message or message.get("text"):
            client.send_message(chat_id, "Not authorized.")
        return

    document = message.get("document")
    if document:
        caption = (message.get("caption") or "").strip()
        if not caption:
            pending_uploads[chat_id] = document["file_id"]
            client.send_message(
                chat_id,
                "Got the file — now reply with the strategy name, e.g. \"vwap_reclaim\" or "
                "\"vwap_reclaim RELIANCE,TCS\" for specific symbols instead of the whole watchlist.",
            )
            return
        pending_uploads.pop(chat_id, None)
        process_upload(chat_id, caption, document["file_id"], client, job_repo, result_repo)
        return

    text = (message.get("text") or "").strip()
    command, arg = _parse_command(text) if text else ("", "")

    if command in _LIST_STRATEGIES_COMMANDS:
        names = list_batch_ready_strategies()
        if names:
            client.send_message(
                chat_id,
                "Strategies you can send a file for (tap and hold a line to copy):\n" + "\n".join(names),
            )
        else:
            client.send_message(chat_id, "No strategies with a conditions.json found.")
        return

    if command in _TEMPLATE_COMMANDS:
        send_blank_template(chat_id, arg, client)
        return

    if command in _RESULTS_COMMANDS:
        send_past_results(chat_id, arg, client, result_repo)
        return

    if command in _STATUS_COMMANDS:
        send_job_status(chat_id, arg, client, job_repo)
        return

    if text and chat_id in pending_uploads:
        file_id = pending_uploads.pop(chat_id)
        process_upload(chat_id, text, file_id, client, job_repo, result_repo)


def run_telegram_bot_forever(
    token: str,
    allowed_user_id: Optional[int],
    job_repo: IBatchJobRepository,
    result_repo: IBacktestResultRepository,
) -> None:
    """The long-polling loop — call this in its own daemon thread (see
    backtest_server.py's lifespan). Never returns; a transient network
    error is logged and retried after a short pause rather than raised,
    since this has no caller left to propagate an exception to."""
    client = TelegramClient(token)
    offset: Optional[int] = None
    pending_uploads: Dict[int, str] = {}
    logger.info("Telegram bot polling started")
    while True:
        try:
            updates = client.get_updates(offset, _POLL_TIMEOUT_SECONDS)
        except Exception as e:
            logger.warning("Telegram getUpdates failed: %s", e)
            time.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            try:
                handle_update(update, client, allowed_user_id, job_repo, result_repo, pending_uploads)
            except Exception as e:
                logger.exception("Error handling Telegram update: %s", e)
