"""异常检测引擎测试（纯函数，固定 seed）。"""
import numpy as np

from app.engine.anomaly import (detect, detect_cusum, detect_seasonal,
                                detect_threesigma, significant)


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


def test_cusum_quantized_baseline_does_not_explode_when_mad_is_zero():
    baseline = np.array([0.003, 0.003, 0.002, 0.003, 0.003,
                         0.003, 0.004, 0.003, 0.003, 0.003])
    x = np.tile(baseline, 10)
    ts = np.arange(len(x)) * 900
    assert detect_cusum(x, ts) == []
    x[-8:] = 0.03
    out = detect_cusum(x, ts)
    assert any(a["idx"] >= 92 and a["severity"] == "high" for a in out)


def test_cusum_reports_escalation_after_an_earlier_weak_crossing():
    x = np.tile([9.5, 10.5], 50)
    x[30:60] = 10.8
    x[60:] = 30
    out = detect_cusum(x, np.arange(len(x)) * 900)
    assert any(a["severity"] == "low" and a["idx"] < 60 for a in out)
    assert any(a["severity"] == "high" and a["idx"] >= 60 for a in out)


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


def test_significant_rejects_quantized_noise():
    """量化到 3 档的低浓度序列:涨 0.001 mg/L 不应报警(现场误报根因)。"""
    x = np.array([0.003] * 80 + [0.004] * 10 + [0.002] * 10)
    ts = np.arange(len(x)) * 900
    anoms = detect_cusum(x, ts)
    assert anoms, "CUSUM 本身会触发(统计显著)"
    assert significant(anoms, x) == [], "但物理上无意义,应被门槛拦下"


def test_significant_keeps_real_event():
    """真实污染:cr6 从 0.003 涨到 0.5(带传感器噪声),必须保留。"""
    rng = np.random.default_rng(2)
    x = np.concatenate([rng.normal(0.003, 0.0004, 80), rng.normal(0.5, 0.01, 20)])
    anoms = [{"idx": 80, "value": 0.5, "baseline": 0.003, "severity": "high"}]
    assert significant(anoms, x)


def test_significant_keeps_small_relative_rise_on_high_baseline():
    """高基线指标的缓升(cod 18 -> 24,仅 1.3 倍)也应保留:门槛看绝对量级。"""
    rng = np.random.default_rng(3)
    x = np.concatenate([rng.normal(18.0, 0.6, 200), rng.normal(24.0, 0.6, 100)])
    anoms = [{"idx": 200, "value": 24.0, "baseline": 18.0, "severity": "medium"}]
    assert significant(anoms, x)


def test_significant_rejects_tiny_relative_rise():
    """高基线上的微小相对波动(cod 18.0 -> 18.1)应被相对涨幅门槛拦下。"""
    x = np.full(300, 18.0)
    anoms = [{"idx": 150, "value": 18.1, "baseline": 18.0, "severity": "high"}]
    assert significant(anoms, x) == []


def test_significant_judges_by_peak_not_trigger_point():
    """触发点落在上升沿、幅度还很小;须按事件峰值判定,否则真实污染被误抑制。"""
    x = np.concatenate([np.full(50, 0.003), np.linspace(0.003, 10.0, 50)])
    trigger = {"idx": 50, "value": 0.0031, "baseline": 0.003, "severity": "high"}
    assert significant([trigger], x)
