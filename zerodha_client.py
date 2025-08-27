import os
from datetime import datetime
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv()

class ZerodhaClient:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        self.api_secret = os.getenv("API_SECRET")
        self.redirect_url = os.getenv("REDIRECT_URL")
        self.access_token = os.getenv("ACCESS_TOKEN")

        if not self.api_key or not self.api_secret:
            raise ValueError("Please set API_KEY and API_SECRET in .env")

        self.kite = KiteConnect(api_key=self.api_key)

        # If access token not set, generate it
        if not self.access_token:
            self.access_token = self._generate_access_token()
            self._update_env_file("ACCESS_TOKEN", self.access_token)

        self.kite.set_access_token(self.access_token)

    def _generate_access_token(self):
        """Login manually and generate access token (once per day)."""
        print(f"Login here: {self.kite.login_url()}")
        request_token = input("Enter request token from URL: ").strip()
        data = self.kite.generate_session(request_token, api_secret=self.api_secret)
        print(f"Your access token: {data['access_token']}")
        return data["access_token"]

    def _update_env_file(self, key, value):
        """Update or add a key-value pair in the .env file."""
        env_path = ".env"
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()

            with open(env_path, "w") as f:
                found = False
                for line in lines:
                    if line.startswith(f"{key}="):
                        f.write(f"{key}={value}\n")
                        found = True
                    else:
                        f.write(line)
                if not found:
                    f.write(f"{key}={value}\n")
        else:
            with open(env_path, "w") as f:
                f.write(f"{key}={value}\n")

    def get_instrument_token(self, symbol, exchange="NSE"):
        """Fetch instrument token for a given stock symbol."""
        instruments = self.kite.instruments(exchange)
        for inst in instruments:
            if inst["tradingsymbol"] == symbol:
                return inst["instrument_token"]
        raise ValueError(f"Instrument token not found for {symbol}")

    def fetch_historical_data(self, symbol, interval, from_date, to_date, exchange="NSE"):
        """Fetch historical OHLC data for given symbol."""
        token = self.get_instrument_token(symbol, exchange)
        data = self.kite.historical_data(
            instrument_token=token,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
        return data
