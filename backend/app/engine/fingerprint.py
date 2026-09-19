"""水质指纹匹配：EEM 合成与相似度（确定性）。"""
from __future__ import annotations

import math

import numpy as np

LEX = np.linspace(200, 500, 61)   # 激发波长 nm
LEM = np.linspace(250, 600, 71)   # 发射波长 nm


def synthesize_eem(peaks: list[dict], lex: np.ndarray | None = None,
                   lem: np.ndarray | None = None) -> np.ndarray:
    """由荧光峰参数合成 EEM 矩阵（高斯峰叠加）。"""
    lex = LEX if lex is None else lex
    lem = LEM if lem is None else lem
    LX, LM = np.meshgrid(lex, lem, indexing="ij")
    eem = np.zeros_like(LX, dtype=float)
    for p in peaks:
        g = np.exp(-((LX - p["lex"]) ** 2 + (LM - p["lem"]) ** 2) / (2 * p["sigma"] ** 2))
        eem += p["amp"] * g
    return eem


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def match_eem(query: np.ndarray, library: dict[str, np.ndarray]) -> list[dict]:
    """现场 EEM vs 指纹库。返回 [{enterprise_id, cosine, pearson, score}] 降序。

    score = 0.6×cosine + 0.4×pearson（两者都∈[-1,1]，score 可能为负，取 max(0,·)）。
    """
    q = query.flatten()
    out = []
    for eid, lib in library.items():
        l = lib.flatten()
        out.append({
            "enterprise_id": eid,
            "cosine": round(_cosine(q, l), 4),
            "pearson": round(_pearson(q, l), 4),
            "score": round(max(0.0, 0.6 * _cosine(q, l) + 0.4 * _pearson(q, l)), 4),
        })
    return sorted(out, key=lambda r: r["score"], reverse=True)


def match_pollutants(query_vec: dict, library: dict[str, dict]) -> list[dict]:
    """特征污染物比例向量匹配（分量 min/max 比均值，类似光谱 SI 相似度）。

    低维共享指标下余弦相似度过于钝化（全部 ≈0.99），min/max 比对
    组分差异更敏感：同源 ≈1.0，异源显著下降。返回 [{enterprise_id, score}] 降序。
    """
    keys = sorted(set(query_vec) | {k for lib in library.values() for k in lib})
    out = []
    for eid, lib in library.items():
        sims = []
        for k in keys:
            x, y = query_vec.get(k, 0.0), lib.get(k, 0.0)
            lo, hi = min(x, y), max(x, y)
            sims.append(1.0 if hi < 1e-12 else lo / hi)
        out.append({"enterprise_id": eid,
                    "score": round(sum(sims) / len(sims), 4)})
    return sorted(out, key=lambda r: r["score"], reverse=True)


def vector_from_excess(baseline: dict[str, float],
                       peak: dict[str, float]) -> dict[str, float]:
    """由实测浓度相对事件前基线的增量,构造特征污染物比例向量。

    在线监测站测的是浓度(cod/氨氮/六价铬/总磷),不是 EEM。监测 Agent 自动检出
    的事件没有实验室指纹,只能靠这条通道提供证据 —— 若退回"背景混合"观测,
    各企业得分会挤成一团(实测 EEM 通道前三名 0.973/0.948/0.946),排名等于噪声。
    """
    keys = set(baseline) | set(peak)
    excess = {k: max(0.0, peak.get(k, 0.0) - baseline.get(k, 0.0)) for k in keys}
    # 必须与指纹库同一口径:指纹是 normalize(sqrt(排放浓度))(见 watershed_builder
    # 的"sqrt 压缩主导指标、放大特征污染物差异"),证据若用原始比例就与库不在一个
    # 空间,真凶在污染物通道排 17/18。这是口径对齐,不是调参。
    compressed = {k: math.sqrt(v) for k, v in excess.items()}
    total = sum(compressed.values())
    if total <= 1e-12:
        return {}
    return {k: round(v / total, 6) for k, v in compressed.items() if v > 0}
