"""扩散引擎测试。"""
import numpy as np

from app.engine.dispersion import puff_at, puff_curve, simulate_puff

MINI = {
    "nodes": [
        {"id": "a", "name": "a", "kind": "source", "x": 0, "y": 0, "flow": 10.0,
         "velocity": 0.5, "k": 0.1},
        {"id": "b", "name": "b", "kind": "segment", "x": 5, "y": 0, "flow": 10.0,
         "velocity": 0.5, "k": 0.1},
        {"id": "c", "name": "c", "kind": "outlet", "x": 10, "y": 0, "flow": 10.0,
         "velocity": 0.5, "k": 0.1},
    ],
    "edges": [
        {"from_node": "a", "to_node": "b", "distance_m": 5000.0},
        {"from_node": "b", "to_node": "c", "distance_m": 5000.0},
    ],
    "stations": [], "enterprises": [], "fingerprints": [],
}


def test_puff_nonnegative_and_shape():
    out = simulate_puff(MINI, "a", mass_kg=100.0, t_hours=24, n=97)
    for node, d in out.items():
        c = np.array(d["c_mgl"])
        assert (c >= 0).all()
        assert c.max() > 0


def test_puff_peak_order():
    out = simulate_puff(MINI, "a", mass_kg=100.0, t_hours=24, n=97)
    tb = np.array(out["b"]["t_h"])[np.argmax(out["b"]["c_mgl"])]
    tc = np.array(out["c"]["t_h"])[np.argmax(out["c"]["c_mgl"])]
    assert tb < tc, "近处先到达峰值"


def test_puff_curve_basic():
    t = np.linspace(0.1, 24, 100)
    c = puff_curve(5000.0, 0.5, 20.0, 0.1, 100.0, t)
    assert c.max() > 0 and (c >= 0).all()


def test_puff_at_downstream_only():
    t = np.linspace(0.1, 24, 50)
    c = puff_at(MINI, "a", "c", 100.0, t)
    assert c.max() > 0
    c_src = puff_at(MINI, "a", "a", 100.0, t)  # 源点自身也有信号（名义距离 100m）
    assert c_src.max() > 0
    c_missing = puff_at(MINI, "a", "no_such_node", 100.0, t)
    assert (c_missing == 0).all()
