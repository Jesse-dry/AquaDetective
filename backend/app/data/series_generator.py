"""时序数据生成：正常基线（季节+昼夜+噪声）+ 企业排放贡献 + 事件注入。

全部确定性：同 seed 结果一致。事件注入后直接更新 readings 表。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np

from ..engine.dispersion import puff_at
from ..engine.topology import impact_matrix

T0 = int(datetime(2025, 1, 1).timestamp())

IND_BASE = {"cod": 18.0, "ammonia": 0.7, "tp": 0.12, "cr6": 0.003, "ph": 7.3}
IND_CV = {"cod": 0.08, "ammonia": 0.10, "tp": 0.12, "cr6": 0.15, "ph": 0.004}
DIURNAL_PHASE = {"cod": 10, "ammonia": 8, "tp": 9, "cr6": None, "ph": 6}
SEASONAL_AMP = {"cod": 0.12, "ammonia": 0.12, "tp": 0.12, "cr6": 0.0, "ph": 0.01}
SEVERITY_MULT = {"low": 1.5, "medium": 2.0, "high": 2.5}
# 突发泄漏演示标定：高斯烟团在窄河道中峰高极高（数千 mg/L 级），
# 演示采用"峰形物理 + 峰高标定"：增量 = 归一化烟团形状 × 原水浓度 × 标定系数 × √(质量/80kg)。
SUDDEN_SCALE = 1.0 / 12.0
# 偷排事件的偷排流量倍数（偷排时废水流量远大于正常）
DUMP_FLOW_MULT = 6.0

_PROFILES = json.loads((Path(__file__).parent / "industry_profiles.json").read_text(encoding="utf-8"))


def outfall_conc(ent: dict, indicator: str) -> float:
    return float(_PROFILES[ent["industry"]]["outfall_conc"].get(indicator, 0.0))


def _wrap_mask(hour: np.ndarray, start: float, end: float) -> np.ndarray:
    if start <= end:
        return (hour >= start) & (hour < end)
    return (hour >= start) | (hour < end)


def activity_series(ent: dict, t_min: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """企业排放活动度：连续/时段型 × 周末 × 季节 × 噪声。event_only 企业平时不排。"""
    pat = ent["discharge_pattern"]
    if pat.get("event_only"):
        return np.zeros(len(t_min))
    hour = (t_min / 60.0) % 24
    day = t_min // 1440
    doy = (day + 1) % 365
    if pat["continuous"]:
        a = 0.9 + 0.1 * np.sin(2 * np.pi * (hour - 9) / 24)
    else:
        a = np.where(_wrap_mask(hour, pat["active_hours"][0], pat["active_hours"][1]), 1.0, 0.0)
    nb = pat.get("night_boost", 1.0)
    if nb > 1.0:
        win = pat.get("night_window", [22, 3])
        a = a * np.where(_wrap_mask(hour, win[0], win[1]), nb, 1.0)
    dow = (day + 3) % 7  # 2025-01-01 是周三
    a = np.where(dow >= 5, a * pat.get("weekend_scale", 1.0), a)
    a = a * (1 + pat.get("seasonal_amp", 0.2) * np.sin(2 * np.pi * (doy - 60) / 365))
    a = a * (1 + 0.05 * rng.normal(size=len(t_min)))
    return np.clip(a, 0.0, 1.8)


def baseline_series(indicator: str, t_min: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    day = t_min // 1440
    doy = (day + 1) % 365
    hour = (t_min / 60.0) % 24
    base = IND_BASE[indicator]
    seasonal = 1 + SEASONAL_AMP[indicator] * np.sin(2 * np.pi * (doy - 60) / 365)
    phase = DIURNAL_PHASE[indicator]
    diurnal = 1.0 if phase is None else 1 + 0.04 * np.sin(2 * np.pi * (hour - phase) / 24)
    x = base * seasonal * diurnal
    x = x + rng.normal(0, IND_CV[indicator] * base, size=len(t_min))
    if indicator == "ph":
        return np.clip(x, 6.5, 8.0)
    return np.clip(x, 0.001, None)


def station_series(watershed: dict, station: dict, indicator: str, t_min: np.ndarray,
                   rng: np.random.Generator, atten: dict) -> np.ndarray:
    x = baseline_series(indicator, t_min, rng)
    for ent in watershed["enterprises"]:
        fac = atten.get((ent["id"], station["id"]))
        if not fac:
            continue
        conc = outfall_conc(ent, indicator)
        if conc == 0.0:
            continue
        act = activity_series(ent, t_min, rng)
        x = x + act * conc * ent["discharge_pattern"].get("treat_rate", 1.0) * fac
    return x


def generate_all(conn, watershed: dict, seed: int = 0, days: int = 90,
                 interval_min: int = 15) -> int:
    """生成全部断面时序并写入 readings，返回写入行数。"""
    rng = np.random.default_rng(seed)
    n = days * 1440 // interval_min
    t_min = np.arange(n) * interval_min
    ts = T0 + (t_min.astype(np.int64) * 60)
    atten = impact_matrix(watershed)
    total = 0
    for st in watershed["stations"]:
        for ind in st["indicators"]:
            x = station_series(watershed, st, ind, t_min, rng, atten)
            rows = [(st["id"], int(t), ind, round(float(v), 3)) for t, v in zip(ts, x)]
            conn.executemany("INSERT OR REPLACE INTO readings VALUES (?,?,?,?)", rows)
            conn.commit()
            total += len(rows)
    return total


def apply_event(conn, watershed: dict, spec: dict, t_min: np.ndarray,
                rng: np.random.Generator, interval_min: int = 15) -> list[dict]:
    """运行时/seed 注入污染事件（确定性），更新 readings 并返回影响摘要。

    spec: {etype: sudden|periodic|gradual, source_id, severity, onset_day,
           duration_d, mass_kg?(sudden)}
    """
    ent = next(e for e in watershed["enterprises"] if e["id"] == spec["source_id"])
    src_node = ent["node_id"]
    atten = impact_matrix(watershed)
    mult = SEVERITY_MULT[spec["severity"]]
    start = spec["onset_day"] * 1440 // interval_min
    dur = spec["duration_d"] * 1440 // interval_min
    idx = np.arange(start, min(start + dur, len(t_min)))
    t_h = idx * interval_min / 60.0 - spec["onset_day"] * 24.0
    if spec["etype"] == "sudden":
        t_h = np.maximum(t_h, 0.0)
    q_dump = ent["discharge_pattern"].get("q_waste", 0.01) * DUMP_FLOW_MULT
    summary = []
    for st in watershed["stations"]:
        fac = atten.get((ent["id"], st["id"]))
        if not fac:
            continue
        q_st = next(n["flow"] for n in watershed["nodes"] if n["id"] == st["node_id"])
        for ind in st["indicators"]:
            conc = outfall_conc(ent, ind)
            if conc == 0.0:
                continue
            if spec["etype"] == "sudden":
                c = puff_at(watershed, src_node, st["node_id"], spec["mass_kg"], t_h)
                peak = float(np.max(c)) if len(c) else 0.0
                if peak > 1e-9:
                    shape = c / peak
                    mag = (spec["mass_kg"] / 80.0) ** 0.5
                    delta = shape * conc * SUDDEN_SCALE * mag
                else:
                    delta = np.zeros_like(c)
            elif spec["etype"] == "periodic":
                # 偷排软阶跃:夜间窗口内用 2.5h 上升沿替代方波开关,
                # 回放时断面颜色能看出渐变(方波会让圈圈瞬间跳红)
                hour = (t_min[idx] / 60.0) % 24
                night = _wrap_mask(hour, 22, 3).astype(float)
                rise = np.clip(t_h / 2.5, 0.0, 1.0)
                dil_dump = q_dump / (q_dump + q_st)
                delta = night * rise * mult * conc * dil_dump
            else:  # gradual
                ramp = np.linspace(0.0, 1.5 * (mult - 1.0), len(idx))
                delta = ramp * conc * fac
            if np.max(np.abs(delta)) < 1e-9:
                continue
            upd = [(round(float(d), 3), st["id"], ind, int(t_min[ix] * 60 + T0))
                   for ix, d in zip(idx, delta)]
            conn.executemany(
                "UPDATE readings SET value = value + ? "
                "WHERE station_id=? AND indicator=? AND ts=?", upd)
            summary.append({"station_id": st["id"], "indicator": ind,
                            "peak_delta": round(float(np.max(delta)), 3)})
        conn.commit()
    return summary


def alert_station_for(watershed: dict, source_id: str) -> str | None:
    """事件最先触达的断面（衰减系数最大者）。"""
    atten = impact_matrix(watershed)
    best, best_fac = None, 0.0
    for st in watershed["stations"]:
        fac = atten.get((source_id, st["id"]), 0.0)
        if fac > best_fac:
            best, best_fac = st["id"], fac
    return best
