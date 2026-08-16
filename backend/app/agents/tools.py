"""Agent 工具层：绑定确定性引擎 + 数据库。

铁律：所有数值（超标判断、相似度、传播时间）来自 engine/数据，LLM 只做推理表达。
"""
from __future__ import annotations

import json

import numpy as np

from ..data.fingerprint_lib import fingerprint_of, observed_eem, rank_eem, rank_pollutants
from ..db import get_conn
from ..engine.dispersion import simulate_puff
from ..engine.pattern import analyze_periodicity
from ..engine.topology import build_graph, impact_matrix

# 静态法规库（RAG 简易版，后续可换成向量检索）
REGULATIONS = [
    {"standard": "GB 3838-2002 地表水环境质量标准", "clause": "Ⅲ类水质限值", "indicator": "cod",
     "limit": 20, "unit": "mg/L", "text": "Ⅲ类水域 COD ≤ 20 mg/L。"},
    {"standard": "GB 3838-2002 地表水环境质量标准", "clause": "Ⅲ类水质限值", "indicator": "ammonia",
     "limit": 1.0, "unit": "mg/L", "text": "Ⅲ类水域氨氮 ≤ 1.0 mg/L。"},
    {"standard": "GB 3838-2002 地表水环境质量标准", "clause": "Ⅲ类水质限值", "indicator": "tp",
     "limit": 0.2, "unit": "mg/L", "text": "Ⅲ类水域总磷 ≤ 0.2 mg/L（河流）。"},
    {"standard": "GB 3838-2002 地表水环境质量标准", "clause": "Ⅲ类水质限值", "indicator": "cr6",
     "limit": 0.05, "unit": "mg/L", "text": "Ⅲ类水域六价铬 ≤ 0.05 mg/L。"},
    {"standard": "GB 3838-2002 地表水环境质量标准", "clause": "Ⅲ类水质限值", "indicator": "ph",
     "limit": "6~9", "unit": "-", "text": "pH 限值 6~9。"},
    {"standard": "中华人民共和国水污染防治法", "clause": "第六十五条", "indicator": "general",
     "limit": "-", "unit": "-", "text": "禁止向水体排放油类、酸液、碱液或者剧毒废液。"},
    {"standard": "中华人民共和国水污染防治法", "clause": "第八十三条", "indicator": "general",
     "limit": "-", "unit": "-", "text": "超过水污染物排放标准排放水污染物的，处十万元以上一百万元以下的罚款；情节严重的，报经有批准权的人民政府批准，责令停业、关闭。"},
    {"standard": "中华人民共和国水污染防治法", "clause": "第八十五条", "indicator": "general",
     "limit": "-", "unit": "-", "text": "利用渗井、渗坑、裂隙、溶洞，私设暗管，篡改、伪造监测数据，或者不正常运行水污染防治设施等逃避监管的方式排放水污染物的，责令改正或者责令限制生产、停产整治，并处十万元以上一百万元以下的罚款；情节严重的，报经有批准权的人民政府批准，责令停业、关闭。"},
]


def parse_indicators(ev: dict) -> list[str]:
    """events.indicators 可能是 JSON 字符串或列表，统一返回列表。"""
    v = ev.get("indicators")
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            v = [v]
    return v or []


def query_station_series(db_path: str, station_id: str, indicator: str,
                         since_ts: int, limit: int = 3000) -> list[dict]:
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT ts, value FROM readings WHERE station_id=? AND indicator=? AND ts>=? "
        "ORDER BY ts LIMIT ?", (station_id, indicator, since_ts, limit)).fetchall()
    conn.close()
    return [{"ts": r["ts"], "value": r["value"]} for r in rows]


def trace_upstream(db_path: str, ws: dict, station_id: str) -> list[dict]:
    """该断面所有上游企业，按衰减系数降序（衰减大 = 影响大）。"""
    atten = impact_matrix(ws)
    out = []
    for ent in ws["enterprises"]:
        fac = atten.get((ent["id"], station_id))
        if not fac:
            continue
        out.append({"enterprise_id": ent["id"], "name": ent["name"],
                    "industry": ent["industry"], "node_id": ent["node_id"],
                    "atten": fac})
    out.sort(key=lambda r: r["atten"], reverse=True)
    return out


def spill_curves(ws: dict, source_node: str, mass_kg: float) -> dict:
    """泄漏扩散曲线（供源强/到达时刻校核与前端动画）。"""
    return simulate_puff(ws, source_node, mass_kg)


def travel_hours(ws: dict, ent_node: str, station_node: str) -> float | None:
    G = build_graph(ws)
    try:
        path = nx_shortest(G, ent_node, station_node)
    except Exception:
        return None
    h = sum((G.edges[a, b]["distance_m"] / G.nodes[a]["velocity"]) / 3600.0
            for a, b in zip(path, path[1:]))
    return round(h, 2)


def nx_shortest(G, s, t):
    import networkx as nx
    return nx.shortest_path(G, s, t)


def observed_eem_at(db_path: str, ws: dict, station_id: str,
                    event_id: str | None = None, seed: int = 7) -> dict:
    """断面"现场"EEM；若事件有 Ground Truth 源，现场以该源指纹为主导。"""
    source = None
    if event_id:
        conn = get_conn(db_path)
        row = conn.execute("SELECT truth_source FROM events WHERE id=?", (event_id,)).fetchone()
        conn.close()
        if row and row["truth_source"]:
            source = row["truth_source"]
    return observed_eem(ws, station_id, seed=seed, event_source=source)


def match_eem_at(db_path: str, ws: dict, station_id: str,
                 event_id: str | None = None) -> list[dict]:
    obs = observed_eem_at(db_path, ws, station_id, event_id)
    q = np.array(obs["eem"])
    return rank_eem(q, ws)


def match_pollutants_at(db_path: str, ws: dict, station_id: str,
                        event_id: str | None = None) -> list[dict]:
    """现场污染物比例向量：以事件源原水比例（微扰）为观测；无事件源则背景混合。"""
    rng = np.random.default_rng(7)
    source = None
    if event_id:
        conn = get_conn(db_path)
        row = conn.execute("SELECT truth_source FROM events WHERE id=?", (event_id,)).fetchone()
        conn.close()
        if row and row["truth_source"]:
            source = row["truth_source"]
    if source:
        fp = fingerprint_of(ws, source)
        vec = {k: v * (1 + 0.08 * rng.normal()) for k, v in fp["pollutants"].items()}
    else:
        atten = impact_matrix(ws)
        fp_by_id = {fp["enterprise_id"]: fp for fp in ws["fingerprints"]}
        vec = {}
        for ent in ws["enterprises"]:
            fac = atten.get((ent["id"], station_id))
            if not fac:
                continue
            for k, v in fp_by_id[ent["id"]]["pollutants"].items():
                vec[k] = vec.get(k, 0.0) + v * fac
    s = sum(vec.values())
    vec = {k: v / s for k, v in vec.items()}
    return rank_pollutants(vec, ws)


def periodicity_at(db_path: str, ws: dict, station_id: str, indicator: str,
                   since_ts: int) -> dict:
    rows = query_station_series(db_path, station_id, indicator, since_ts, limit=2016)
    if len(rows) < 200:
        return {"active_hours": [], "night_share": 1.0, "strength": 0.0, "note": "数据不足"}
    x = np.array([r["value"] for r in rows], dtype=float)
    return analyze_periodicity(x, interval_min=15)


def get_enterprise_profile(ws: dict, ent_id: str) -> dict | None:
    for ent in ws["enterprises"]:
        if ent["id"] == ent_id:
            fp = fingerprint_of(ws, ent_id)
            return {**ent, "fingerprint": fp}
    return None


def search_regulations(keyword: str) -> list[dict]:
    kw = keyword.lower()
    hits = [r for r in REGULATIONS if kw in r["indicator"].lower() or kw in r["standard"].lower()
            or kw in r["clause"].lower() or kw in r["text"].lower()]
    return hits or REGULATIONS
