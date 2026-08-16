"""异常检测引擎测试（纯函数，固定 seed）。"""
import numpy as np

from app.engine.anomaly import detect, detect_cusum, detect_seasonal, detect_threesigma


def _series(seed=0, n=2000):
    rng = np.random.default_rng(seed)
    return rng.normal(10.0, 0.5, n), np.arange(n) * 900


def test_cusum_detects_step():
    x, ts = _series()
    x[800:] += 2.0  # 阶跃
    out = detect_cusum(x, ts)
    assert out, "应检出异常"
    assert out[0]["idx"] >= 800, "检出点应在阶跃之后"


def test_cusum_ignores_flat():
    x = np.full(1000, 5.0)
    out = detect_cusum(x, np.arange(1000) * 900)
    assert out == [], "平直序列不应误报"


def test_threesigma_detects_spike():
    x, ts = _series()
    x[500] = 25.0
    out = detect_threesigma(x, ts)
    assert any(a["idx"] == 500 for a in out)


def test_seasonal_detects_anomaly():
    rng = np.random.default_rng(1)
    day = np.sin(np.arange(96 * 7) / 96 * 2 * np.pi) * 2 + 10
    x = day + rng.normal(0, 0.2, len(day))
    x[96 * 4 + 10] += 6.0
    out = detect_seasonal(x, np.arange(len(x)) * 900, period=96)
    assert any(a["idx"] == 96 * 4 + 10 for a in out)


def test_detect_dispatch():
    x, ts = _series()
    assert detect(x, ts, "cusum") is not None
    assert detect(x, ts, "ewma") is not None
    try:
        detect(x, ts, "nope")
        assert False
    except ValueError:
        pass
