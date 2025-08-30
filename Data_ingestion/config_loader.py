import yaml
import json

symbols = "symbols" #"stocks"
def load_config(config_path="config.yaml"):
    """Load YAML configuration file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def load_stocks(json_path="stocks.json"):
    """Load stock symbols from JSON file."""
    with open(json_path, "r") as f:
        data = json.load(f)
    return data.get("symbols", [])
