import pytest

from core.domain.strategy_conditions import ConditionSet, StagedConditionSet, validate_conditions_json


def test_simple_comparator_against_param():
    cs = ConditionSet.from_dict({
        "parameters": {"adx_threshold": 25},
        "conditions": [{"left": "adx", "op": ">=", "right": {"param": "adx_threshold"}}],
    })
    assert cs.evaluate("SYM", {"adx": 25}) is True
    assert cs.evaluate("SYM", {"adx": 24.9}) is False


def test_simple_comparator_against_field():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": "ema9", "op": ">", "right": {"field": "ema21"}}],
    })
    assert cs.evaluate("SYM", {"ema9": 10, "ema21": 9}) is True
    assert cs.evaluate("SYM", {"ema9": 9, "ema21": 10}) is False


def test_simple_comparator_against_literal_value():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": "rsi", "op": "<", "right": {"value": 48}}],
    })
    assert cs.evaluate("SYM", {"rsi": 40}) is True
    assert cs.evaluate("SYM", {"rsi": 50}) is False


def test_all_conditions_must_hold():
    cs = ConditionSet.from_dict({
        "conditions": [
            {"left": "adx", "op": ">=", "right": {"value": 25}},
            {"left": "volume_ratio", "op": ">=", "right": {"value": 1.5}},
        ],
    })
    assert cs.evaluate("SYM", {"adx": 30, "volume_ratio": 2.0}) is True
    assert cs.evaluate("SYM", {"adx": 30, "volume_ratio": 1.0}) is False


def test_missing_required_field_fails_closed():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": "adx", "op": ">=", "right": {"value": 25}}],
    })
    assert cs.evaluate("SYM", {"adx": None}) is False
    assert cs.evaluate("SYM", {}) is False


def test_crossed_above_does_not_fire_on_first_tick_even_if_already_above():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": "ema5", "op": "crossed_above", "right": {"field": "ema9"}}],
    })
    assert cs.evaluate("SYM", {"ema5": 10, "ema9": 9}) is False


def test_crossed_above_fires_on_the_crossing_tick():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": "ema5", "op": "crossed_above", "right": {"field": "ema9"}}],
    })
    cs.evaluate("SYM", {"ema5": 8, "ema9": 9})  # priming tick, below
    assert cs.evaluate("SYM", {"ema5": 10, "ema9": 9}) is True


def test_crossed_above_does_not_refire_while_already_above():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": "ema5", "op": "crossed_above", "right": {"field": "ema9"}}],
    })
    cs.evaluate("SYM", {"ema5": 8, "ema9": 9})
    cs.evaluate("SYM", {"ema5": 10, "ema9": 9})  # crosses here
    assert cs.evaluate("SYM", {"ema5": 11, "ema9": 9}) is False  # still above, not a new cross


def test_crossed_below_fires_on_the_crossing_tick():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": "rsi", "op": "crossed_below", "right": {"value": 70}}],
    })
    cs.evaluate("SYM", {"rsi": 75})
    assert cs.evaluate("SYM", {"rsi": 65}) is True


def test_default_boundary_strictness_prev_non_strict_current_strict():
    # default (inclusive=False): previous <= right, current > right —
    # a tie on the CURRENT tick does not count as crossed.
    cs = ConditionSet.from_dict({
        "conditions": [{"left": "rsi", "op": "crossed_above", "right": {"value": 100}}],
    })
    cs.evaluate("SYM", {"rsi": 100})  # prev tie counts as "not yet above" (<=)
    assert cs.evaluate("SYM", {"rsi": 100}) is False  # current tie is not strictly above


def test_inclusive_boundary_strictness_prev_strict_current_non_strict():
    # inclusive=True: previous < right, current >= right — a tie on the
    # PREVIOUS tick does not prime it, but a tie on the CURRENT tick fires.
    cs = ConditionSet.from_dict({
        "conditions": [
            {"left": "rsi", "op": "crossed_above", "right": {"value": 100}, "inclusive": True}
        ],
    })
    cs.evaluate("SYM", {"rsi": 100})  # prev tie does NOT prime it (needs strict <)
    assert cs.evaluate("SYM", {"rsi": 100}) is False

    cs2 = ConditionSet.from_dict({
        "conditions": [
            {"left": "rsi", "op": "crossed_above", "right": {"value": 100}, "inclusive": True}
        ],
    })
    cs2.evaluate("SYM", {"rsi": 99})  # strictly below primes it
    assert cs2.evaluate("SYM", {"rsi": 100}) is True  # current tie fires (>=)


def test_symbols_tracked_independently():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": "ema5", "op": "crossed_above", "right": {"field": "ema9"}}],
    })
    cs.evaluate("A", {"ema5": 8, "ema9": 9})
    # B has never been primed — must not fire even though it's "above"
    assert cs.evaluate("B", {"ema5": 10, "ema9": 9}) is False
    assert cs.evaluate("A", {"ema5": 10, "ema9": 9}) is True


def test_unknown_operator_rejected():
    with pytest.raises(ValueError):
        ConditionSet.from_dict({
            "conditions": [{"left": "adx", "op": "~=", "right": {"value": 25}}],
        })


def test_unknown_field_rejected():
    with pytest.raises(ValueError):
        ConditionSet.from_dict({
            "conditions": [{"left": "ema9", "op": ">", "right": {"field": "ema22"}}],
        })


def test_unknown_param_reference_rejected():
    with pytest.raises(ValueError):
        ConditionSet.from_dict({
            "parameters": {"adx_threshold": 25},
            "conditions": [{"left": "adx", "op": ">=", "right": {"param": "typo_threshold"}}],
        })


# --- StagedConditionSet: a funnel of independently-evaluable named
# stages sharing one parameters block (orb_reversal's stage1/2/3) ---

ORB_LIKE = {
    "parameters": {"rsi_max": 48, "volume_ratio_min": 1.7},
    "stages": {
        "stage1": [{"left": "rsi", "op": "<", "right": {"param": "rsi_max"}}],
        "stage2": [{"left": "volume_ratio", "op": ">=", "right": {"param": "volume_ratio_min"}}],
    },
}


def test_staged_evaluates_each_stage_independently():
    scs = StagedConditionSet.from_dict(ORB_LIKE)

    assert scs.evaluate("stage1", "SYM", {"rsi": 40}) is True
    assert scs.evaluate("stage1", "SYM", {"rsi": 50}) is False
    assert scs.evaluate("stage2", "SYM", {"volume_ratio": 2.0}) is True
    assert scs.evaluate("stage2", "SYM", {"volume_ratio": 1.0}) is False


def test_staged_stages_do_not_see_each_others_required_fields():
    scs = StagedConditionSet.from_dict(ORB_LIKE)

    # stage1 only needs rsi — missing volume_ratio (stage2's field) must
    # not affect it.
    assert scs.evaluate("stage1", "SYM", {"rsi": 40, "volume_ratio": None}) is True


def test_staged_shares_one_parameters_block_across_stages():
    scs = StagedConditionSet.from_dict(ORB_LIKE)

    assert scs.stages["stage1"].parameters == scs.stages["stage2"].parameters


def test_validate_conditions_json_accepts_flat_shape():
    validate_conditions_json({"conditions": [{"left": "adx", "op": ">=", "right": {"value": 25}}]})


def test_validate_conditions_json_accepts_staged_shape():
    validate_conditions_json(ORB_LIKE)


def test_validate_conditions_json_rejects_garbage():
    with pytest.raises((KeyError, ValueError)):
        validate_conditions_json({"nonsense": True})


# --- Structured indicator references: {"indicator": "ema", "params":
# {"period": 20}} instead of a bare field name — any period, not just the
# fixed defaults (core/domain/indicator_registry.py) ---

def test_indicator_ref_on_right_resolves_to_canonical_key():
    cs = ConditionSet.from_dict({
        "conditions": [
            {"left": "ema9", "op": ">", "right": {"field": {"indicator": "ema", "params": {"period": 20}}}}
        ],
    })
    # evaluate() looks the value up by the canonical key "ema_20" —
    # exactly what required_indicators() below says the pipeline must
    # compute and hand back under that same key.
    assert cs.evaluate("SYM", {"ema9": 15, "ema_20": 10}) is True
    assert cs.evaluate("SYM", {"ema9": 5, "ema_20": 10}) is False


def test_indicator_ref_on_left_resolves_to_canonical_key():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": {"indicator": "ema", "params": {"period": 20}}, "op": ">", "right": {"field": "ema9"}}],
    })
    assert cs.evaluate("SYM", {"ema9": 10, "ema_20": 15}) is True


def test_required_indicators_reports_dynamic_refs_only():
    cs = ConditionSet.from_dict({
        "conditions": [
            {"left": "adx", "op": ">=", "right": {"value": 25}},  # bare field — not dynamic
            {"left": {"indicator": "ema", "params": {"period": 20}}, "op": ">", "right": {"field": "ema9"}},
        ],
    })
    specs = cs.required_indicators()
    assert len(specs) == 1
    assert specs[0].key == "ema_20"


def test_required_indicators_empty_when_only_bare_fields_used():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": "adx", "op": ">=", "right": {"value": 25}}],
    })
    assert cs.required_indicators() == []


def test_unknown_indicator_type_in_structured_ref_rejected():
    with pytest.raises(ValueError, match="Unknown indicator type"):
        ConditionSet.from_dict({
            "conditions": [{"left": {"indicator": "macd_bogus", "params": {}}, "op": ">", "right": {"value": 0}}],
        })


def test_missing_dynamic_indicator_value_fails_closed_same_as_bare_field():
    cs = ConditionSet.from_dict({
        "conditions": [{"left": {"indicator": "ema", "params": {"period": 20}}, "op": ">", "right": {"value": 100}}],
    })
    # ema_20 not present in the snapshot (pipeline hasn't computed it) ->
    # same fail-closed behavior as a bare field that isn't warmed up yet.
    assert cs.evaluate("SYM", {}) is False


def test_staged_condition_set_required_indicators_spans_all_stages():
    scs = StagedConditionSet.from_dict({
        "stages": {
            "stage1": [{"left": {"indicator": "ema", "params": {"period": 20}}, "op": ">", "right": {"value": 0}}],
            "stage2": [{"left": {"indicator": "rsi", "params": {"period": 9}}, "op": ">", "right": {"value": 0}}],
        },
    })
    keys = {spec.key for spec in scs.required_indicators()}
    assert keys == {"ema_20", "rsi_9"}
