"""流域构建：以真实河流为蓝本的简化河网（主河道 + 3 条支流）。

输出结构（与 db 表一一对应，同时落 JSON 供前端/工具使用）:
{
  "meta": {...},
  "nodes": [{id, name, kind, x, y, flow, velocity, k}],
  "edges": [{from_node, to_node, distance_m}],
  "stations": [{id, node_id, interval_min, indicators}],
  "enterprises": [{id, name, industry, node_id, discharge_pattern}],
  "fingerprints": [{enterprise_id, spectrum, pollutants}]
}
坐标说明：示意坐标（x 沿河流走向，单位 km 网格），后续可整体替换为真实经纬度。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

PROFILES_PATH = Path(__file__).parent / "industry_profiles.json"

MAIN_V = 0.6   # 主河道流速 m/s
TRIB_V = 0.4   # 支流流速 m/s
MAIN_K = 0.15  # 主河道降解系数 1/d
TRIB_K = 0.2

INDICATORS = ["cod", "ammonia", "tp", "cr6", "ph"]

# 企业废水流量（m³/s）与正常处理率（正常排放浓度 = 原水浓度 × 处理率）
Q_WASTE = {"electroplating": 0.01, "dyeing": 0.01, "paper": 0.01, "chemical": 0.01,
           "pharma": 0.01, "food": 0.01, "wwtp": 0.6}
TREAT_RATE = {"electroplating": 0.01, "dyeing": 0.02, "paper": 0.02, "chemical": 0.01,
              "pharma": 0.02, "food": 0.03, "wwtp": 1.0}


def _load_profiles() -> dict:
    with open(PROFILES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _main_stem() -> tuple[list[dict], list[dict]]:
    """主河道 m00..m14，每段 6000m；流量在下游汇合点阶梯增加。"""
    nodes, edges = [], []
    seg_flows = [25] * 4 + [33] * 4 + [45] * 3 + [51] * 4  # 15 个节点流量
    for i in range(15):
        kind = "source" if i == 0 else ("outlet" if i == 14 else "segment")
        nodes.append({
            "id": f"m{i:02d}", "name": f"清源河主河道 {i} 号段",
            "kind": kind, "x": float(i * 6), "y": 0.0,
            "flow": float(seg_flows[i]), "velocity": MAIN_V, "k": MAIN_K,
        })
    for i in range(14):
        edges.append({"from_node": f"m{i:02d}", "to_node": f"m{i+1:02d}", "distance_m": 6000.0})
    return nodes, edges


def _tributary(prefix: str, count: int, join_m: int, flow: float, y: float) -> tuple[list[dict], list[dict]]:
    """支流：count 个节点，末端经 800m 汇入主河道 join_m 节点。"""
    nodes, edges = [], []
    for i in range(count):
        kind = "source" if i == 0 else "segment"
        nodes.append({
            "id": f"{prefix}_{i:02d}", "name": f"{prefix} 支流 {i} 号段",
            "kind": kind, "x": float(join_m * 6 - (count - 1 - i) * 4 - 0.8), "y": y,
            "flow": float(flow), "velocity": TRIB_V, "k": TRIB_K,
        })
    for i in range(count - 1):
        edges.append({"from_node": f"{prefix}_{i:02d}", "to_node": f"{prefix}_{i+1:02d}", "distance_m": 4000.0})
    edges.append({"from_node": f"{prefix}_{count-1:02d}", "to_node": f"m{join_m:02d}", "distance_m": 800.0})
    return nodes, edges


def _stations() -> list[dict]:
    node_ids = ["m02", "m04", "m06", "m08", "m10", "m12", "m14", "t1_02", "t2_03", "t3_01"]
    return [
        {"id": f"st_{i+1:02d}", "node_id": nid, "interval_min": 15, "indicators": list(INDICATORS)}
        for i, nid in enumerate(node_ids)
    ]


_ENTERPRISES = [
    # (id, 名称, 行业, 节点, 排放规律)
    ("ent_01", "华美电镀厂", "electroplating", "t1_01", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=0.6, seasonal_amp=0.3)),
    ("ent_02", "耀光金属表面处理", "electroplating", "m03", dict(continuous=False, active_hours=[22, 3], night_boost=1.0, weekend_scale=0.7, seasonal_amp=0.2, event_only=True)),
    ("ent_03", "蓝海电镀园", "electroplating", "m09", dict(continuous=True, active_hours=[0, 24], night_boost=1.2, weekend_scale=0.8, seasonal_amp=0.2)),
    ("ent_04", "彩云印染厂", "dyeing", "t2_01", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=0.7, seasonal_amp=0.4)),
    ("ent_05", "天虹纺织染整", "dyeing", "m06", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=0.5, seasonal_amp=0.4)),
    ("ent_06", "晨光纸业", "paper", "m01", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=0.8, seasonal_amp=0.3)),
    ("ent_07", "绿洲纸业", "paper", "t3_00", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=0.9, seasonal_amp=0.3)),
    ("ent_08", "东升化工", "chemical", "m05", dict(continuous=True, active_hours=[0, 24], night_boost=1.3, weekend_scale=0.7, seasonal_amp=0.2)),
    ("ent_09", "恒泰精细化工", "chemical", "t2_02", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=0.9, seasonal_amp=0.2)),
    ("ent_10", "新宇制药", "pharma", "m10", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=0.7, seasonal_amp=0.3)),
    ("ent_11", "康达生物制药", "pharma", "t1_03", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=0.8, seasonal_amp=0.3)),
    ("ent_12", "味全食品", "food", "m07", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=0.8, seasonal_amp=0.3)),
    ("ent_13", "绿源食品", "food", "t2_00", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=0.8, seasonal_amp=0.3)),
    ("ent_14", "丰润酿造", "food", "m13", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=1.3, seasonal_amp=0.3)),
    ("ent_15", "城东污水处理厂", "wwtp", "m12", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=1.0, seasonal_amp=0.1)),
    ("ent_16", "城西污水处理厂", "wwtp", "t1_00", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=1.0, seasonal_amp=0.1)),
    ("ent_17", "高新污水处理厂", "wwtp", "t2_04", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=1.0, seasonal_amp=0.1)),
    ("ent_18", "滨江污水处理厂", "wwtp", "m02", dict(continuous=True, active_hours=[0, 24], night_boost=1.0, weekend_scale=1.0, seasonal_amp=0.1)),
]


def _fingerprints(profiles: dict, rng: np.random.Generator) -> list[dict]:
    out = []
    for i, (ent_id, _name, industry, _node, _pat) in enumerate(_ENTERPRISES):
        prof = profiles[industry]
        peaks = []
        for j, p in enumerate(prof["peaks"]):
            # 企业级微扰（确定性）：峰位 ±8nm、峰高 ±15%，模拟"一厂一谱"
            peaks.append({
                "lex": round(p["lex"] + 8 * math.sin(0.9 * i + j), 1),
                "lem": round(p["lem"] + 8 * math.cos(0.7 * i + j), 1),
                "amp": round(p["amp"] * (1 + 0.15 * math.sin(1.7 * i + j)), 3),
                "sigma": p["sigma"],
            })
        # 污染物比例向量：sqrt 压缩主导指标（cod 占绝对大头），放大特征污染物差异，
        # 归一化后作为"特征污染物指纹"（一厂一谱）。
        vec = {k: abs(v) for k, v in prof["outfall_conc"].items() if k != "ph"}
        vec = {k: math.sqrt(v) * (1 + 0.12 * math.sin(1.3 * i + jj))
               for jj, (k, v) in enumerate(vec.items())}
        s = sum(vec.values())
        vec = {k: round(v / s, 4) for k, v in vec.items()}
        out.append({"enterprise_id": ent_id, "spectrum": peaks, "pollutants": vec})
    return out


def build_watershed() -> dict:
    """构建完整流域（确定性，可复现）。"""
    rng = np.random.default_rng(42)
    profiles = _load_profiles()
    nodes, edges = _main_stem()
    for prefix, count, join, flow, y in [("t1", 4, 4, 8.0, 4.0), ("t2", 5, 8, 12.0, -4.0), ("t3", 3, 11, 6.0, 8.0)]:
        tn, te = _tributary(prefix, count, join, flow, y)
        nodes += tn
        edges += te
    enterprises = []
    for eid, name, ind, node, pat in _ENTERPRISES:
        pat = dict(pat)
        pat["q_waste"] = Q_WASTE[ind]
        pat["treat_rate"] = TREAT_RATE[ind]
        enterprises.append({"id": eid, "name": name, "industry": ind, "node_id": node,
                            "discharge_pattern": pat})
    return {
        "meta": {
            "name": "清源河模拟流域",
            "note": "示意坐标（km 网格）；企业/断面为模拟数据，用于演示与算法验证",
            "indicators": INDICATORS,
        },
        "nodes": nodes,
        "edges": edges,
        "stations": _stations(),
        "enterprises": enterprises,
        "fingerprints": _fingerprints(profiles, rng),
    }


def save_watershed(path: str | Path) -> dict:
    ws = build_watershed()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(ws, f, ensure_ascii=False, indent=1)
    return ws


def load_watershed(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    ws = save_watershed(Path(__file__).parent / "watershed_config.json")
    print(f"nodes={len(ws['nodes'])} edges={len(ws['edges'])} "
          f"stations={len(ws['stations'])} enterprises={len(ws['enterprises'])}")
