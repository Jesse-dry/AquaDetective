"""异常检测：3σ / CUSUM / EWMA / 季节基线（确定性，纯函数）。"""
from __future__ import annotations

import numpy as np


def _robust_sigma(x: np.ndarray) -> float:
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    # Rounded sensor values can have zero MAD despite a nonzero noise spread.
    sigma = mad * 1.4826
    return max(sigma if sigma > 1e-9 else float(np.std(x)), 1e-9)


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


def _resolution(x: np.ndarray) -> float:
    """推断数据的量化分辨率(最小非零相邻差值);无法推断时返回 0(该项门槛不生效)。"""
    u = np.unique(np.round(x, 6))
    d = np.diff(u)
    d = d[d > 0]
    return float(d.min()) if len(d) else 0.0


def significant(anoms: list[dict], x: np.ndarray, min_rel_rise: float = 0.2,
                min_snr: float = 3.0, min_res_mult: float = 5.0) -> list[dict]:
    """从检出中筛出"值得报警"的:统计显著不等于物理有意义。

    低浓度指标的读数常被量化成少数几档(如 cr6 只有 0.002/0.003/0.004),
    此时稳健标准差退化为 0,CUSUM 的 z 值虚高,会出现"涨了 0.001 mg/L 也判高风险"
    的误报。故要求同时满足两条:
    1. 事件峰值偏离 >= max(min_snr × 基线稳健标准差, min_res_mult × 量化分辨率)
    2. 峰值相对基线涨幅 >= min_rel_rise

    幅度取**触发点之后窗口内的峰值**,而非触发点本身:变点检测报的是变化起始处,
    那一刻幅度还很小,拿它判幅度会把真实污染也一并抑制掉。
    """
    if not anoms:
        return []
    floor = max(min_snr * _robust_sigma(x), min_res_mult * _resolution(x))
    out = []
    for a in anoms:
        i = int(a.get("idx", 0))
        base = float(a["baseline"])
        peak = float(np.max(np.abs(x[i:] - base))) if i < len(x) else 0.0
        if peak >= floor and peak / max(abs(base), 1e-9) >= min_rel_rise:
            out.append(a)
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
    """双侧 CUSUM，返回阈值越过及浓度首次达到基线两倍的触发点。

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
        # A weak crossing must not hide a later concentration doubling.
        doubled = x[i] >= 2 * max(mu, 1e-9) and (i == 0 or x[i - 1] < 2 * max(mu, 1e-9))
        if z[i] > h and (i == 0 or z[i - 1] <= h or doubled):
            triggers.append(i)
    baseline = np.full(len(x), mu)
    # 严重度按触发点的偏离量(以基线稳健标准差为单位)判定。
    # 不能拿 CUSUM 统计量当 z:它是累积量,触发时恒在阈值 h 附近(z/h≈1),
    # 而 _severity 要 |z|>=3 才算 medium —— 结果 medium 永不出现,
    # high 只在浓度翻倍(ratio>=2)时出现,报警门槛实际退化成"翻倍才报"。
    dev_z = (x - mu) / std
    return _pack(x, ts, np.array(triggers), baseline, dev_z)


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
                    k: float = 3.0, min_hist: int = 3) -> list[dict]:
    """与历史同期（前 days 天同一时刻）比较。

    历史同刻样本少于 min_hist 个的位置不参与判定:样本太少时标准差不可靠,
    单个样本更会让 std=0、z 发散到 1e12 量级(实测把 3% 的正常偏离判成高风险)。
    std 取历史样本的稳健尺度,并以"序列自身的高频噪声"与"量化分辨率"兜底:
    前者防止小样本下 MAD 退化为 0(连续型指标如 cod 会因此虚高到 z=200+),
    后者防止量化数据(如 cr6 只有三档)出现同样的问题。
    """
    n = len(x)
    hf = _robust_sigma(np.diff(x)) / np.sqrt(2) if len(x) > 1 else 0.0
    floor = max(_resolution(x), hf)
    baseline = np.zeros(n)
    z = np.zeros(n)
    idx: list[int] = []
    for i in range(n):
        j = i - period
        hist = []
        while j >= 0 and len(hist) < days:
            hist.append(x[j])
            j -= period
        if len(hist) < min_hist:
            # 历史不足:基线取自身,偏离恒为 0,即不判定
            baseline[i] = float(x[i])
            continue
        hist_a = np.asarray(hist, dtype=float)
        base = float(np.mean(hist_a))
        sd = max(_robust_sigma(hist_a), floor, 1e-12)
        baseline[i] = base
        z[i] = (x[i] - base) / sd
        if abs(z[i]) > k:
            idx.append(i)
    return _pack(x, ts, np.array(idx, dtype=int), baseline, z)


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
