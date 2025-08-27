import logging

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

    def fetch_all_live_quotes(self, stocks):
        results = {}
        for stock in stocks:
            try:
                data = self.client.get_live_quote(stock, self.config["settings"]["exchange"])
                results[stock] = data
            except Exception as e:
                logging.error(f"Error fetching live for {stock}: {e}")
        return results
