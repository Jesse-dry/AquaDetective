"""拓扑溯源引擎测试（用真实流域构建）。"""
from app.data.watershed_builder import build_watershed
from app.engine.topology import build_graph, impact_matrix, upstream_nodes


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
