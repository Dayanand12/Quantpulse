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
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.application.interfaces.backtest_result_repository import IBacktestResultRepository
from core.application.interfaces.batch_job_repository import IBatchJobRepository
from core.domain.batch_job import BatchJob
from core.domain.charges import ChargeConfig
from core.domain.metrics import compute_performance_metrics
from core.domain.models import StrategyConfig
from infrastructure.config.settings import get_settings
from runners.backtesting.batch_job_import import parse_scenarios_from_excel
from runners.backtesting.batch_job_runner import DEFAULT_SCENARIO_SETTINGS, run_batch_job
from runners.backtesting.engine import run_backtest
from runners.backtesting.historical_loader import load_backtest_csv
from runners.backtesting.report import build_blank_scenario_template, export_stored_results_to_excel
from runners.backtesting.result_persistence import (
    read_strategy_params_json,
    required_dynamic_indicators,
    save_per_symbol_results,
)
from runners.backtesting.strategy_resolver import (
    UnknownStrategyError,
    list_strategy_names,
    resolve_strategy_class,
)
from runners.backtesting.watchlist import get_named_watchlists, get_tradeable_watchlist_symbols

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
# "run vwap_reclaim" (whole watchlist) or "run vwap_reclaim RELIANCE" /
# "run vwap_reclaim RELIANCE,TCS" (one or a few specific symbols) -> the
# same immediate button-triggered backtest as the "Run Backtest" menu
# button, just typed instead of tapped. This is the ONLY way to pick a
# single/specific symbol from Telegram — the button flow only offers
# "whole watchlist" or a named watchlist, since listing every individual
# symbol as its own button doesn't scale any better here than it would on
# the web Backtest form (which uses a text search box for exactly this,
# not a button grid — see SymbolAutocomplete.tsx).
_RUN_COMMANDS = {"run"}
# "menu" / "start" / "/start" (Telegram's own default first-message
# command) -> the inline-button main menu, an alternative front door to
# the same capabilities the text commands above already provide, plus
# Live Status and Restart which have no text-command equivalent.
_MENU_COMMANDS = {"menu", "start"}

# The live paper-trading app (server/main.py) is a SEPARATE process/port
# from this one (backtest_server.py) — deliberately, see this module's
# docstring and CLAUDE.md ("no Zerodha session needed" for backtesting).
# "Live Status" reaches across to it the same way the frontend does, over
# plain localhost HTTP, not by importing any of its wiring.
_LIVE_APP_BASE = "http://127.0.0.1:5000"


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

    def send_message(self, chat_id: int, text: str, reply_markup: Optional[dict] = None) -> None:
        data: Dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            data["reply_markup"] = json.dumps(reply_markup)
        requests.post(f"{self._base}/sendMessage", data=data, timeout=30)

    def edit_message_text(
        self, chat_id: int, message_id: int, text: str, reply_markup: Optional[dict] = None
    ) -> None:
        """Updates an already-sent message in place — what makes inline-
        button menu navigation feel like one screen changing rather than
        a new message spammed for every tap."""
        data: Dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup is not None:
            data["reply_markup"] = json.dumps(reply_markup)
        requests.post(f"{self._base}/editMessageText", data=data, timeout=30)

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> None:
        """MUST be called for every button tap, even just to acknowledge
        it with no text — otherwise Telegram's client shows that button's
        tiny loading spinner indefinitely."""
        data: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            data["text"] = text
        requests.post(f"{self._base}/answerCallbackQuery", data=data, timeout=30)

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

    def _run_and_reply() -> None:
        run_batch_job(job, strategy_cls, symbol_csv_pairs, job_repo, result_repo)

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


def run_backtest_command(
    chat_id: int, arg: str, client: TelegramClient, result_repo: IBacktestResultRepository
) -> None:
    """"run <strategy_name>" (whole watchlist) or "run <strategy_name>
    SYMBOL1,SYMBOL2" (one or a few specific symbols) — the text-command
    equivalent of the "Run Backtest" menu button, and the only way to
    target a single symbol from Telegram (see _RUN_COMMANDS). Reuses
    parse_caption() — same "name" / "name SYM1,SYM2" shape the file-
    upload caption already accepts."""
    if not arg:
        client.send_message(
            chat_id,
            'Usage: "run <strategy_name>" for the whole watchlist, or '
            '"run <strategy_name> SYMBOL1,SYMBOL2" for specific symbols, e.g. "run vwap_reclaim RELIANCE". '
            'Send "/strategies" to see available names.',
        )
        return

    strategy_name, symbol_list = parse_caption(arg)
    try:
        resolve_strategy_class(strategy_name)
    except UnknownStrategyError as e:
        client.send_message(chat_id, str(e))
        return

    symbols = symbol_list or get_tradeable_watchlist_symbols()
    if not symbols:
        client.send_message(chat_id, "No symbols to backtest (empty watchlist and none given).")
        return

    _execute_backtest_via_telegram(chat_id, strategy_name, symbols, client, result_repo)


# -----------------------------------------------------------------------
# Inline-button menu: an alternative front door to the same capabilities
# as the text commands above, plus Live Status and Restart which have no
# text-command equivalent. Callback data is a short "namespace:step:arg"
# string (Telegram caps it at 64 bytes) — see handle_callback_query()
# for the full routing table.
# -----------------------------------------------------------------------

def _kb(rows: List[List[Tuple[str, str]]]) -> dict:
    """rows: each a list of (button label, callback_data) pairs — one
    inner list per keyboard ROW, so [[a, b], [c]] renders two buttons on
    the first row and one on the second."""
    return {"inline_keyboard": [[{"text": label, "callback_data": data} for label, data in row] for row in rows]}


def _main_menu_keyboard() -> dict:
    return _kb([
        [("🧪 Run Backtest", "run")],
        [("📊 View Results", "res")],
        [("🔴 Live Status", "live")],
        [("🔄 Restart Backtest Server", "restart")],
    ])


def list_runnable_strategies() -> List[str]:
    """Every strategy resolvable for a plain backtest run — unlike
    list_batch_ready_strategies(), a conditions.json isn't required here:
    a button-triggered run has no per-row parameter overrides, it just
    uses whatever the strategy currently does (see
    _execute_backtest_via_telegram)."""
    names = []
    for name in list_strategy_names():
        try:
            resolve_strategy_class(name)
        except Exception:
            continue
        names.append(name)
    return sorted(names)


def _strategy_picker_keyboard(prefix: str) -> dict:
    rows = [[(name, f"{prefix}:s:{name}")] for name in list_runnable_strategies()]
    rows.append([("« Back", "menu")])
    return _kb(rows)


def _watchlist_picker_keyboard(strategy_name: str) -> dict:
    rows = [[("Whole watchlist (union)", f"run:w:{strategy_name}:all")]]
    for w in get_named_watchlists():
        rows.append([(f"{w.name} ({len(w.symbols)})", f"run:w:{strategy_name}:{w.id}")])
    rows.append([("« Back", "run")])
    return _kb(rows)


def _fmt_metrics_summary(m: Dict[str, Any]) -> str:
    def fmt(key: str, spec: str = "{:.2f}") -> str:
        value = m.get(key)
        return spec.format(value) if value is not None else "—"

    return (
        f"{m.get('total_trades', 0)} trades · Win rate {fmt('win_rate', '{:.1f}%')} · "
        f"Profit factor {fmt('profit_factor')}\n"
        f"Net P&L: ₹{fmt('total_pnl', '{:,.0f}')} · Sharpe {fmt('sharpe_ratio')} · "
        f"Max drawdown {fmt('max_drawdown_pct', '{:.1f}%')}"
    )


def _execute_backtest_via_telegram(
    chat_id: int,
    strategy_name: str,
    symbols: List[str],
    client: TelegramClient,
    result_repo: IBacktestResultRepository,
) -> None:
    """"Run Backtest" button's actual execution — same engine call and
    the same save_per_symbol_results() the web UI's POST /api/backtest/run
    uses, just triggered from a tapped button. Always runs at
    DEFAULT_SCENARIO_SETTINGS's risk/sizing — no per-field Telegram
    equivalent to the web form's Stop Loss/Target/etc inputs, same
    limitation process_upload() already documents for file uploads. Fine
    tuning still goes through the web UI or an Excel upload."""
    try:
        strategy_cls = resolve_strategy_class(strategy_name)
    except UnknownStrategyError as e:
        client.send_message(chat_id, str(e))
        return

    client.send_message(chat_id, f"Running {strategy_name} on {len(symbols)} symbol(s) at default settings…")

    def _run() -> None:
        settings = DEFAULT_SCENARIO_SETTINGS
        config = StrategyConfig(
            quantity=settings["quantity"], stoploss_pct=settings["stoploss_pct"],
            target_pct=settings["target_pct"], trailing_pct=settings["trailing_pct"],
            max_cycles_per_day=settings["max_cycles_per_day"], start_time=settings["start_time"],
            end_time=settings["end_time"], timeframe=settings["timeframe"],
        )
        charge_config = ChargeConfig() if settings["charges"] else None
        extra_indicators = required_dynamic_indicators(strategy_name)

        all_trades = []
        symbols_used = []
        data_min = data_max = None
        for symbol in symbols:
            try:
                df = load_backtest_csv(_default_csv_path(symbol))
            except FileNotFoundError:
                continue
            df_min, df_max = df["date"].min().date(), df["date"].max().date()
            data_min = df_min if data_min is None else min(data_min, df_min)
            data_max = df_max if data_max is None else max(data_max, df_max)
            trades = run_backtest(
                strategy_cls(), symbol, df, config, charge_config=charge_config,
                extra_indicators=extra_indicators,
            )
            all_trades.extend(trades)
            symbols_used.append(symbol)

        if not symbols_used:
            client.send_message(chat_id, "No historical data found for any of those symbols.")
            return

        metrics = compute_performance_metrics(all_trades, settings["capital"])
        save_per_symbol_results(
            result_repo, strategy_name=strategy_name, symbols_used=symbols_used, all_trades=all_trades,
            config=config, charges_enabled=bool(settings["charges"]), date_from=data_min, date_to=data_max,
            capital=settings["capital"],
        )
        client.send_message(
            chat_id,
            f"Done — {strategy_name} on {len(symbols_used)} symbol(s).\n{_fmt_metrics_summary(asdict(metrics))}\n\n"
            f"Saved one result per symbol — browse them on the Analysis tab, or send "
            f"\"results {strategy_name}\" here for the full Excel export.",
        )

    threading.Thread(target=_run, daemon=True).start()


def _results_summary_keyboard(strategy_name: str) -> dict:
    return _kb([
        [("📎 Export Excel", f"res:x:{strategy_name}")],
        [("« Back", "res")],
    ])


def send_results_summary(
    chat_id: int,
    message_id: int,
    strategy_name: str,
    client: TelegramClient,
    result_repo: IBacktestResultRepository,
) -> None:
    """"View Results" button, after a strategy is picked — a quick
    glanceable summary (count + best-by-profit-factor combo) rather than
    trying to list every stored result as buttons (there can be
    thousands, one per symbol per parameter combo — see
    save_per_symbol_results). "Export Excel" underneath is the same file
    the "results <name>" text command already sends, for the full
    picture."""
    results = result_repo.list_results(strategy_name)
    if not results:
        client.edit_message_text(
            chat_id, message_id, f"No stored results yet for {strategy_name!r}.",
            _strategy_picker_keyboard("res"),
        )
        return

    best = max(results, key=lambda r: r.result.get("metrics", {}).get("profit_factor") or 0)
    lines = [
        f"{strategy_name}: {len(results)} stored result(s).",
        "",
        f"Best by profit factor — {best.params.symbols}, {best.params.timeframe}, "
        f"SL {best.params.stoploss_pct}/TP {best.params.target_pct}/Trail {best.params.trailing_pct}:",
        _fmt_metrics_summary(best.result.get("metrics", {})),
    ]
    client.edit_message_text(chat_id, message_id, "\n".join(lines), _results_summary_keyboard(strategy_name))


def send_live_status(chat_id: int, client: TelegramClient) -> None:
    """"Live Status" button — calls the LIVE app's own REST API (a
    separate process/port, server/main.py) over plain localhost HTTP, the
    same way the frontend does. This bot's own process (backtest_server.py)
    has no live-trading wiring of its own, deliberately — see this
    module's docstring."""
    try:
        health = requests.get(f"{_LIVE_APP_BASE}/api/health", timeout=5).json()
        deployments = requests.get(f"{_LIVE_APP_BASE}/api/deployments", timeout=5).json()
    except Exception:
        client.send_message(
            chat_id,
            "Can't reach the live app on port 5000 — is `python run_live.py` (or run_all.py) running?",
        )
        return

    lines = ["Feed: " + ("STALE ⚠️" if health.get("feed_stale") else "live ✅")]
    running = [d for d in deployments if d.get("running")]
    if not running:
        lines.append("No deployments currently running.")
    for d in running:
        status = d.get("status") or {}
        lines.append(
            f"• {d['strategy_name']}: {status.get('open_position_count', 0)} open · "
            f"today ₹{status.get('realized_pnl', 0):,.0f}"
        )
    client.send_message(chat_id, "\n".join(lines))


def _any_batch_job_running(job_repo: IBatchJobRepository) -> Optional[str]:
    """Mirrors the manual check CLAUDE.md documents before ever
    restarting backtest_server.py — force-killing it mid-job orphans that
    job at status="running" forever, since nothing else will ever finish
    it."""
    for name in list_strategy_names():
        if any(j.status == "running" for j in job_repo.list_for_strategy(name, limit=3)):
            return name
    return None


def _restart_confirm_keyboard() -> dict:
    return _kb([[("⚠️ Confirm Restart", "restart:go"), ("Cancel", "restart:no")]])


def _restart_backtest_server() -> None:
    """Spawns a fresh backtest_server.py process, then exits this one —
    there's no supervisor watching this process, so the replacement has
    to already be starting before this one dies, not after. A brief 409
    from Telegram's getUpdates while the old poller's connection hasn't
    been released yet is expected (see this module's docstring/
    CLAUDE.md's documented ~10s gap) and self-heals via
    run_telegram_bot_forever's own retry loop once the new process's
    poller starts."""
    repo_root = Path(__file__).resolve().parents[2]
    subprocess.Popen([sys.executable, "run_backtest_server.py"], cwd=str(repo_root))
    os._exit(0)


def handle_callback_query(
    callback_query: dict,
    client: TelegramClient,
    allowed_user_id: Optional[int],
    job_repo: IBatchJobRepository,
    result_repo: IBacktestResultRepository,
) -> None:
    """One tapped inline-button. Always answered first (query_id) even
    when unauthorized/malformed — otherwise Telegram's client leaves that
    button's tiny loading spinner stuck indefinitely."""
    query_id = callback_query["id"]
    client.answer_callback_query(query_id)

    from_id = callback_query.get("from", {}).get("id")
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    data = callback_query.get("data", "")

    if chat_id is None or message_id is None:
        return
    if allowed_user_id is not None and from_id != allowed_user_id:
        client.send_message(chat_id, "Not authorized.")
        return

    if data == "menu":
        client.edit_message_text(chat_id, message_id, "What do you want to do?", _main_menu_keyboard())
    elif data == "run":
        client.edit_message_text(chat_id, message_id, "Pick a strategy to backtest:", _strategy_picker_keyboard("run"))
    elif data == "res":
        client.edit_message_text(chat_id, message_id, "Pick a strategy to view results for:", _strategy_picker_keyboard("res"))
    elif data == "live":
        send_live_status(chat_id, client)
    elif data == "restart":
        running = _any_batch_job_running(job_repo)
        if running:
            client.edit_message_text(
                chat_id, message_id,
                f"Not restarting — a batch job is currently running for {running!r}. Try again once it finishes.",
                _main_menu_keyboard(),
            )
        else:
            client.edit_message_text(chat_id, message_id, "Restart the backtest server now?", _restart_confirm_keyboard())
    elif data == "restart:no":
        client.edit_message_text(chat_id, message_id, "Cancelled.", _main_menu_keyboard())
    elif data == "restart:go":
        # Re-checked right before acting, not just at the confirm prompt —
        # closes the race where a job started in the gap between the two taps.
        running = _any_batch_job_running(job_repo)
        if running:
            client.edit_message_text(
                chat_id, message_id, f"Not restarting — {running!r} just started a batch job.", _main_menu_keyboard(),
            )
            return
        client.edit_message_text(chat_id, message_id, "Restarting…")
        client.send_message(chat_id, "Restarting the backtest server now — back in a few seconds.")
        _restart_backtest_server()
    elif data.startswith("run:s:"):
        strategy_name = data.split(":", 2)[2]
        client.edit_message_text(
            chat_id, message_id,
            f"Run {strategy_name} on which symbols? Pick a watchlist below, or for one/a few specific "
            f"symbols instead, send: \"run {strategy_name} SYMBOL1,SYMBOL2\"",
            _watchlist_picker_keyboard(strategy_name),
        )
    elif data.startswith("run:w:"):
        _, _, strategy_name, watchlist_ref = data.split(":", 3)
        if watchlist_ref == "all":
            symbols = get_tradeable_watchlist_symbols()
        else:
            match = next((w for w in get_named_watchlists() if str(w.id) == watchlist_ref), None)
            symbols = match.symbols if match else []
        if not symbols:
            client.edit_message_text(chat_id, message_id, "That watchlist has no symbols.", _main_menu_keyboard())
            return
        client.edit_message_text(chat_id, message_id, f"Starting {strategy_name}…")
        _execute_backtest_via_telegram(chat_id, strategy_name, symbols, client, result_repo)
    elif data.startswith("res:s:"):
        strategy_name = data.split(":", 2)[2]
        send_results_summary(chat_id, message_id, strategy_name, client, result_repo)
    elif data.startswith("res:x:"):
        strategy_name = data.split(":", 2)[2]
        send_past_results(chat_id, strategy_name, client, result_repo)


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
    callback_query = update.get("callback_query")
    if callback_query:
        handle_callback_query(callback_query, client, allowed_user_id, job_repo, result_repo)
        return

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

    if command in _MENU_COMMANDS:
        client.send_message(chat_id, "What do you want to do?", _main_menu_keyboard())
        return

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

    if command in _RUN_COMMANDS:
        run_backtest_command(chat_id, arg, client, result_repo)
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
