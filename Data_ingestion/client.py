import os
import time
import logging
import webbrowser
from threading import Thread
from flask import Flask, request
from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect, KiteTicker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load .env file
ENV_PATH = ".env"
load_dotenv(ENV_PATH)


class ZerodhaClient:
    def __init__(self, exchange=None, api_key=None, api_secret=None, access_token=None):
        self.api_key = api_key or os.getenv("API_KEY")
        self.api_secret = api_secret or os.getenv("API_SECRET")
        self.access_token = access_token or os.getenv("ACCESS_TOKEN")
        self.exchange= exchange


        if not self.api_key or not self.api_secret:
            raise ValueError("❌ API_KEY and API_SECRET must be set in .env file")

        self.kite = KiteConnect(api_key=self.api_key)

        # If access_token not available, trigger login flow
        if not self.access_token:
            self.access_token = self._auto_generate_access_token()

        # Set access token in KiteConnect
        self.kite.set_access_token(self.access_token)
        self.kws = KiteTicker(self.api_key, self.access_token)

    def _auto_generate_access_token(self):
        """Automatic login using Flask + browser."""
        app = Flask(__name__)

        @app.route("/callback")
        def callback():
            request_token = request.args.get("request_token")
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            access_token = data["access_token"]

            # Save access token in .env for reuse
            set_key(ENV_PATH, "ACCESS_TOKEN", access_token)
            print("✅ Login successful, token saved in .env")
            return "✅ Login successful! You can close this tab now."

        # Open login page
        login_url = self.kite.login_url()
        print(f"🌐 Opening browser for login: {login_url}")
        webbrowser.open(login_url)

        # Run Flask server in background
        server = Thread(target=lambda: app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False))
        server.daemon = True   # 👈 ensures Flask thread stops when main program exits
        server.start()

        # Wait until .env gets ACCESS_TOKEN
        try:
            timeout = 60  # seconds
            start_time = time.time()

            while True:
                load_dotenv(ENV_PATH, override=True)
                token = os.getenv("ACCESS_TOKEN")
                if token:
                    print("✅ Access token received!")
                    return token
                if time.time() - start_time > timeout:
                    raise TimeoutError("❌ Login timed out. Access token not received.")
                time.sleep(1)

        except TimeoutError as e:
            print(e)
            # Exit or handle as needed
            os._exit(0)

        except KeyboardInterrupt:
            print("\n❌ Interrupted by user. Exiting...")
            os._exit(0)


    def get_instrument_token(self, symbol, exchange):
        """Get instrument token for symbol."""
        exchange = exchange or self.exchange
        instruments = self.kite.instruments(exchange)
        for inst in instruments:
            if inst["tradingsymbol"] == symbol:
                return inst["instrument_token"]
        raise ValueError(f"❌ Token not found for {symbol}")

    def fetch_historical_data(self, symbol, interval, from_date, to_date, exchange):
        """Fetch OHLC historical data."""
        exchange = exchange or self.exchange
        token = self.get_instrument_token(symbol, exchange)
        data = self.kite.historical_data(
            instrument_token=token,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
        logging.info(f"Fetched {len(data)} candles for {symbol}")
        return data

    def get_live_quote(self, symbol, exchange):
        """Fetch one-time live snapshot."""
        exchange = exchange or self.exchange
        symbol_code = f"{exchange}:{symbol}"
        data = self.kite.quote([symbol_code])
        return data[symbol_code]

    def start_live_data(self, symbols, exchange):
        """Stream live ticks via WebSocket with auto-reconnect."""
        exchange = exchange or self.exchange
        tokens = [self.get_instrument_token(sym, exchange) for sym in symbols]

        self.live_ticks = []
        def on_ticks(ws, ticks):
            self.live_ticks = ticks

            for tick in ticks:
                token = tick['instrument_token']
                ltp = tick['last_price']
                ohlc = tick.get('ohlc', {})  # sometimes OHLC may be missing
                open_price = ohlc.get('open')
                high_price = ohlc.get('high')
                low_price = ohlc.get('low')
                close_price = ohlc.get('close')
                volume = tick.get('volume_traded', 0)

                print(f"Token: {token} | LTP: {ltp} | O: {open_price} | H: {high_price} | L: {low_price} | C: {close_price} | Volume: {volume}")

        def on_connect(ws, response):
            logging.info("Connected. Subscribing...")
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)

        def on_close(ws, code, reason):
            logging.warning(f"Connection closed: {reason}")

        def on_error(ws, code, reason):
            logging.error(f"WebSocket Error: {reason}")

        def on_noreconnect(ws):
            logging.error("Reconnection failed after multiple attempts!")

        def on_reconnect(ws, attempt_count):
            logging.warning(f"Reconnecting... Attempt #{attempt_count}")

        def on_order_update(ws, data):
            logging.info(f"Order Update: {data}")

        self.kws.on_ticks = on_ticks
        self.kws.on_connect = on_connect
        self.kws.on_close = on_close
        self.kws.on_error = on_error
        self.kws.on_noreconnect = on_noreconnect
        self.kws.on_reconnect = on_reconnect
        self.kws.on_order_update = on_order_update

        logging.info("Starting live data stream...")
        self.kws.connect(threaded=True, disable_ssl_verification=False)


# -------------------------
# Example usage
# -------------------------
if __name__ == "__main__":
    client = ZerodhaClient()
    quote = client.get_live_quote("INFY")
    print("Live Quote:", quote)
    # client.start_live_data(["INFY", "TCS"])
