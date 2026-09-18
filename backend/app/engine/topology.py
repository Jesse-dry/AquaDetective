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


def station_travel_hours(watershed: dict, from_station: str, to_station: str) -> float | None:
    """两断面间的传播时间(小时);无上下游通路返回 None。"""
    G = build_graph(watershed)
    node_of = {s["id"]: s["node_id"] for s in watershed["stations"]}
    a, b = node_of.get(from_station), node_of.get(to_station)
    if a is None or b is None or a == b:
        return None
    try:
        path = nx.shortest_path(G, a, b)
    except nx.NetworkXNoPath:
        return None
    return _path_travel_hours(G, path)


def _station_nodes(watershed: dict) -> dict[str, str | None]:
    return {s["id"]: s.get("node_id") for s in watershed.get("stations") or []}


def _has_network(watershed: dict) -> bool:
    """是否具备可用的河网信息(无节点/无连边时无法判断上下游关系)。"""
    return bool(watershed.get("nodes")) and bool(watershed.get("edges"))


def upstream_most(watershed: dict, station_ids: list[str]) -> str:
    """组内最上游的断面(拓扑最小),作为合并后事件的锚点。

    取"组内没有更上游成员"的断面;并列时按 id 定序,保证结果确定。
    无河网信息或只有一个断面时直接返回该断面。
    """
    if not station_ids:
        raise ValueError("station_ids 为空")
    ordered = sorted(station_ids)
    if len(ordered) == 1 or not _has_network(watershed):
        return ordered[0]
    G = build_graph(watershed)
    node_of = _station_nodes(watershed)

    def n_upstream(sid: str) -> int:
        target = node_of.get(sid)
        return sum(1 for o in ordered
                   if o != sid and _reachable(G, node_of.get(o), target))

    return min(ordered, key=n_upstream)


def _reachable(G: nx.DiGraph, src: str | None, dst: str | None) -> bool:
    if src is None or dst is None or src == dst:
        return False
    return nx.has_path(G, src, dst)


def group_detections(watershed: dict, detections: list[dict],
                     lead_h: float = 2.0, lag_h: float = 3.0) -> list[list[dict]]:
    """把同一次污染在多个断面上的检出合并成组(确定性,并查集)。

    两个检出归为同一次污染,当且仅当两断面在河网上有上下游关系,且下游检出
    时刻落在 [上游 − lead_h, 上游 + 传播时间 + lag_h] 区间内。

    区间下界容差 lead_h:浓度抬升的起始沿会同时出现在各断面(烟团尚未到达时
    浓度已开始爬升),下游不会晚于上游太多;上界 lag_h 覆盖检出延迟(CUSUM
    需数个采样点才越限)。

    同一断面的不同指标异常不在此合并(各自成组),由调用方按断面维度处理;
    无河网信息时不做任何跨断面合并。
    """
    if not detections:
        return []
    if not _has_network(watershed):
        return [[d] for d in detections]
    G = build_graph(watershed)
    node_of = _station_nodes(watershed)
    n = len(detections)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = detections[i], detections[j]
            if a["station_id"] == b["station_id"]:
                continue
            na, nb = node_of.get(a["station_id"]), node_of.get(b["station_id"])
            # 两个方向各试一次:只有真正有上下游关系的那一侧才可能成立
            for up, dn, t_up, t_dn in ((na, nb, a["ts"], b["ts"]),
                                       (nb, na, b["ts"], a["ts"])):
                if not _reachable(G, up, dn):
                    continue
                travel_h = _path_travel_hours(G, nx.shortest_path(G, up, dn))
                dt_h = (t_dn - t_up) / 3600.0
                if -lead_h <= dt_h <= travel_h + lag_h:
                    union(i, j)
                    break

    groups: dict[int, list[dict]] = {}
    for i, d in enumerate(detections):
        groups.setdefault(find(i), []).append(d)
    return [groups[k] for k in sorted(groups)]


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
