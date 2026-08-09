import polars as pl
import pytest

from core.domain.indicator_registry import IndicatorSpec, available_indicator_types, compute, compute_all


def make_df(n=60):
    return pl.DataFrame({
        "close": [100.0 + i for i in range(n)],
        "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
    })


def test_available_indicator_types_includes_the_existing_defaults():
    types = available_indicator_types()
    assert set(types) >= {"ema", "rsi", "adx", "atr"}


def test_spec_key_encodes_type_and_params():
    assert IndicatorSpec.of("ema", period=20).key == "ema_20"
    assert IndicatorSpec.of("rsi", period=14).key == "rsi_14"


def test_spec_key_ignores_dict_ordering():
    a = IndicatorSpec.of("ema", period=20)
    b = IndicatorSpec(type="ema", params=(("period", 20),))
    assert a == b
    assert a.key == b.key


def test_compute_names_the_series_by_canonical_key():
    df = make_df()
    series = compute(IndicatorSpec.of("ema", period=20), df)
    assert series.name == "ema_20"
    assert series.len() == df.height


def test_compute_rejects_unknown_indicator_type():
    with pytest.raises(ValueError, match="Unknown indicator type"):
        compute(IndicatorSpec.of("bogus_indicator", period=5), make_df())


def test_compute_all_adds_one_column_per_distinct_spec():
    df = make_df()
    out = compute_all(
        [IndicatorSpec.of("ema", period=20), IndicatorSpec.of("ema", period=9), IndicatorSpec.of("rsi", period=14)],
        df,
    )
    assert {"ema_20", "ema_9", "rsi_14"} <= set(out.columns)


def test_compute_all_deduplicates_identical_specs():
    df = make_df()
    out = compute_all([IndicatorSpec.of("ema", period=20), IndicatorSpec.of("ema", period=20)], df)
    assert out.columns.count("ema_20") == 1


def test_compute_all_with_no_specs_returns_df_unchanged():
    df = make_df()
    out = compute_all([], df)
    assert out.columns == df.columns
