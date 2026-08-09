# core/domain/strategy_conditions.py
"""Parses and evaluates a strategy's conditions.json (see strategies/
vwap_reclaim.json for the canonical example) — the data-driven replacement
for hand-writing screen()'s boolean logic in every strategy file. A
strategy loads one ConditionSet once (in __init__) and calls evaluate()
per symbol per tick; this is what makes an indicator threshold (or the
comparison operator itself) an editable, trackable value instead of a
buried Python constant.

Schema:
    {
      "parameters": {"adx_threshold": 25, ...},
      "conditions": [
        {"left": "adx", "op": ">=", "right": {"param": "adx_threshold"}},
        {"left": "ema9", "op": ">", "right": {"field": "ema21"}},
        {"left": "ltp", "op": "crossed_above", "right": {"field": "vwap"}},
        {"left": {"indicator": "ema", "params": {"period": 20}}, "op": ">", "right": {"field": "ema9"}}
      ]
    }

`right` is exactly one of `field` (another live indicator in the
snapshot), `param` (a named value from `parameters`, above), or `value`
(a raw literal). Every condition must hold (AND) for evaluate() to return
True — no strategy today needs OR/grouping, so that's not supported yet.

`left` (and `right.field`) can ALSO be a structured indicator reference
— {"indicator": "ema", "params": {"period": 20}} — instead of a bare
field name, for any period/indicator registered in
core/domain/indicator_registry.py, not just the fixed always-computed
set below. This is purely additive: existing bare-string references
(the only form every strategy uses today) keep meaning exactly what they
always have. required_indicators() reports which of these a ConditionSet
needs so the pipeline (runners/backtesting/snapshot_builder.py,
runners/paper_trading/live_engine.py) knows what extra to compute —
resolved to the SAME canonical key (IndicatorSpec.key, e.g. "ema_20")
that evaluate() looks up in the snapshot dict, so there's exactly one
naming scheme shared by both sides.

crossed_above/crossed_below need a previous tick on record for that
(symbol, condition) pair to fire at all — same "skip until we've seen one
prior tick" behavior every hand-written crossing check had before this
existed. The default crossing boundary is the standard technical-analysis
definition — previous <=/>= (not yet moved to the other side), this tick
strictly on the other side: `previous_left <= previous_right and left >
right` for crossed_above. Set `"inclusive": true` on a condition to flip
which side of the boundary is strict — `previous_left < previous_right
and left >= right` instead — matching a hand-written check that required
strictly-below on the prior tick but accepted at-or-above on this one
(this is a real distinction: vwap_reclaim's original crossing check used
this convention, and on real price data left == right happens often
enough to change actual trade counts — confirmed by direct comparison
against the pre-refactor code, not a hypothetical edge case).

Every field ANY condition references must be present (non-None) before a
symbol is considered at all AND before any crossing state is updated for
it — matches the original strategies' single upfront
`if None in (...): continue` guard exactly, including that state is
never advanced on a symbol that fails the check.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from core.domain.indicator_registry import IndicatorSpec, available_indicator_types

_COMPARATORS = {
    ">": lambda l, r: l > r,
    ">=": lambda l, r: l >= r,
    "<": lambda l, r: l < r,
    "<=": lambda l, r: l <= r,
    "==": lambda l, r: l == r,
}
_CROSSING_OPS = {"crossed_above", "crossed_below"}
_VALID_OPS = set(_COMPARATORS) | _CROSSING_OPS

# Every field a strategy's screen() actually receives — exactly
# LiveEngine.get_snapshot()'s per-symbol shape, also what
# runners/backtesting/engine.py forwards from its precomputed series (see
# that module's _STRATEGY_SNAPSHOT_KEYS, which imports this same tuple so
# the two can never drift apart). A condition referencing anything outside
# this set (e.g. "ema22" — only 5/9/21-period EMAs are actually computed
# anywhere) would otherwise fail silently: the field always resolves to
# None, which reads as "still warming up" and the condition just never
# fires — no error, no trades, ever. Validating against this list at
# save/load time turns that into an immediate, clear rejection instead.
# Changing what's IN this list (adding a new period, a new indicator) is
# a bigger change than this file scopes to — see core/domain/
# strategy_conditions.py's module docstring / the Phase 1 vs Phase 2 split.
VALID_SNAPSHOT_FIELDS = (
    "ltp", "ema5", "ema9", "ema21", "rsi", "adx", "atr_pct",
    "vwap", "volume_ratio", "orb_low", "orb_high", "distance_to_or_low",
)


def _parse_field_ref(value) -> Tuple[str, Optional[IndicatorSpec]]:
    """Resolves a `left`/`right.field` value to (canonical_snapshot_key,
    indicator_spec). A bare string must be one of the always-computed
    VALID_SNAPSHOT_FIELDS; a {"indicator": ..., "params": {...}} dict must
    name a type registered in core/domain/indicator_registry.py — its
    canonical key (e.g. "ema_20") becomes the snapshot lookup key,
    identically to how a bare field name already works."""
    if isinstance(value, str):
        if value not in VALID_SNAPSHOT_FIELDS:
            raise ValueError(
                f"{value!r} isn't a computed indicator. Available: {', '.join(VALID_SNAPSHOT_FIELDS)}"
            )
        return value, None
    if isinstance(value, dict) and "indicator" in value:
        spec = IndicatorSpec.of(value["indicator"], **value.get("params", {}))
        if spec.type not in available_indicator_types():
            raise ValueError(
                f"Unknown indicator type: {spec.type!r}. Available: {', '.join(available_indicator_types())}"
            )
        return spec.key, spec
    raise ValueError(f"Invalid field reference: {value!r}")


@dataclass(frozen=True)
class Condition:
    left: str  # canonical snapshot key — a bare field, or an IndicatorSpec.key
    op: str
    right_field: Optional[str] = None  # canonical key, same rule as `left`
    right_param: Optional[str] = None
    right_value: Optional[float] = None
    # Only meaningful for crossed_above/crossed_below — see module
    # docstring for exactly which strictness this flips.
    inclusive: bool = False
    # Set only when left/right_field came from a structured indicator
    # reference rather than a bare field name — what required_indicators()
    # collects, unrelated to evaluate()'s logic (which only ever looks at
    # the canonical key above, identically either way).
    left_indicator: Optional[IndicatorSpec] = None
    right_indicator: Optional[IndicatorSpec] = None


class ConditionSet:
    def __init__(self, parameters: Dict[str, float], conditions: List[Condition]):
        self.parameters = parameters
        self.conditions = conditions
        self._required_fields = self._collect_required_fields(conditions)
        self._required_indicators = self._collect_required_indicators(conditions)
        # (symbol, condition_index) -> (previous_left, previous_right),
        # only for crossing conditions.
        self._previous: Dict[Tuple[str, int], Tuple[float, float]] = {}

    @staticmethod
    def _collect_required_fields(conditions: List[Condition]) -> set:
        fields = set()
        for c in conditions:
            fields.add(c.left)
            if c.right_field is not None:
                fields.add(c.right_field)
        return fields

    @staticmethod
    def _collect_required_indicators(conditions: List[Condition]) -> List[IndicatorSpec]:
        specs = []
        for c in conditions:
            if c.left_indicator is not None:
                specs.append(c.left_indicator)
            if c.right_indicator is not None:
                specs.append(c.right_indicator)
        return specs

    def required_indicators(self) -> List[IndicatorSpec]:
        """Every dynamically-computed indicator (anything beyond the
        always-available VALID_SNAPSHOT_FIELDS) this ConditionSet needs —
        what the pipeline (snapshot_builder.py/live_engine.py) must
        additionally compute before evaluate() can see a real value
        instead of a permanent None."""
        return list(self._required_indicators)

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "ConditionSet":
        with open(path) as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def from_dict(cls, data: dict) -> "ConditionSet":
        parameters = data.get("parameters", {})
        conditions = []
        for c in data["conditions"]:
            if c["op"] not in _VALID_OPS:
                raise ValueError(f"Unknown condition operator: {c['op']!r}")

            left_key, left_indicator = _parse_field_ref(c["left"])

            right = c["right"]
            right_field, right_indicator = (None, None)
            if "field" in right:
                right_field, right_indicator = _parse_field_ref(right["field"])

            right_param = right.get("param")
            if right_param is not None and right_param not in parameters:
                raise ValueError(f"{right_param!r} isn't defined in this file's \"parameters\" block")

            conditions.append(Condition(
                left=left_key,
                op=c["op"],
                right_field=right_field,
                right_param=right_param,
                right_value=right.get("value"),
                inclusive=c.get("inclusive", False),
                left_indicator=left_indicator,
                right_indicator=right_indicator,
            ))
        return cls(parameters, conditions)

    def _resolve_right(self, cond: Condition, snapshot: dict) -> Optional[float]:
        if cond.right_field is not None:
            return snapshot.get(cond.right_field)
        if cond.right_param is not None:
            return self.parameters.get(cond.right_param)
        return cond.right_value

    def evaluate(self, symbol: str, snapshot: dict) -> bool:
        if any(snapshot.get(f) is None for f in self._required_fields):
            return False

        results = []
        for idx, cond in enumerate(self.conditions):
            left = snapshot[cond.left]
            right = self._resolve_right(cond, snapshot)

            if cond.op in _CROSSING_OPS:
                key = (symbol, idx)
                previous = self._previous.get(key)
                self._previous[key] = (left, right)

                if previous is None:
                    results.append(False)
                    continue

                prev_left, prev_right = previous
                if cond.op == "crossed_above":
                    matched = (
                        (prev_left < prev_right and left >= right)
                        if cond.inclusive
                        else (prev_left <= prev_right and left > right)
                    )
                else:
                    matched = (
                        (prev_left > prev_right and left <= right)
                        if cond.inclusive
                        else (prev_left >= prev_right and left < right)
                    )
                results.append(matched)
            else:
                results.append(_COMPARATORS[cond.op](left, right))

        return all(results)


class StagedConditionSet:
    """Multiple independently-evaluable named stages sharing one
    parameters block — for a funnel-style strategy like orb_reversal,
    whose screening exposes each stage's pass/fail separately (see
    services/filter_engine.py, which also drives the Screener page's live
    display), not just one final AND. Each stage reuses ConditionSet's
    exact evaluation semantics unchanged; only the file's top-level shape
    differs — a "stages" dict of condition lists instead of one flat
    "conditions" list:

        {
          "parameters": {"stage1_rsi_max": 48, ...},
          "stages": {
            "stage1": [{"left": "rsi", "op": "<", "right": {"param": "stage1_rsi_max"}}, ...],
            "stage2": [...]
          }
        }
    """

    def __init__(self, stages: Dict[str, ConditionSet]):
        self.stages = stages

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "StagedConditionSet":
        with open(path) as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def from_dict(cls, data: dict) -> "StagedConditionSet":
        parameters = data.get("parameters", {})
        stages = {
            stage_name: ConditionSet.from_dict({"parameters": parameters, "conditions": conditions})
            for stage_name, conditions in data["stages"].items()
        }
        return cls(stages)

    def evaluate(self, stage_name: str, symbol: str, snapshot: dict) -> bool:
        return self.stages[stage_name].evaluate(symbol, snapshot)

    def required_indicators(self) -> List[IndicatorSpec]:
        specs = []
        for cs in self.stages.values():
            specs.extend(cs.required_indicators())
        return specs


def required_indicators_from_json(raw_json: str) -> List[IndicatorSpec]:
    """Parses a strategy's raw conditions.json text (either the flat
    ConditionSet shape or the staged one) and returns every dynamically-
    computed indicator it declares (core/domain/indicator_registry.py) —
    what the pipeline (runners/backtesting/snapshot_builder.py,
    runners/paper_trading/live_engine.py) needs to additionally compute.
    "" (no conditions.json yet, or a strategy that only uses bare/fixed
    field references) -> []. The one place both the backtest and live
    paths derive this from, so they can never resolve it differently."""
    if not raw_json:
        return []
    data = json.loads(raw_json)
    if "stages" in data:
        return StagedConditionSet.from_dict(data).required_indicators()
    return ConditionSet.from_dict(data).required_indicators()


def validate_conditions_json(data: dict) -> None:
    """Accepts either a flat ConditionSet or a StagedConditionSet shape —
    used where a strategy's conditions.json is validated generically
    (infrastructure/strategies/filesystem_strategy_params_repository.py)
    without knowing in advance which shape a given strategy uses. Raises
    ValueError/KeyError on anything that parses as neither."""
    if "stages" in data:
        StagedConditionSet.from_dict(data)
    else:
        ConditionSet.from_dict(data)
