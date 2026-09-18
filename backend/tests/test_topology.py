"""拓扑溯源引擎测试（用真实流域构建）。"""
from app.data.watershed_builder import build_watershed
from app.engine.topology import (build_graph, group_detections, impact_matrix,
                                station_travel_hours, upstream_most, upstream_nodes)


def test_upstream_only():
    ws = build_watershed()
    G = build_graph(ws)
    ups = {u["node_id"] for u in upstream_nodes(G, "m04", t_window_h=48)}
    assert "m03" in ups and "m00" in ups
    assert "m05" not in ups, "下游节点不应出现在上游列表"
    assert "t1_02" in ups, "支流上游应可达"


def test_impact_matrix_keys():
    ws = build_watershed()
    mat = impact_matrix(ws)
    # ent_02 在 m03，st_02 在 m04
    assert ("ent_02", "st_02") in mat
    assert mat[("ent_02", "st_02")] > mat[("ent_02", "st_05")], "越远衰减越大"


def test_downstream_not_upstream():
    ws = build_watershed()
    G = build_graph(ws)
    ups = {u["node_id"] for u in upstream_nodes(G, "t1_02", t_window_h=48)}
    assert "m04" not in ups, "干流节点不在支流上游"


def _ws_for_grouping():
    """两断面链:st_a 在上游(m1) -> m2 -> st_b 在下游(m3)。"""
    return {
        "nodes": [
            {"id": "m1", "kind": "segment", "flow": 1.0, "velocity": 1.0, "k": 0.1},
            {"id": "m2", "kind": "segment", "flow": 1.0, "velocity": 1.0, "k": 0.1},
            {"id": "m3", "kind": "segment", "flow": 1.0, "velocity": 1.0, "k": 0.1},
        ],
        "edges": [
            {"from_node": "m1", "to_node": "m2", "distance_m": 3600.0},
            {"from_node": "m2", "to_node": "m3", "distance_m": 3600.0},
        ],
        "stations": [
            {"id": "st_a", "node_id": "m1", "indicators": ["cr6"]},
            {"id": "st_b", "node_id": "m3", "indicators": ["cr6"]},
        ],
    }


def _det(station, ts, indicator="cr6"):
    return {"station_id": station, "indicator": indicator, "ts": ts,
            "severity": "high", "zscore": 9.0, "value": 1.0, "baseline": 0.1}


def test_group_merges_downstream_detections():
    """同一污染在下游断面的检出应并成一组(下游滞后约 2h)。"""
    ws = _ws_for_grouping()
    t0 = 1_700_000_000
    groups = group_detections(ws, [_det("st_a", t0), _det("st_b", t0 + 2 * 3600)])
    assert len(groups) == 1


def test_group_keeps_unrelated_branches_apart():
    """无上下游关系的断面(不同支流)不应合并。"""
    ws = _ws_for_grouping()
    ws["nodes"].append({"id": "m9", "kind": "segment", "flow": 1.0,
                        "velocity": 1.0, "k": 0.1})
    ws["stations"].append({"id": "st_c", "node_id": "m9", "indicators": ["cr6"]})
    t0 = 1_700_000_000
    groups = group_detections(ws, [_det("st_a", t0), _det("st_c", t0)])
    assert len(groups) == 2


def test_group_leaves_same_station_indicators_apart():
    """同一断面的不同指标不在此合并(跨断面传播关系才是本函数的判据)。"""
    ws = _ws_for_grouping()
    t0 = 1_700_000_000
    groups = group_detections(ws, [_det("st_a", t0, "cr6"), _det("st_a", t0, "cod")])
    assert len(groups) == 2


def test_group_without_network_info_does_not_merge():
    """无河网信息(缺 nodes/edges/node_id)时退化为逐条独立,不误合并。"""
    ws = {"stations": [{"id": "st_01", "indicators": ["cod"]},
                       {"id": "st_02", "indicators": ["cod"]}]}
    t0 = 1_700_000_000
    groups = group_detections(ws, [_det("st_01", t0), _det("st_02", t0)])
    assert len(groups) == 2
    assert upstream_most(ws, ["st_01", "st_02"]) == "st_01"


def test_group_keeps_far_apart_detections_apart():
    """时间上离得太远(远超传播时间)视为两次污染。"""
    ws = _ws_for_grouping()
    t0 = 1_700_000_000
    groups = group_detections(ws, [_det("st_a", t0), _det("st_b", t0 + 20 * 3600)])
    assert len(groups) == 2


def test_upstream_most_picks_topological_min():
    ws = _ws_for_grouping()
    assert upstream_most(ws, ["st_a", "st_b"]) == "st_a"
    assert upstream_most(ws, ["st_b", "st_a"]) == "st_a"


def test_station_travel_hours():
    ws = _ws_for_grouping()
    assert abs(station_travel_hours(ws, "st_a", "st_b") - 2.0) < 1e-6
    assert station_travel_hours(ws, "st_b", "st_a") is None
