#run_live.py
import sys
import threading
import time

# Windows consoles default to cp1252, which can't encode the emoji used in
# print()/logging calls throughout this codebase and crashes on first use.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import uvicorn

from Data_ingestion.run_client import initialize_trading_environment
from services.filter_engine import start_engine
from core.container import build_container
from infrastructure.config.settings import get_settings
from infrastructure.logging.logger import configure_logging, get_logger
from infrastructure.persistence.migrate import run_migrations
from runners.paper_trading.deployment_runner import run_deployments
from runners.paper_trading.eod_scheduler import run_eod_scheduler
from runners.paper_trading.feed_watchdog import run_feed_watchdog
from runners.paper_trading.regime_call_evaluator import run_regime_call_evaluator
from runners.backtesting.telegram_bot import TelegramClient
from server.main import create_app


def main():
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(__name__)

    # -----------------------------
    # Ensure the SQLite schema is current (watchlist, deployments, ...)
    # -----------------------------
    run_migrations()

    # -----------------------------
    # Initialize Zerodha + Config
    # -----------------------------
    client, _, _, _ = initialize_trading_environment(
        config_file=settings.zerodha_config_file,
        json_file=settings.zerodha_stocks_file,
    )

    # -----------------------------
    # Composition root: wire every interface to its concrete adapter.
    # Symbols now come from the persisted watchlist (seeded from
    # stocks.json on first run) — see core/container.py::build_container.
    # -----------------------------
    container = build_container(settings, client)

    # -----------------------------
    # Create FastAPI App (IMPORTANT: before running)
    # -----------------------------
    app = create_app(container, settings)

    # -----------------------------
    # Start the market-wide screener funnel display (Screener page / Live
    # Dashboard) — display-only, independent of deployments.
    # -----------------------------
    threading.Thread(
        target=lambda: start_engine(container.live_engine),
        daemon=True,
    ).start()

    # -----------------------------
    # Run every deployment's own ExecutionManager
    # -----------------------------
    threading.Thread(
        target=lambda: run_deployments(container.deployment_runtimes),
        daemon=True,
    ).start()

    # -----------------------------
    # End-of-day trades/metrics report (backend/eod_report.py), written
    # automatically once a day at settings.eod_report_time
    # -----------------------------
    threading.Thread(
        target=lambda: run_eod_scheduler(
            container.session_factory,
            container.deployment_repository,
            settings.eod_report_time,
            settings.eod_report_dir,
            settings.database_url,
            settings.db_backup_dir,
            settings.db_backup_remote,
        ),
        daemon=True,
    ).start()

    # -----------------------------
    # Regime accuracy tracking: backfill forward returns on logged
    # _classify() calls (backend/market_analysis_engine.py) so the
    # Decision panel's win-rate stat has data to compute against.
    # -----------------------------
    threading.Thread(
        target=lambda: run_regime_call_evaluator(
            container.zerodha_client,
            container.regime_call_repository,
        ),
        daemon=True,
    ).start()

    # -----------------------------
    # Start Zerodha WebSocket
    # -----------------------------
    container.market_data_provider.start(container.watchlist_repository.get_all_symbols())

    # -----------------------------
    # Feed watchdog: Telegram alert if the live tick feed goes stale
    # (reuses the existing backtest-bot's TelegramClient + the same
    # telegram_allowed_user_id as the DM target). Off entirely if the bot
    # isn't configured, same as the backtest bot itself.
    # -----------------------------
    if settings.telegram_bot_token and settings.telegram_allowed_user_id:
        threading.Thread(
            target=lambda: run_feed_watchdog(
                container.market_data_provider,
                TelegramClient(settings.telegram_bot_token),
                settings.telegram_allowed_user_id,
                settings.feed_stale_threshold_seconds,
            ),
            daemon=True,
        ).start()
        logger.info(
            "Feed watchdog started (alerts via Telegram if quiet for >%ss during market hours).",
            settings.feed_stale_threshold_seconds,
        )
    else:
        logger.warning("Telegram not configured — feed watchdog alerts are disabled.")

    # -----------------------------
    # Tick Processing Loop (Background Thread)
    # -----------------------------
    def tick_loop():
        # One bad tick/indicator edge case must not kill this daemon thread
        # silently — that leaves the FastAPI server up and responsive while
        # nothing actually processes ticks anymore, which looks like
        # "everything's fine" from outside (see 2026-08-11 incident: engine
        # froze for hours with no error visible anywhere).
        while True:
            try:
                for symbol, tick in container.market_data_provider.get_latest_ticks().items():
                    container.trading_engine.process_tick(symbol, tick)
            except Exception:
                logger.exception("tick_loop iteration failed — continuing")
            time.sleep(0.5)

    threading.Thread(
        target=tick_loop,
        daemon=True,
    ).start()

    # -----------------------------
    # Start FastAPI Server (ONLY ONCE)
    # -----------------------------
    logger.info("Starting FastAPI server on %s:%s", settings.api_host, settings.api_port)
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
