"""拓扑溯源：河网图构建、上溯可达性、衰减影响矩阵（确定性）。"""
from __future__ import annotations

import math

import networkx as nx


def build_graph(watershed: dict) -> nx.DiGraph:
    G = nx.DiGraph()
    for nd in watershed["nodes"]:
        G.add_node(nd["id"], flow=nd["flow"], velocity=nd["velocity"], k=nd["k"], kind=nd["kind"])
    for e in watershed["edges"]:
        G.add_edge(e["from_node"], e["to_node"], distance_m=e["distance_m"])
    return G


def _path_travel_hours(G: nx.DiGraph, path: list[str]) -> float:
    hours = 0.0
    for a, b in zip(path, path[1:]):
        d = G.edges[a, b]["distance_m"]
        v = G.nodes[a]["velocity"]
        hours += (d / v) / 3600.0
    return hours


def upstream_nodes(G: nx.DiGraph, node_id: str, t_window_h: float) -> list[dict]:
    """返回 t_window_h 内可能影响 node_id 的全部上游节点（含距离/传播时间，升序）。"""
    out = []
    for u in G.nodes():
        if u == node_id:
            continue
        try:
            path = nx.shortest_path(G, u, node_id)
        except nx.NetworkXNoPath:
            continue
        travel_h = _path_travel_hours(G, path)
        if travel_h <= t_window_h:
            d = sum(G.edges[a, b]["distance_m"] for a, b in zip(path, path[1:]))
            out.append({"node_id": u, "distance_m": d, "travel_h": round(travel_h, 2)})
    return sorted(out, key=lambda r: r["travel_h"])


def downstream_nodes(G: nx.DiGraph, node_id: str) -> list[str]:
    """所有下游节点（含自身），按路径长度升序。"""
    out = []
    for v in G.nodes():
        if v == node_id:
            continue
        try:
            nx.shortest_path(G, node_id, v)
            out.append(v)
        except nx.NetworkXNoPath:
            pass
    return sorted(out, key=lambda v: len(nx.shortest_path(G, node_id, v)))


def impact_matrix(watershed: dict) -> dict[tuple[str, str], float]:
    """(企业 id → 断面 id) 的衰减系数 = 稀释比 × 降解衰减。

    稀释比 = q_waste/(q_waste + Q_断面)（废水与河水保守混合）；
    降解衰减 = exp(-k均值 × 传播时间(天))；同节点只算稀释。
    """
    G = build_graph(watershed)
    mat: dict[tuple[str, str], float] = {}
    for ent in watershed["enterprises"]:
        s = ent["node_id"]
        q = float(ent["discharge_pattern"].get("q_waste", 0.01))
        for st in watershed["stations"]:
            t = st["node_id"]
            try:
                path = nx.shortest_path(G, s, t)
            except nx.NetworkXNoPath:
                continue
            travel_h = _path_travel_hours(G, path)
            ks = [G.nodes[n]["k"] for n in path]
            k_mean = sum(ks) / len(ks)
            q_st = G.nodes[t]["flow"]
            dilution = q / (q + q_st)
            factor = dilution * math.exp(-k_mean * travel_h / 24.0)
            if s == t:
                factor = dilution
            mat[(ent["id"], st["id"])] = round(factor, 8)
    return mat
