"""Test JSON Threshold — deliberately trivial JsonConditionStrategy for
unit tests (tests/unit/test_batch_runner.py). Not a real trading strategy.

Fires whenever ltp >= parameters.threshold — a single bare-field
comparison against a named parameter is enough to exercise
merge_condition_overrides()/run_batch_backtests() without needing real
indicator warm-up data. Delete once no longer needed.
"""

from core.domain.enums import OrderSide
from core.domain.json_condition_strategy import JsonConditionStrategy


class TestJsonThresholdStrategy(JsonConditionStrategy):
    name = "test_json_threshold"
    display_name = "TEST: JSON Threshold"
    side = OrderSide.BUY
