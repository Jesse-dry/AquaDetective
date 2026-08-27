"""水质指纹库：EEM 合成、现场指纹观测、相似度匹配（确定性引擎的入口）。"""
from __future__ import annotations

import numpy as np

from ..engine.fingerprint import match_eem, match_pollutants, synthesize_eem
from ..engine.topology import impact_matrix

LEX = np.linspace(200, 500, 61)   # 激发波长 nm
LEM = np.linspace(250, 600, 71)   # 发射波长 nm


def fingerprint_of(watershed: dict, enterprise_id: str) -> dict | None:
    for fp in watershed["fingerprints"]:
        if fp["enterprise_id"] == enterprise_id:
            return fp
    return None


def library_eems(watershed: dict) -> dict[str, np.ndarray]:
    """指纹库 → {enterprise_id: EEM 矩阵}。"""
    return {fp["enterprise_id"]: synthesize_eem(fp["spectrum"]) for fp in watershed["fingerprints"]}


def observed_eem(watershed: dict, station_id: str, seed: int = 0,
                 event_source: str | None = None) -> dict:
    """模拟"案发现场"EEM：上游各企业指纹按 衰减×排放强度 加权混合 + 噪声。

    若 event_source 指定（事件 Ground Truth），该源权重放大 60 倍（现场以其指纹为主导）。
    污水厂出水荧光弱（处理后的腐殖质类信号），其 EEM 贡献乘 0.3。
    返回 {lex, lem, eem(2D list), dominant(权重最大企业)}
    """
    rng = np.random.default_rng(seed)
    station = next(s for s in watershed["stations"] if s["id"] == station_id)
    atten = impact_matrix(watershed)
    weights: dict[str, float] = {}
    fp_by_id = {fp["enterprise_id"]: fp for fp in watershed["fingerprints"]}
    for ent in watershed["enterprises"]:
        fac = atten.get((ent["id"], station["id"]))
        if not fac:
            continue
        # 排放强度近似：指纹污染物向量总和 × 衰减；wwtp 荧光弱
        w = fac * sum(fp_by_id[ent["id"]]["pollutants"].values()) * (0.5 + rng.random())
        if ent["industry"] == "wwtp":
            w *= 0.3
        if event_source and ent["id"] == event_source:
            w *= 60.0
        weights[ent["id"]] = w
    if not weights:
        raise ValueError(f"station {station_id} 上游无企业")
    total = sum(weights.values())
    dom = max(weights, key=weights.get)
    mixed = sum(
        synthesize_eem(fp_by_id[eid]["spectrum"]) * (w / total) for eid, w in weights.items()
    )
    mixed = mixed / mixed.max()  # 归一化
    mixed = mixed + rng.normal(0, 0.03, mixed.shape)  # 观测噪声
    return {
        "lex": LEX.tolist(),
        "lem": LEM.tolist(),
        "eem": np.clip(mixed, 0, None).round(4).tolist(),
        "dominant": dom,
        "weights": {k: round(v / total, 4) for k, v in weights.items()},
    }


def observed_pollutants(watershed: dict, station_id: str, seed: int = 0,
                        event_source: str | None = None) -> dict[str, float]:
    """模拟现场污染物比例观测，供数据生成阶段持久化。

    `event_source` 只能由模拟器传入。调查阶段读取已持久化的观测，不能用来源标签
    重新生成证据。
    """
    rng = np.random.default_rng(seed)
    if event_source:
        fp = fingerprint_of(watershed, event_source)
        if fp is None:
            raise ValueError(f"enterprise {event_source} 无指纹")
        vec = {k: max(0.0, v * (1 + 0.08 * rng.normal()))
               for k, v in fp["pollutants"].items()}
    else:
        atten = impact_matrix(watershed)
        fp_by_id = {fp["enterprise_id"]: fp for fp in watershed["fingerprints"]}
        vec: dict[str, float] = {}
        for ent in watershed["enterprises"]:
            fac = atten.get((ent["id"], station_id))
            if not fac:
                continue
            for key, value in fp_by_id[ent["id"]]["pollutants"].items():
                vec[key] = vec.get(key, 0.0) + value * fac
    total = sum(vec.values())
    if total <= 1e-12:
        raise ValueError(f"station {station_id} 上游无污染物观测")
    return {key: round(value / total, 6) for key, value in vec.items()}


def rank_eem(query_eem: np.ndarray, watershed: dict) -> list[dict]:
    """现场 EEM vs 指纹库，返回按分数降序的企业列表。"""
    return match_eem(query_eem, library_eems(watershed))


# ---------- 真实许可证指纹注入 ----------
# 按行业把真实企业指纹轮转映射到合成流域企业(同名行业,顺序轮换)
_INDUSTRY_TO_REAL: dict[str, list[dict]] | None = None


def _real_by_industry() -> dict[str, list[dict]]:
    """从许可证指纹库按行业分组真实企业指纹。懒加载。"""
    global _INDUSTRY_TO_REAL
    if _INDUSTRY_TO_REAL is not None:
        return _INDUSTRY_TO_REAL
    from .permit_fingerprints import INDUSTRY_MAP, real_fingerprints_by_name
    # 需要 industry 信息,从 outlets_report 的 major pollutant 推断行业不易,
    # 改读 v2 企业表
    import csv
    from pathlib import Path
    ROOT = Path(__file__).resolve().parent.parent.parent.parent
    v2 = ROOT / "data/interim/taihu_enterprises_v1/taihu_basin_enterprises_v2.csv"
    name_ind: dict[str, str] = {}
    if v2.exists():
        for r in csv.DictReader(open(v2, encoding="utf-8")):
            name_ind[r["name"]] = INDUSTRY_MAP.get(r.get("industry_cn", "").strip(), r.get("industry", "").strip())
    real_fp = real_fingerprints_by_name()
    by: dict[str, list[dict]] = {}
    for name, vec in real_fp.items():
        ind = name_ind.get(name, "unknown")
        by.setdefault(ind, []).append({"name": name, "fingerprint": vec})
    _INDUSTRY_TO_REAL = by
    return by


def _injected_pollutant_lib(watershed: dict) -> dict[str, dict[str, float]]:
    """合成流域指纹库 + 真实许可证指纹按行业轮转覆盖。

    对每个合成企业,若其行业有真实指纹样本,按"合成企业索引 % 该行业真实样本数"
    取一个真实向量替换合成向量(确定性,可复现)。无真实样本的行业保留合成向量。
    """
    by_ind = _real_by_industry()
    # 按行业对合成企业编号
    ind_idx: dict[str, int] = {}
    lib: dict[str, dict[str, float]] = {}
    for fp in watershed["fingerprints"]:
        eid = fp["enterprise_id"]
        ent = next((e for e in watershed["enterprises"] if e["id"] == eid), None)
        ind = ent["industry"] if ent else "unknown"
        samples = by_ind.get(ind, [])
        if samples:
            i = ind_idx.get(ind, 0)
            ind_idx[ind] = i + 1
            lib[eid] = samples[i % len(samples)]["fingerprint"]
        else:
            lib[eid] = fp["pollutants"]
    return lib


def rank_pollutants(query_vec: dict, watershed: dict) -> list[dict]:
    """现场污染物向量 vs 指纹库(真实许可证指纹注入后)。

    注入层用真实许可证主要污染物比例向量覆盖合成值;数值计算仍走
    engine.match_pollutants(纯函数 min/max 比相似度)。
    """
    lib = _injected_pollutant_lib(watershed)
    return match_pollutants(query_vec, lib)
