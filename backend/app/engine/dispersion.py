"""一维对流-扩散：高斯烟团解析解（确定性），用于突发泄漏的浓度动画与源强校核。"""
from __future__ import annotations

import numpy as np

import networkx as nx

from .topology import build_graph

DEFAULT_DISPERSION = 10.0  # m²/s 纵向弥散系数（演示标定值：峰形/到达时刻偏物理，峰高另标定）


def _downstream_paths(watershed: dict, source_node: str) -> dict[str, dict]:
    G = build_graph(watershed)
    out: dict[str, dict] = {source_node: {"distance_m": 100.0, "travel_h": 0.0}}
    for v in G.nodes():
        if v == source_node:
            continue
        try:
            path = nx.shortest_path(G, source_node, v)
        except nx.NetworkXNoPath:
            continue
        d = sum(G.edges[a, b]["distance_m"] for a, b in zip(path, path[1:]))
        hours = sum((G.edges[a, b]["distance_m"] / G.nodes[a]["velocity"]) / 3600
                    for a, b in zip(path, path[1:]))
        out[v] = {"distance_m": d, "travel_h": hours}
    return out


def puff_curve(distance_m: float, velocity: float, area_m2: float, k: float,
               mass_kg: float, t_h: np.ndarray, D: float = DEFAULT_DISPERSION) -> np.ndarray:
    """高斯烟团：c(t) = M/(A·√(4πDt))·exp(-(d-vt)²/(4Dt))·exp(-kt)，单位 mg/L。

    M 单位 kg → mg；A 单位 m²；t 单位 s；D 单位 m²/s。
    """
    t = np.maximum(t_h * 3600.0, 1.0)
    c = (mass_kg * 1e6 / (area_m2 * np.sqrt(4 * np.pi * D * t))
         * np.exp(-((distance_m - velocity * t) ** 2) / (4 * D * t))
         * np.exp(-k * t / 86400.0))
    return np.clip(c, 0.0, None)


def simulate_puff(watershed: dict, source_node: str, mass_kg: float,
                  t_hours: float = 72.0, n: int = 289,
                  D: float = DEFAULT_DISPERSION) -> dict:
    """返回 {node_id: {"t_h": [...], "c_mgl": [...]}}，供前端浓度动画。"""
    G = build_graph(watershed)
    paths = _downstream_paths(watershed, source_node)
    t_h = np.linspace(0.0, t_hours, n)
    out: dict[str, dict] = {}
    for node, info in paths.items():
        v = G.nodes[source_node]["velocity"]
        A = G.nodes[source_node]["flow"] / v
        k = G.nodes[source_node]["k"]
        c = puff_curve(info["distance_m"], v, A, k, mass_kg, t_h, D)
        out[node] = {"t_h": t_h.round(2).tolist(), "c_mgl": c.round(4).tolist()}
    return out


def puff_at(watershed: dict, source_node: str, station_node: str, mass_kg: float,
            t_h: np.ndarray, D: float = DEFAULT_DISPERSION) -> np.ndarray:
    """指定断面在给定时刻的烟团浓度（mg/L）；源点自身给名义距离 100m 的即时信号。"""
    G = build_graph(watershed)
    paths = _downstream_paths(watershed, source_node)
    if station_node not in paths:
        return np.zeros_like(t_h, dtype=float)
    info = paths[station_node]
    v = G.nodes[source_node]["velocity"]
    A = G.nodes[source_node]["flow"] / v
    k = G.nodes[source_node]["k"]
    return puff_curve(info["distance_m"], v, A, k, mass_kg, np.asarray(t_h, dtype=float), D)
