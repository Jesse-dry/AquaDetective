"""异常检测：3σ / CUSUM / EWMA / 季节基线（确定性，纯函数）。"""
from __future__ import annotations

import numpy as np


def _robust_sigma(x: np.ndarray) -> float:
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    return max(mad * 1.4826, 1e-9)


def _severity(z: float, ratio: float) -> str:
    if abs(z) >= 5.0 or ratio >= 2.0:
        return "high"
    if abs(z) >= 3.0:
        return "medium"
    return "low"


def _pack(x, ts, idx, baseline, z) -> list[dict]:
    out = []
    for i in idx:
        v = float(x[i])
        b = float(baseline[i])
        out.append({
            "idx": int(i), "ts": int(ts[i]), "value": round(v, 4),
            "baseline": round(b, 4), "zscore": round(float(z[i]), 2),
            "severity": _severity(float(z[i]), v / max(b, 1e-9)),
        })
    return out


def _rolling_stats(x: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    w = np.lib.stride_tricks.sliding_window_view(x, window)
    m = w.mean(axis=1)
    s = w.std(axis=1)
    pad = window // 2
    m = np.concatenate([np.full(pad, m[0]), m, np.full(window - 1 - pad, m[-1])])
    s = np.concatenate([np.full(pad, s[0]), s, np.full(window - 1 - pad, s[-1])])
    return m, np.where(s < 1e-12, 1e-12, s)


def detect_threesigma(x: np.ndarray, ts: np.ndarray, window: int = 144, k: float = 3.0) -> list[dict]:
    m, s = _rolling_stats(x, window)
    z = (x - m) / s
    idx = np.where(np.abs(z) > k)[0]
    return _pack(x, ts, idx, m, z)


def detect_cusum(x: np.ndarray, ts: np.ndarray, k: float = 0.5, h: float = 7.0,
                 warmup: float = 0.1) -> list[dict]:
    """双侧 CUSUM，返回每次越过阈值 h 的触发点。

    目标值（mu/std）从前 warmup 比例的数据建立，避免事件本身污染基线。
    h=7σ 为演示标定：约 2000 点噪声窗口内无误报，4σ 阶跃 2 点内触发。
    """
    n_w = max(int(len(x) * warmup), 10)
    mu = float(np.median(x[:n_w]))
    std = _robust_sigma(x[:n_w])
    sp = sn = 0.0
    z = np.zeros(len(x))
    triggers = []
    for i in range(len(x)):
        sp = max(0.0, sp + (x[i] - mu) / std - k)
        sn = max(0.0, sn - (x[i] - mu) / std - k)
        z[i] = max(sp, sn)
        if z[i] > h and (i == 0 or z[i - 1] <= h):
            triggers.append(i)
    baseline = np.full(len(x), mu)
    return _pack(x, ts, np.array(triggers), baseline, z / h)


def detect_ewma(x: np.ndarray, ts: np.ndarray, lam: float = 0.3, k: float = 3.0) -> list[dict]:
    mu = float(np.median(x))
    std = _robust_sigma(x)
    n = len(x)
    ew = np.zeros(n)
    z = np.zeros(n)
    acc = x[0]
    for i in range(n):
        acc = lam * x[i] + (1 - lam) * acc
        ew[i] = acc
        var = std**2 * (lam / (2 - lam)) * (1 - (1 - lam) ** (2 * (i + 1)))
        z[i] = (acc - mu) / max(np.sqrt(var), 1e-12)
    idx = np.where(np.abs(z) > k)[0]
    return _pack(x, ts, idx, np.full(n, mu), z)


def detect_seasonal(x: np.ndarray, ts: np.ndarray, period: int = 96, days: int = 7,
                    k: float = 3.0) -> list[dict]:
    """与历史同期（前 days 天同一时刻）比较。"""
    n = len(x)
    baseline = np.zeros(n)
    std = np.zeros(n)
    for i in range(n):
        j = i - period
        hist = []
        while j >= 0 and len(hist) < days:
            hist.append(x[j])
            j -= period
        if hist:
            baseline[i] = float(np.mean(hist))
            std[i] = max(float(np.std(hist)), 1e-12)
        else:
            baseline[i] = float(x[i])
            std[i] = 1e-12
    z = (x - baseline) / std
    idx = np.where(np.abs(z) > k)[0]
    return _pack(x, ts, idx, baseline, z)


def detect(x: np.ndarray, ts: np.ndarray, method: str = "cusum", **kw) -> list[dict]:
    """统一入口。method: threesigma|cusum|ewma|seasonal"""
    if method == "threesigma":
        return detect_threesigma(x, ts, **kw)
    if method == "cusum":
        return detect_cusum(x, ts, **kw)
    if method == "ewma":
        return detect_ewma(x, ts, **kw)
    if method == "seasonal":
        return detect_seasonal(x, ts, **kw)
    raise ValueError(f"unknown method: {method}")
