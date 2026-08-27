#!/usr/bin/env python3
"""真实数据端到端候选溯源演示:真实断面异常 → 河网上溯 → 筛选候选企业。

链路:
  1. 读取已核验的太湖断面 HydroRIVERS 吸附注册表;
  2. 从 HydroRIVERS NEXT_DOWN 构建有向河网图(下游方向),实现站点河段反向上溯;
  3. 在"有上游吸附企业"的断面中,选异常最显著者,跑 backend 引擎 anomaly.detect_cusum,提取最严重异常窗口;
  4. 从异常断面上溯,在传播时间窗内筛选候选企业,按行业-指标合理性排序。

数值计算只走确定性函数(anomaly 引擎 + networkx 拓扑 + 纯几何吸附),无 LLM。
用法:python tools/realdata_e2e_trace.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.anomaly import detect_cusum

# ---------- 路径 ----------
STATIONS_SNAPPED = ROOT / "data/processed/guokong_taihu/stations_snapped.csv"
READINGS_DIR = ROOT / "data/processed/guokong_taihu/readings"
ENT_SNAPPED = ROOT / "data/processed/taihu_enterprises/enterprises_snapped.csv"
RIVERS_SHP = ROOT / "data/interim/hydrorivers_v10_as/hydrorivers_taihu_bbox.shp"
OUT_DIR = ROOT / "data/processed/guokong_taihu"
FRONTEND_OUT = ROOT / "frontend/public/data/e2e_trace_case.json"

SNAP_LIMIT_M = 2000.0  # 断面吸附阈值(放宽:断面在河口/湖滨,距河网略远合理)
TRAVEL_WINDOW_H = 72.0  # 上溯传播时间窗(小时):3 天内可能影响断面的企业
ASSUMED_V_MS = 0.5  # 小微河流平均流速 m/s(缺断面流速时的保守估计)

INDICATOR_LABELS = {
    "ammonia_n": "氨氮",
    "codmn": "高锰酸盐指数",
    "tp": "总磷",
    "do": "溶解氧",
    "turbidity": "浊度",
    "conductivity": "电导率",
}
INDUSTRY_LABELS = {
    "wwtp": "污水处理厂",
    "dyeing": "印染",
    "electroplating": "电镀",
    "paper": "造纸",
    "chemical": "化工",
    "leather": "皮革",
    "pharmaceutical": "制药",
}

# ---------- 河网有向图 ----------
def build_river_graph(rivers: gpd.GeoDataFrame) -> nx.DiGraph:
    """NEXT_DOWN 指向下游河段;边方向 = 当前河段 → 下游河段(水流方向)。
    上溯 = 在反向图上从断面河段出发的可达前驱。"""
    G = nx.DiGraph()
    river_ids = set(rivers["HYRIV_ID"].astype(int))
    for _, r in rivers.iterrows():
        hid = int(r["HYRIV_ID"])
        G.add_node(
            hid,
            length_km=float(r["LENGTH_KM"]),
            dis_av_cms=float(r["DIS_AV_CMS"]),
            ord_stra=int(r["ORD_STRA"]),
            geom=r["geometry"],
        )
        nd = int(r["NEXT_DOWN"])
        if nd != 0 and nd in river_ids:
            G.add_edge(hid, nd)  # hid 流向 nd
    return G


def group_enterprises_by_reach(enterprises: pd.DataFrame) -> dict[int, list[pd.Series]]:
    """Index every enterprise on a reach without dropping co-located facilities."""
    grouped: dict[int, list[pd.Series]] = {}
    for _, enterprise in enterprises.iterrows():
        if pd.isna(enterprise["hyriv_id"]):
            continue
        grouped.setdefault(int(enterprise["hyriv_id"]), []).append(enterprise)
    return grouped


def upstream_reaches(G: nx.DiGraph, start_hid: int, window_h: float) -> list[dict]:
    """从 start_hid 反向上溯(BFS 沿前驱),返回 {hid, path, dist_km, travel_h} 升序。
    传播时间用 LENGTH_KM / 估算流速(DIS_AV_CMS 折算)。"""
    RG = G.reverse(copy=False)
    out = []
    for pred in nx.nodes(RG):
        if pred == start_hid:
            continue
        try:
            path = nx.shortest_path(RG, start_hid, pred)  # start_hid → ... → pred(上溯方向)
        except nx.NetworkXNoPath:
            continue
        # path 在反图中从 start 出发到 pred;对应正图即 pred → ... → start_hid(水流到断面)
        dist_km = 0.0
        travel_h = 0.0
        for hid in path:  # 含起点河段自身的长度不计入上游距离;只累加上游河段
            nd = G.nodes[hid]
            length = nd["length_km"]
            q = nd["dis_av_cms"]
            # 流速估计:Q 越大流速越大,保底下限 0.3 m/s
            v_ms = max(0.3, min(2.0, 0.3 + 0.4 * math.log1p(max(q, 0.1))))
            v_kmh = v_ms * 3.6
            if hid != start_hid:
                dist_km += length
                travel_h += length / max(v_kmh, 0.1)
        if travel_h <= window_h:
            out.append({
                "hid": pred,
                "path_len": len(path),
                "dist_km": round(dist_km, 2),
                "travel_h": round(travel_h, 2),
            })
    return sorted(out, key=lambda r: r["travel_h"])


def travel_time_metadata(estimate_h: float) -> dict:
    """Represent heuristic travel time without presenting it as causal evidence."""
    upper_h = min(TRAVEL_WINDOW_H, max(24.0, estimate_h * 2))
    return {
        "estimate_h": round(float(estimate_h), 2),
        "range_h": [round(float(estimate_h), 2), round(float(upper_h), 2)],
        "method": "HydroRIVERS reach length / estimated velocity",
        "causal_evidence": False,
    }


def build_frontend_case(result: dict, readings: pd.DataFrame) -> dict:
    """Build the frontend projection from the canonical trace result."""
    anomaly = result["anomaly"]
    candidate = result["primary_candidate"]
    event_ts = int(anomaly["event_ts"])
    indicator = anomaly["indicator"]
    values = pd.to_numeric(readings[indicator], errors="coerce")
    window = readings[
        readings["epoch"].between(event_ts - 9 * 86400, event_ts + 5 * 86400)
        & values.notna()
    ].copy()
    window["value"] = values.loc[window.index]
    series = [
        {
            "dt": pd.Timestamp(row["ts"]).strftime("%m-%d %H:%M"),
            "v": round(float(row["value"]), 4),
            "cls": "" if pd.isna(row.get("quality_class")) else str(row["quality_class"]),
        }
        for _, row in window.iterrows()
    ]

    before = window[window["epoch"] < event_ts]
    baseline_class = ""
    if not before.empty and "quality_class" in before:
        classes = before["quality_class"].dropna().astype(str)
        baseline_class = classes.mode().iloc[0] if not classes.empty else ""
    event_rows = window.iloc[(window["epoch"] - event_ts).abs().argsort()[:1]]
    event_class = ""
    if not event_rows.empty and pd.notna(event_rows.iloc[0].get("quality_class")):
        event_class = str(event_rows.iloc[0]["quality_class"])

    baseline = float(anomaly["event_baseline"])
    peak = float(anomaly["event_value"])
    multiple = round(peak / baseline, 1) if baseline else None
    return {
        "title": "③ 真实数据端到端候选溯源演示(太湖国控断面)",
        "dataset": (
            f"断面 {anomaly['station_name']}({anomaly['station_id']}) · "
            f"{INDICATOR_LABELS.get(indicator, indicator)} · "
            f"{pd.Timestamp(anomaly['event_dt']).strftime('%Y-%m')}"
        ),
        "station": {
            "id": anomaly["station_id"],
            "name": anomaly["station_name"],
            "lon": result["station"]["lon"],
            "lat": result["station"]["lat"],
        },
        "primary_candidate": {
            "name": candidate["enterprise"],
            "industry": INDUSTRY_LABELS.get(candidate["industry"], candidate["industry"]),
            "city": candidate["city"],
            "lon": candidate["lon_wgs84"],
            "lat": candidate["lat_wgs84"],
            "dist_km": candidate["dist_km"],
            "travel_time": candidate["travel_time"],
            "evidence_status": candidate["evidence_status"],
            "causal_confirmed": candidate["causal_confirmed"],
        },
        "primary_candidate_tie_count": result["primary_candidate_tie_count"],
        "anomaly": {
            "indicator": INDICATOR_LABELS.get(indicator, indicator),
            "event_dt": pd.Timestamp(anomaly["event_dt"]).strftime("%Y-%m-%d %H:%M"),
            "peak": peak,
            "baseline": baseline,
            "multiple": f"约 {multiple:g} 倍基线" if multiple is not None else "基线不可用",
            "class_shift": f"{baseline_class} → {event_class}" if event_class else baseline_class,
            "method": "CUSUM (h=7σ)",
            "severity": {"high": "严重", "medium": "中等", "low": "提示"}.get(
                anomaly["event_severity"], anomaly["event_severity"]
            ),
            "shape": "异常峰前后 14 天实测序列",
        },
        "upstream_path": result["upstream_trace"]["upstream_path_sample"],
        "series": series,
        "evidence_status": result["evidence_status"],
        "causal_confirmed": result["causal_confirmed"],
        "limitations": result["limitations"],
    }


def main() -> None:
    # ===== 1. 读取已核验的站点河网吸附 =====
    st_snap = pd.read_csv(STATIONS_SNAPPED)
    print(
        f"[吸附] 断面命中河网(<{SNAP_LIMIT_M}m): "
        f"{st_snap['matched'].sum()}/{len(st_snap)}; "
        f"中位吸附距离 {st_snap['snap_dist_m'].median():.0f}m"
    )
    rivers = gpd.read_file(RIVERS_SHP)

    # ===== 2. 河网图 + 上溯到企业 =====
    G = build_river_graph(rivers)
    print(f"[河网] 节点 {G.number_of_nodes()} 段, 边 {G.number_of_edges()} 条")

    ents = pd.read_csv(ENT_SNAPPED)
    ent_by_hid = group_enterprises_by_reach(ents)

    # ===== 3. 挑选有上游企业的异常断面 =====
    # 行业→污染指标合理性(用于候选排序佐证,非数值计算)
    industry_indicators = {
        "dyeing": (["codmn", "ammonia_n", "tp"], "印染废水高 COD/氨氮/总磷"),
        "electroplating": (["cr6", "conductivity", "turbidity"], "电镀废水含重金属/高电导"),
        "paper": (["codmn", "ammonia_n"], "造纸废水高 COD"),
        "chemical": (["codmn", "ammonia_n", "tp"], "化工综合废水"),
        "leather": (["codmn", "ammonia_n", "turbidity"], "皮革废水高 COD/氨氮"),
        "pharmaceutical": (["codmn", "ammonia_n"], "制药废水高 COD/氨氮"),
        "wwtp": (["ammonia_n", "codmn", "tp"], "污水处理厂出水氨氮/COD/总磷异常"),
    }
    indicators = ["ammonia_n", "codmn", "tp", "do", "turbidity", "conductivity"]
    # 指标作为工业排污示踪剂的合理性(数值无关,仅用于演示选例与候选佐证)
    indicator_weight = {"ammonia_n": 3, "codmn": 3, "tp": 2, "conductivity": 1, "turbidity": 0, "do": 0}

    candidates = []
    for _, s in st_snap[st_snap["matched"]].iterrows():
        hid = int(s["hyriv_id"])
        ups = upstream_reaches(G, hid, TRAVEL_WINDOW_H)
        ups_hids = {u["hid"] for u in ups}
        upstream_ents = [
            enterprise
            for upstream_hid in ups_hids
            for enterprise in ent_by_hid.get(upstream_hid, [])
        ]
        if not upstream_ents:
            continue
        # 跑 cusum 找该断面最强异常指标
        sid = s["station_id"]
        rd = READINGS_DIR / f"{sid}.csv"
        if not rd.exists():
            continue
        df = pd.read_csv(rd)
        best = None
        for ind in indicators:
            if ind not in df.columns:
                continue
            y = pd.to_numeric(df[ind], errors="coerce").dropna()
            if len(y) < 200:
                continue
            ts = df.loc[y.index, "epoch"].astype("int64").to_numpy()
            dets = detect_cusum(y.to_numpy(), ts)
            n_high = sum(1 for d in dets if d["severity"] in ("high", "medium"))
            if n_high == 0:
                continue
            score = n_high
            if best is None or score > best["score"]:
                best = {"indicator": ind, "n_high": n_high, "n_dets": len(dets),
                        "detections": dets, "score": score}
        if best is None:
            continue
        candidates.append({
            "station_id": sid, "station_name": s["name"], "hyriv_id": hid,
            "station_lon": s["lon_wgs"], "station_lat": s["lat_wgs"],
            "indicator": best["indicator"], "n_high": best["n_high"], "n_dets": best["n_dets"],
            "score": best["score"], "upstream_ents": len(upstream_ents),
            "upstream_reaches": len(ups), "detections": best["detections"],
            "upstream": ups,
            "ind_weight": indicator_weight.get(best["indicator"], 0),
        })

    # 选例优先:指标合理(工业示踪剂) + 上游企业聚焦(少) + 异常显著
    candidates.sort(key=lambda c: (c["ind_weight"], -c["upstream_ents"], c["score"]), reverse=True)
    if not candidates:
        print("[!] 无满足条件的断面(有上游企业且检出异常)")
        return
    print(f"[候选] {len(candidates)} 个断面同时满足:有上游吸附企业 + 检出异常")
    for c in candidates[:8]:
        print(f"  {c['station_id']} {c['station_name']} | 指标={c['indicator']} 高异常={c['n_high']} "
              f"上游企业={c['upstream_ents']} 上游河段={c['upstream_reaches']}")

    pick = candidates[0]

    # ===== 4. 上溯筛选候选企业 + 产出结果 =====
    # 取最严重异常点作为事件窗口
    dets_sorted = sorted(pick["detections"], key=lambda d: abs(d["zscore"]), reverse=True)
    top = dets_sorted[0]
    ts_event = top["ts"]
    dt = datetime.fromtimestamp(ts_event, tz=timezone(timedelta(hours=8)))
    win_before_h = 24
    win_after_h = 12

    # 候选企业:在传播时间窗内的上游企业,按 travel_h 升序,行业-指标匹配加权
    enterprise_candidates = []
    for u in pick["upstream"]:
        for e in ent_by_hid.get(u["hid"], []):
            ind_ok, ind_note = industry_indicators.get(e["industry"], ([], ""))
            ind_match = pick["indicator"] in ind_ok
            enterprise_candidates.append({
                "enterprise": e["name"], "city": e["city"], "industry": e["industry"],
                "credit_code": e["credit_code"], "address": e["address"],
                "lon_wgs84": e["lon_wgs84"], "lat_wgs84": e["lat_wgs84"],
                "hyriv_id": int(e["hyriv_id"]),
                "travel_time": travel_time_metadata(u["travel_h"]),
                "dist_km": u["dist_km"], "snap_dist_m": e["snap_dist_m"],
                "indicator_match": ind_match, "indicator_note": ind_note,
                "ranking_score": u["travel_h"] - (24 if ind_match else 0),
                "evidence_status": "candidate_unverified",
                "causal_confirmed": False,
            })
    enterprise_candidates.sort(key=lambda x: (x["ranking_score"], str(x["enterprise"])))
    primary_candidate = enterprise_candidates[0] if enterprise_candidates else None
    if primary_candidate is None:
        print("[!] 无上游企业候选,停止生成演示结果")
        return
    primary_candidate_tie_count = sum(
        math.isclose(candidate["ranking_score"], primary_candidate["ranking_score"])
        for candidate in enterprise_candidates
    )

    limitations = [
        "企业仅因位于河网上游且行业指标相符而成为候选,未取得排口同期监测证据。",
        "传播时间来自 HydroRIVERS 河段长度与估算流速,只用于排序,不是因果证据。",
        "断面和企业坐标存在地图查询与河网吸附误差,正式归因前必须复核。",
    ]
    if primary_candidate_tie_count > 1:
        limitations.append(
            f"首位有 {primary_candidate_tie_count} 家同分候选;界面仅展示其中一家,"
            "不代表其证据优于其他同分候选。"
        )
    limitations.append("本结果是算法验证,不是对真实污染事件或企业责任的认定。")

    result = {
        "pipeline": "realdata_e2e_trace",
        "summary": {
            "station_id": pick["station_id"], "station_name": pick["station_name"],
            "indicator": pick["indicator"],
            "primary_candidate": primary_candidate["enterprise"],
            "primary_candidate_tie_count": primary_candidate_tie_count,
            "evidence_status": "candidate_unverified",
            "causal_confirmed": False,
        },
        "station": {
            "lon": round(float(pick["station_lon"]), 6),
            "lat": round(float(pick["station_lat"]), 6),
        },
        "anomaly": {
            "station_id": pick["station_id"], "station_name": pick["station_name"],
            "hyriv_id": pick["hyriv_id"], "indicator": pick["indicator"],
            "method": "cusum", "n_detections": pick["n_dets"], "n_high_medium": pick["n_high"],
            "event_ts": ts_event, "event_dt": dt.isoformat(),
            "event_value": top["value"], "event_zscore": top["zscore"], "event_severity": top["severity"],
            "event_baseline": top["baseline"],
            "window_before_h": win_before_h, "window_after_h": win_after_h,
        },
        "upstream_trace": {
            "window_h": TRAVEL_WINDOW_H,
            "upstream_reaches_count": pick["upstream_reaches"],
            "upstream_enterprises_count": pick["upstream_ents"],
            "upstream_path_sample": pick["upstream"][:20],
        },
        "primary_candidate": primary_candidate,
        "primary_candidate_tie_count": primary_candidate_tie_count,
        "candidate_enterprises": enterprise_candidates[:10],
        "all_candidates_summary": [{"station": c["station_id"], "name": c["station_name"],
                                    "indicator": c["indicator"], "n_high": c["n_high"],
                                    "upstream_ents": c["upstream_ents"]} for c in candidates[:15]],
        "assumptions": {
            "coord_source": "百度地图模糊查询(站点经纬度坐标.csv),按 GCJ-02→WGS84 转换,误差米级",
            "snap_limit_m": SNAP_LIMIT_M, "travel_window_h": TRAVEL_WINDOW_H,
            "velocity": f"估速 0.3~2.0 m/s(由 DIS_AV_CMS 对数折算),保底 {ASSUMED_V_MS} m/s",
            "anomaly_engine": "backend/app/engine/anomaly.py detect_cusum (h=7σ, 纯函数)",
            "note": "数值计算(异常检测/拓扑/吸附)全走确定性纯函数;行业-指标映射仅用于候选排序。",
        },
        "evidence_status": "candidate_unverified",
        "causal_confirmed": False,
        "limitations": limitations,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "e2e_trace_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    picked_readings = pd.read_csv(READINGS_DIR / f"{pick['station_id']}.csv")
    frontend_case = build_frontend_case(result, picked_readings)
    FRONTEND_OUT.parent.mkdir(parents=True, exist_ok=True)
    FRONTEND_OUT.write_text(
        json.dumps(frontend_case, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print("\n" + "=" * 60)
    print(f"[结果] 断面 {pick['station_id']}({pick['station_name']}) 指标={pick['indicator']}")
    print(f"  异常事件: {dt:%Y-%m-%d %H:%M} 值={top['value']} z={top['zscore']} 严重度={top['severity']}")
    print(f"  首选候选: {primary_candidate['enterprise']}({primary_candidate['industry']})")
    print(
        f"  行业指标匹配: {primary_candidate['indicator_match']}"
        f"({primary_candidate['indicator_note']})"
    )
    estimate_h = primary_candidate["travel_time"]["estimate_h"]
    print(f"  估算传播时间: {estimate_h}h, 距离 {primary_candidate['dist_km']}km")
    print(f"  上游企业候选: {pick['upstream_ents']} 家, 上游河段: {pick['upstream_reaches']} 段")
    print(f"  结果写入: {OUT_DIR / 'e2e_trace_result.json'}")
    print(f"  前端投影: {FRONTEND_OUT}")


if __name__ == "__main__":
    main()
