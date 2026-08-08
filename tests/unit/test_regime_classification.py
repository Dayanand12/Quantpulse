from core.domain.regime_classification import classify_regime, classify_screens


def test_classify_regime_bullish_trend_strong_normal_vol_is_buy_normal_size():
    result = classify_regime(ltp=110, ema9=105, ema21=100, adx=30, vwap=108, atr_pct=0.8)

    assert result["regime"] == "Bullish Trend"
    assert result["trend_strength"] == "Strong"
    assert result["volatility_state"] == "Normal"
    assert result["decision"] == "BUY NORMAL SIZE"
    assert result["suggested_side"] == "BUY"


def test_classify_regime_bearish_trend_is_sell():
    result = classify_regime(ltp=90, ema9=95, ema21=100, adx=30, vwap=92, atr_pct=0.8)

    assert result["regime"] == "Bearish Trend"
    assert result["decision"].startswith("SELL")
    assert result["suggested_side"] == "SELL"


def test_classify_regime_range_is_no_trade():
    result = classify_regime(ltp=100, ema9=100, ema21=100, adx=10, vwap=100, atr_pct=0.6)

    assert result["regime"] == "Range"
    assert result["decision"] == "NO TRADE"
    assert result["suggested_side"] is None


def test_classify_regime_high_expansion_volatility_forces_no_trade_even_in_a_trend():
    # Strong bullish trend, but volatility is blown out -> sit out rather
    # than chase, regardless of how good the trend itself looks.
    result = classify_regime(ltp=110, ema9=105, ema21=100, adx=30, vwap=108, atr_pct=1.5)

    assert result["regime"] == "Bullish Trend"
    assert result["volatility_state"] == "High Expansion"
    assert result["decision"] == "NO TRADE"
    assert result["suggested_side"] is None


def test_classify_regime_weak_trend_low_score_is_reduced_size():
    # Bullish direction but ADX barely above the Range cutoff -> Weak trend
    # strength, so score lands below the NORMAL SIZE threshold.
    result = classify_regime(ltp=110, ema9=105, ema21=100, adx=19, vwap=108, atr_pct=0.8)

    assert result["decision"] == "BUY REDUCED SIZE"


def test_classify_screens_trending_up_reuses_regime_verdict():
    regime = classify_regime(ltp=110, ema9=105, ema21=100, adx=30, vwap=108, atr_pct=0.8)

    screens = classify_screens(
        regime, ltp=110, vwap=108, rsi=55, volume_ratio=1.0, atr_pct=0.8
    )

    assert "Trending Up" in screens
    assert "Trending Down" not in screens


def test_classify_screens_none_regime_skips_trend_screens_but_keeps_others():
    screens = classify_screens(
        None, ltp=100, vwap=140, rsi=20, volume_ratio=1.0, atr_pct=0.3
    )

    assert "Trending Up" not in screens
    assert "Trending Down" not in screens
    assert "Oversold" in screens


def test_classify_screens_near_vwap():
    screens = classify_screens(
        None, ltp=100.1, vwap=100.0, rsi=None, volume_ratio=None, atr_pct=None
    )

    assert "Near VWAP" in screens


def test_classify_screens_not_near_vwap_when_far_away():
    screens = classify_screens(
        None, ltp=110, vwap=100.0, rsi=None, volume_ratio=None, atr_pct=None
    )

    assert "Near VWAP" not in screens


def test_classify_screens_oversold_threshold():
    below = classify_screens(None, ltp=None, vwap=None, rsi=34, volume_ratio=None, atr_pct=None)
    above = classify_screens(None, ltp=None, vwap=None, rsi=36, volume_ratio=None, atr_pct=None)

    assert "Oversold" in below
    assert "Oversold" not in above


def test_classify_screens_high_volatility_from_either_volume_or_atr():
    from_volume = classify_screens(
        None, ltp=None, vwap=None, rsi=None, volume_ratio=2.0, atr_pct=0.2
    )
    from_atr = classify_screens(
        None, ltp=None, vwap=None, rsi=None, volume_ratio=1.0, atr_pct=1.5
    )
    neither = classify_screens(
        None, ltp=None, vwap=None, rsi=None, volume_ratio=1.0, atr_pct=0.2
    )

    assert "High Volatility" in from_volume
    assert "High Volatility" in from_atr
    assert "High Volatility" not in neither


def test_classify_screens_all_none_inputs_returns_empty_list():
    assert classify_screens(None, ltp=None, vwap=None, rsi=None, volume_ratio=None, atr_pct=None) == []


def test_classify_screens_symbol_can_match_multiple_screens_at_once():
    regime = classify_regime(ltp=110, ema9=105, ema21=100, adx=30, vwap=108, atr_pct=1.0)

    screens = classify_screens(
        regime, ltp=110, vwap=108, rsi=55, volume_ratio=2.0, atr_pct=1.0
    )

    assert "Trending Up" in screens
    assert "High Volatility" in screens
