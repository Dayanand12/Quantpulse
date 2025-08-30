import logging
import datetime as dt
class DataManager:
    def __init__(self, client, config):
        self.client = client
        self.config = config

    def fetch_all_historical(self, stocks):
        results = {}
        for stock in stocks:
            try:
                data = self.client.fetch_historical_data(
                    symbol=stock,
                    interval=self.config["settings"]["interval"],
                    from_date=self.config["settings"]["from_date"],
                    to_date=self.config["settings"]["to_date"],
                    exchange=self.config["settings"]["exchange"]
                )
                results[stock] = data
            except Exception as e:
                logging.error(f"Error fetching {stock}: {e}")
        return results
    

    def fetch_historical_ind(self, stocks):
        """
        Fetches historical data for a list of stocks with a period
        automatically calculated based on the configured candle interval.
        """

        results = {}

        # 1. Define the end date as the current time
        to_date = dt.datetime.now()

        # 2. Get the interval from the configuration
        interval = self.config["settings"]["interval"]

        # 3. Normalize interval string (to avoid mismatches)
        normalized_interval = (
            interval.lower()
            .replace("minutes", "min")
            .replace("minute", "min")
            .replace(" ", "")
            .replace("-", "")
        )

        # 4. Mapping of intervals → number of days of historical data
        time_periods = {
            "1min": 2,      # ~2 days of intraday 1-min candles
            "5min": 14,     # ~2 weeks of intraday
            "15min": 30,    # ~1 month of intraday
            "30min": 60,    # ~2 months of intraday
            "60min": 180,   # ~6 months of hourly
            "1day": 365,    # 1 year of daily
        }

        # 5. Calculate from_date based on interval
        days_to_fetch = time_periods.get(normalized_interval, 30)
        if normalized_interval not in time_periods:
            logging.warning(f"Interval '{interval}' not found. Defaulting to 30 days.")
        from_date = to_date - dt.timedelta(days=days_to_fetch)

        # 6. Fetch data for each stock
        for stock in stocks:
            try:
                data = self.client.fetch_historical_data(
                    symbol=stock,
                    interval=interval,  # keep original string for API
                    from_date=from_date,
                    to_date=to_date,
                    exchange=self.config["settings"]["exchange"]
                )

                if not data or len(data) == 0:
                    logging.warning(f"No data returned for {stock} in interval {interval}")
                else:
                    results[stock] = data

            except Exception as e:
                logging.exception(f"Error fetching data for {stock}: {e}")

        return results


    def fetch_all_live_quotes(self, stocks):
        results = {}
        for stock in stocks:
            try:
                data = self.client.get_live_quote(stock, self.config["settings"]["exchange"])
                results[stock] = data
            except Exception as e:
                logging.error(f"Error fetching live for {stock}: {e}")
        return results
