import datetime as dt

from core.domain.models import StrategyConfig
from runners.paper_trading.deployment_runner import _is_within_window, _parse_hhmm


def test_parse_hhmm():
    assert _parse_hhmm("09:20") == dt.time(9, 20)
    assert _parse_hhmm("23:59") == dt.time(23, 59)


def test_within_default_window():
    config = StrategyConfig()  # 09:20-11:30

    assert _is_within_window(config, dt.time(9, 20)) is True  # start is inclusive
    assert _is_within_window(config, dt.time(10, 0)) is True
    assert _is_within_window(config, dt.time(11, 30)) is True  # end is inclusive
    assert _is_within_window(config, dt.time(9, 19)) is False
    assert _is_within_window(config, dt.time(11, 31)) is False


def test_within_custom_window_per_deployment():
    morning = StrategyConfig(start_time="09:15", end_time="10:00")
    afternoon = StrategyConfig(start_time="13:00", end_time="15:00")

    assert _is_within_window(morning, dt.time(9, 30)) is True
    assert _is_within_window(morning, dt.time(13, 30)) is False
    assert _is_within_window(afternoon, dt.time(9, 30)) is False
    assert _is_within_window(afternoon, dt.time(13, 30)) is True
