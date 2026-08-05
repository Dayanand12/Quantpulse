from core.domain.market_condition import classify_market_condition


def test_classifies_trending_high_volume_above_vwap():
    label = classify_market_condition(ltp=250.0, adx=31.0, vwap=248.0, volume_ratio=2.0)

    assert label == "Trending / High Volume / Above VWAP"


def test_classifies_ranging_normal_volume_below_vwap():
    label = classify_market_condition(ltp=100.0, adx=12.0, vwap=101.0, volume_ratio=0.8)

    assert label == "Ranging / Normal Volume / Below VWAP"


def test_omits_vwap_bias_when_ltp_or_vwap_missing():
    assert classify_market_condition(ltp=None, adx=30.0, vwap=None, volume_ratio=1.0) == (
        "Trending / Normal Volume"
    )


def test_returns_none_when_adx_missing():
    assert classify_market_condition(ltp=100.0, adx=None, vwap=100.0, volume_ratio=1.0) is None


def test_returns_none_when_volume_ratio_missing():
    assert classify_market_condition(ltp=100.0, adx=30.0, vwap=100.0, volume_ratio=None) is None


def test_threshold_boundaries_are_inclusive_of_trending_and_high_volume():
    label = classify_market_condition(ltp=100.0, adx=25.0, vwap=100.0, volume_ratio=1.5)

    assert label == "Trending / High Volume / Above VWAP"
