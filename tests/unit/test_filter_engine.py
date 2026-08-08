from services.filter_engine import stage3_filter


def test_stage3_accepts_the_boundaries():
    assert stage3_filter({"distance_to_or_low": -2.0}) is True
    assert stage3_filter({"distance_to_or_low": 2.0}) is True
    assert stage3_filter({"distance_to_or_low": 0.0}) is True


def test_stage3_rejects_just_outside_the_boundaries():
    assert stage3_filter({"distance_to_or_low": -2.01}) is False
    assert stage3_filter({"distance_to_or_low": 2.01}) is False


def test_stage3_rejects_missing_distance():
    assert stage3_filter({}) is False
    assert stage3_filter({"distance_to_or_low": None}) is False
