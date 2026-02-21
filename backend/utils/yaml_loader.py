import yaml
import os

def load_strategy_yaml(strategy_name):
    path = f"config/strategies/{strategy_name.lower()}.yaml"
    if not os.path.exists(path):
        raise FileNotFoundError(f"YAML for {strategy_name} not found")

    with open(path, "r") as f:
        return yaml.safe_load(f)