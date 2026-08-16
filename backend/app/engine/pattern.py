"""排放规律分析：昼夜活跃时段、周期性强度（确定性）。"""
from __future__ import annotations

import numpy as np


def analyze_periodicity(x: np.ndarray, interval_min: int = 15, period_h: int = 24) -> dict:
    """分析序列的日周期性，返回活跃时段等特征，供"偷排时段"佐证。

    返回: {period_h, period_points, autocorr, peak_hour, active_hours,
          night_share, strength}
    """
    period = period_h * 60 // interval_min
    n = len(x)
    if n < 2 * period:
        return {"period_h": period_h, "period_points": period, "autocorr": 0.0,
                "peak_hour": None, "active_hours": [], "night_share": 1.0, "strength": 0.0}
    r = 0.0
    if np.std(x[:-period]) > 1e-12 and np.std(x[period:]) > 1e-12:
        r = float(np.corrcoef(x[:-period], x[period:])[0, 1])
    m = n // period * period
    prof = x[:m].reshape(-1, period).mean(axis=0)
    hour = (np.arange(period) * interval_min) / 60.0
    overall = float(prof.mean())
    sd = float(prof.std())
    thr = overall + max(0.3 * sd, 1e-9)
    active = [round(float(h), 1) for h in hour[prof > thr]]
    peak_hour = float(hour[int(np.argmax(prof))])
    night_idx = (hour >= 22) | (hour < 3)
    night_share = float(prof[night_idx].mean() / max(overall, 1e-9))
    return {
        "period_h": period_h, "period_points": int(period),
        "autocorr": round(max(0.0, r), 3),
        "peak_hour": round(peak_hour, 1),
        "active_hours": active,
        "night_share": round(night_share, 3),
        "strength": round(max(0.0, r), 3),
    }
