from datetime import datetime

from core.domain.regime_snapshot import build_regime_fields


def _own_bullish_snapshot(**overrides) -> dict:
    base = dict(ltp=250.0, ema9=252.0, ema21=248.0, adx=30.0, vwap=249.0, atr_pct=0.9)
    base.update(overrides)
    return base


def test_own_regime_uses_classify_regime_on_symbol_fields():
    fields = build_regime_fields(_own_bullish_snapshot(), entry_time=None)

    assert fields["regime_trend"] == "Bullish Trend"
    assert fields["regime_volatility"] == "Normal"


def test_own_regime_none_when_a_core_input_is_missing():
    fields = build_regime_fields(_own_bullish_snapshot(adx=None), entry_time=None)

    assert fields["regime_trend"] is None
    assert fields["regime_volatility"] is None


def test_index_trend_derived_from_nifty_prefixed_fields():
    snapshot = _own_bullish_snapshot(
        nifty_ltp=24800.0, nifty_ema9=24750.0, nifty_ema21=24900.0,
        nifty_adx=15.0, nifty_vwap=24850.0, nifty_atr_pct=0.4,
    )
    fields = build_regime_fields(snapshot, entry_time=None)

    assert fields["index_trend"] == "Bearish Trend"


def test_index_trend_none_when_nifty_fields_absent():
    fields = build_regime_fields(_own_bullish_snapshot(), entry_time=None)

    assert fields["index_trend"] is None


def test_vix_bucket_thresholds():
    assert build_regime_fields({"vix_ltp": 12.0}, None)["vix_bucket"] == "Low"
    assert build_regime_fields({"vix_ltp": 15.0}, None)["vix_bucket"] == "Medium"
    assert build_regime_fields({"vix_ltp": 20.0}, None)["vix_bucket"] == "High"
    assert build_regime_fields({}, None)["vix_bucket"] is None


def test_session_phase_from_entry_time():
    opening = datetime(2026, 9, 19, 9, 20)
    midday = datetime(2026, 9, 19, 11, 30)
    closing = datetime(2026, 9, 19, 14, 45)

    assert build_regime_fields({}, opening)["session_phase"] == "Opening"
    assert build_regime_fields({}, midday)["session_phase"] == "Mid-day"
    assert build_regime_fields({}, closing)["session_phase"] == "Closing"
    assert build_regime_fields({}, None)["session_phase"] is None
