#run_live.py
import threading
import time

from Data_ingestion.run_client import initialize_trading_environment
from engine import TradingEngine
from backend.filter_engine import start_engine
from UI.app import create_app

CAPITAL = 100000


def main():

    # -----------------------------
    # Initialize Zerodha + Config
    # -----------------------------
    client, config, json_data, data_manager = initialize_trading_environment(
        config_file="Data_ingestion/config.yaml",
        json_file="Data_ingestion/stocks.json"
    )

    symbols = json_data.get("symbols", [])

    # -----------------------------
    # Start Live Engine
    # -----------------------------
    engine = TradingEngine()
    live_engine = engine.start_live(symbols, capital=CAPITAL)

    # -----------------------------
    # Create Flask App (IMPORTANT: before running)
    # -----------------------------
    app = create_app(live_engine)

    # -----------------------------
    # Start ORB Screener in Background Thread
    # -----------------------------
    threading.Thread(
        target=lambda: start_engine(live_engine),
        daemon=True
    ).start()

    # -----------------------------
    # Start Zerodha WebSocket
    # -----------------------------
    client.start_live_data(symbols, config["settings"]["exchange"])

    # -----------------------------
    # Tick Processing Loop (Background Thread)
    # -----------------------------
    def tick_loop():
        while True:
            for symbol, tick_data in client.market_data.items():
                if "LTP" in tick_data:
                    live_engine.process_tick(symbol, tick_data)
            time.sleep(0.5)

    threading.Thread(
        target=tick_loop,
        daemon=True
    ).start()

    # -----------------------------
    # Start Flask Server (ONLY ONCE)
    # -----------------------------
    print("🚀 Starting Flask Server...")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()