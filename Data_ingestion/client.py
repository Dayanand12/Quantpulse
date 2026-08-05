import os
import time
import logging
import webbrowser
from threading import Thread
from flask import Flask, request
from werkzeug.serving import make_server
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
        self.exchange = exchange

        if not self.api_key or not self.api_secret:
            raise ValueError("❌ API_KEY and API_SECRET must be set in .env file")

        self.kite = KiteConnect(api_key=self.api_key)

        # Initialize market_data dict here
        self.market_data = {}

        # Instrument dumps are the same all day and expensive to fetch
        # (thousands of rows) — cache per exchange (plus one entry for the
        # no-exchange/global lookup) instead of hitting kite.instruments()
        # on every get_instrument_token() call. Matters most for callers
        # that look up the same symbol repeatedly (e.g.
        # backend/market_analysis_engine.py, polled every few seconds).
        self._instruments_cache = {}

        # A saved access_token from a previous day is almost always expired
        # (Kite tokens are valid until ~6am the next day) — verify it still
        # works before trusting it, otherwise re-run the login flow.
        if self.access_token and not self._is_token_valid(self.access_token):
            logging.warning("Saved ACCESS_TOKEN is expired/invalid — re-running login.")
            self.access_token = None

        # If access_token not available, trigger login flow
        if not self.access_token:
            self.access_token = self._auto_generate_access_token()

        # ✅ Now that token is ready, set it in KiteConnect and create KiteTicker
        self.kite.set_access_token(self.access_token)
        self.kws = KiteTicker(self.api_key, self.access_token)


    def _is_token_valid(self, access_token):
        """Cheap check: a token is only valid if Kite accepts it for a real call."""
        try:
            probe = KiteConnect(api_key=self.api_key)
            probe.set_access_token(access_token)
            probe.profile()
            return True
        except Exception:
            return False

    def _auto_generate_access_token(self):
        """Automatic login using Flask + browser."""
        app = Flask(__name__)
        result = {}

        @app.route("/callback")
        def callback():
            request_token = request.args.get("request_token")
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            access_token = data["access_token"]

            # Save access token in .env for reuse
            set_key(ENV_PATH, "ACCESS_TOKEN", access_token)
            result["token"] = access_token
            print("✅ Login successful, token saved in .env")

            # Stop the callback server so the main app can bind this port.
            Thread(target=httpd.shutdown, daemon=True).start()
            return "✅ Login successful! You can close this tab now."

        # Open login page
        login_url = self.kite.login_url()
        print(f"🌐 Opening browser for login: {login_url}")
        webbrowser.open(login_url)

        # Run a shutdown-able Flask server in the background. This listens
        # on the same port (5000) the main app will use later, so it MUST
        # be stopped (see callback() above) before this function returns —
        # otherwise the main server can never bind that port.
        httpd = make_server("127.0.0.1", 5000, app)
        server = Thread(target=httpd.serve_forever)
        server.daemon = True
        server.start()

        try:
            timeout = 60  # seconds
            start_time = time.time()

            while "token" not in result:
                if time.time() - start_time > timeout:
                    httpd.shutdown()
                    raise TimeoutError("❌ Login timed out. Access token not received.")
                time.sleep(0.5)

            server.join(timeout=5)
            print("✅ Access token received!")
            return result["token"]

        except TimeoutError as e:
            print(e)
            raise

        except KeyboardInterrupt:
            httpd.shutdown()
            print("\n❌ Interrupted by user. Exiting...")
            raise


    def _cached_instruments(self, exchange=None):
        """exchange=None fetches Kite's global instrument list (needed for
        indices, which aren't under a single tradeable exchange)."""
        cache_key = exchange or "__global__"
        if cache_key not in self._instruments_cache:
            self._instruments_cache[cache_key] = (
                self.kite.instruments(exchange) if exchange else self.kite.instruments()
            )
        return self._instruments_cache[cache_key]

    def get_instrument_token(self, symbol, exchange):
        """Get instrument token for symbol (supports indices like NIFTY 50)."""
        exchange = exchange or self.exchange

        # Try normal exchange lookup first (stocks etc.)
        for inst in self._cached_instruments(exchange):
            if inst["tradingsymbol"] == symbol:
                return inst["instrument_token"]

        # If not found, try global instrument list (for indices)
        for inst in self._cached_instruments():
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

        # A single delisted/renamed symbol (e.g. after a corporate action
        # like a demerger) must not take down the whole websocket feed —
        # skip it and keep streaming everything that did resolve.
        tokens = {}
        for sym in symbols:
            try:
                tokens[self.get_instrument_token(sym, exchange)] = sym
            except ValueError as exc:
                logging.warning("%s — skipping, not subscribed", exc)

        if not tokens:
            raise ValueError("❌ No symbols resolved to a valid instrument token")

        # dict that stores the latest tick for each symbol
        self.market_data = {}

        def on_ticks(ws, ticks):
            #print("Ticks received:", ticks)
            for tick in ticks:
                token = tick["instrument_token"]
                symbol = tokens.get(token, str(token))  # map token back to symbol
                ltp = tick['last_price']
                ohlc = tick.get('ohlc', {})
                open_price = ohlc.get('open')
                high_price = ohlc.get('high')
                low_price = ohlc.get('low')
                close_price = ohlc.get('close')
                volume = tick.get('volume_traded', 0)

                # store in dict
                self.market_data[symbol] = {
                    "Token": token,
                    "LTP": ltp,
                    "O": open_price,
                    "H": high_price,
                    "L": low_price,
                    "C": close_price,
                    "Volume": volume
                }

            # optional: print only updated row
            #print(f"{symbol}: {self.market_data[symbol]}")

        def on_connect(ws, response):
            logging.info("Connected. Subscribing...")
            print("Subscribed tokens:", tokens)
            ws.subscribe(list(tokens.keys()))
            ws.set_mode(ws.MODE_FULL, list(tokens.keys()))

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
    # quote = client.get_live_quote("INFY")
    # print("Live Quote:", quote)
    # client.start_live_data(["INFY", "TCS"])


#######################################################################
'''# Call indicators with default parameters
print("RSI:", ind.rsi(df).to_list())  # Default period=14 → You can change it by passing period=21, period=7, etc.
print("MACD:", ind.macd(df))  # Default fast=12, slow=26, signal=9 → Override with macd(df, fast=8, slow=21, signal=5)
print("Bollinger Bands:", ind.bollinger_bands(df))  # Default period=20, std=2 → Override with bollinger_bands(df, period=14, std=2.5)
print("VWAP:", ind.vwap(df).to_list())  # VWAP is cumulative → No main parameter, but you must ensure df has 'volume'
print("ADX:", ind.adx(df).to_list())  # Default period=14 → Override with adx(df, period=10)
print("EMV:", ind.emv(df).to_list())  # Default period=14 → Override with emv(df, period=20)

# Override parameters easily
print("Custom RSI:", ind.rsi(df, period=21).to_list())  # Example: RSI with 21-period instead of 14
print("Custom MACD:", ind.macd(df, fast=8, slow=21, signal=5))  # Example: Faster MACD settings
print("Custom Bollinger Bands:", ind.bollinger_bands(df, period=14, std=2.5))  # Example: Narrower period, higher deviation
print("Custom ADX:", ind.adx(df, period=10).to_list())  # Example: Shorter ADX period
print("Custom EMV:", ind.emv(df, period=20).to_list())  # Example: Longer EMV period'''
##########################################################################################################