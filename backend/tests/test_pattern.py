"""排放规律分析测试。"""
import numpy as np

from app.engine.pattern import analyze_periodicity


def test_night_only_pattern():
    rng = np.random.default_rng(0)
    n = 96 * 14
    hours = (np.arange(n) * 15 / 60) % 24
    night = ((hours >= 22) | (hours < 3)).astype(float)
    x = 5 + night * 8 + rng.normal(0, 0.3, n)
    p = analyze_periodicity(x, interval_min=15)
    assert p["night_share"] > 1.5, "夜排占比应显著偏高"
    assert 22 <= p["peak_hour"] <= 24 or 0 <= p["peak_hour"] < 3
    assert p["strength"] > 0.3


def test_flat_series():
    x = np.full(96 * 5, 3.0)
    p = analyze_periodicity(x, interval_min=15)
    assert p["strength"] == 0.0
