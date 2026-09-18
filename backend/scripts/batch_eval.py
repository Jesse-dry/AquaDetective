"""批量评测:自动注入 N 个随机事件 → 逐个跑完整调查 → 汇总溯源指标。

产出指标(对应《后续开发计划》§8):
- 预警检出率(注入事件被监测 Agent 扫出的比例)
- 上游候选召回率(真凶进入假设列表的比例)
- 污染源 Top-1 / Top-3 / MRR(最终候选排名命中)
- 置信度分布(命中样本的 confidence 均值/最小值)
- 按事件类型(sudden/periodic/gradual)分组的命中率

设计要点:
- 评测走与线上完全相同的调查链路(节点函数直调,LLM=None 模板降级,无副作用落盘)
- 真值隔离:调查引擎只拿观测数据,truth_source 仅在本脚本内做对答案
- 全程在演示库的**副本**上跑(注入会写 readings),演示库保持干净可复现
- 检出率口径:注入时点落在监测扫描窗口(最近 24h)内,且以真实首达断面是否被
  检出为准(不是"扫到了任何东西")

用法:
    python scripts/batch_eval.py [轮数]   # 默认 12 轮
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.agents.compliance import compliance_review  # noqa: E402
from app.agents.investigator import (conclude, generate_hypotheses,  # noqa: E402
                                     parse_event, verify_hypotheses)
from app.agents.monitor import scan_for_events  # noqa: E402
from app.agents.reporter import build_report  # noqa: E402
from app.agents.responder import response_plan  # noqa: E402
from app.agents import tools  # noqa: E402
from app.config import settings  # noqa: E402
from app.context import get_db_path, get_watershed  # noqa: E402
from app.data.seed import ensure_db  # noqa: E402
from app.data.event_observations import upsert_event_observation  # noqa: E402
from app.data.series_generator import T0, alert_station_for, apply_event  # noqa: E402
from app.db import get_conn  # noqa: E402
from app.engine.dispersion import puff_at  # noqa: E402

NODES = [parse_event, generate_hypotheses, verify_hypotheses, conclude,
         compliance_review, response_plan, build_report]
# 注入参数空间:类型 × 严重度,源企业从 18 家中随机(排除 event_only 平时不排的也可命中)
ETYPES = ["sudden", "periodic", "gradual"]
SEVERITIES = ["low", "medium", "high"]
SEVERITY_MULT = {"low": 1.5, "medium": 2.0, "high": 2.5}


def run_investigation(event_row: dict, db: str, ws: dict) -> dict:
    """跑一次完整调查(与 smoke_investigate 同路径,模板降级,无落盘副作用)。"""
    state = {
        "event": event_row, "hypotheses": [], "evidence_log": [],
        "conclusion": None, "report": None, "stream": [], "round": 0,
        "done": False, "investigation_id": f"eval_{uuid4().hex[:6]}",
    }
    for fn in NODES:
        state.update(fn(state, None, db, ws))
        if fn is verify_hypotheses and not state.get("done"):
            while not state.get("done"):
                state.update(verify_hypotheses(state, None, db, ws))
    return state


def _copy_database(source: str, target: str) -> None:
    """SQLite backup includes committed WAL pages, unlike copying the main file."""
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


def main(rounds: int = 12, output_path: Path | None = None) -> None:
    if rounds < 1:
        raise ValueError("rounds must be positive")
    ensure_db(settings)
    with tempfile.TemporaryDirectory(prefix="aqua_eval_") as directory:
        baseline = str(Path(directory) / "baseline.db")
        db = str(Path(directory) / "round.db")
        _copy_database(get_db_path(), baseline)
        # Existing detected events must not suppress the injected test events.
        with closing(get_conn(baseline)) as conn, conn:
            conn.execute("DELETE FROM event_observations WHERE event_id IN "
                         "(SELECT id FROM events WHERE etype='detected')")
            conn.execute("DELETE FROM investigations WHERE event_id IN "
                         "(SELECT id FROM events WHERE etype='detected')")
            conn.execute("DELETE FROM events WHERE etype='detected'")
            conn.execute("DELETE FROM monitor_cursors")
        _copy_database(baseline, db)
        _evaluate(rounds, baseline, db, output_path)


def _evaluate(rounds: int, baseline: str, db: str, output_path: Path | None) -> None:
    ws = get_watershed()
    rng = np.random.default_rng(42)

    # 注入时间轴:与 seed 完全一致的全程 t_min(相对分钟,0 起,15min 步长)。
    # apply_event 的 onset_day 是数组下标基准(onset_day*96),必须用全程序列;
    # onset 位于末日，与最近 24 小时扫描窗口一致。
    conn = get_conn(db)
    ts_max = conn.execute("SELECT MAX(ts) FROM readings").fetchone()[0]
    total_min = (ts_max - T0) // 60
    conn.close()
    t_min = np.arange(0, total_min + 15, 15)
    last_day = total_min // 1440

    # 干净基线上本来就报出的告警(常驻误报):归因检出率要把它扣掉,
    # 否则任何注入都"自动命中",数字虚高
    def _alarmed_pairs(events=None):
        """扫描结果覆盖的 (断面,指标) 集合(合并事件按波及断面展开)。"""
        events = scan_for_events(db, ws, window_h=24, method=settings.monitor_method) if events is None else events
        return {(a["station_id"], a["indicator"])
                for e in events
                for a in (e.get("affected") or [{"station_id": e["station_id"],
                                                 "indicator": i}
                                                for i in e.get("indicators", [])])}

    _copy_database(baseline, db)
    chronic = _alarmed_pairs()
    print(f"干净基线常驻告警: {len(chronic)} 个(断面,指标)")

    ents = [e for e in ws["enterprises"]]
    results = []
    print(f"===== 批量评测: {rounds} 轮(注入窗口: 最近 24h)=====")

    for i in range(rounds):
        # Restore the same baseline each round; injected readings never accumulate.
        _copy_database(baseline, db)
        etype = ETYPES[i % len(ETYPES)]
        # 严重度用不同模数,与类型解绑:若两者同用 i%3,则突发恒为 low、
        # 周期恒为 medium、渐变恒为 high,分类型数字实际是(类型,严重度)组合数,
        # 既分不清类型差异也分不清严重度差异
        sev = SEVERITIES[(i // len(ETYPES)) % len(SEVERITIES)]
        ent = ents[int(rng.integers(len(ents)))]
        # onset_day:必须落在监测扫描窗口(最近 24h)内,否则测的不是检出能力
        onset_day = last_day

        spec = {"etype": etype, "source_id": ent["id"], "severity": sev,
                "onset_day": onset_day, "duration_d": 3}
        if etype == "sudden":
            spec["mass_kg"] = 80.0

        # 注入时序(告警断面 = 真实首达断面,与 seed 相同逻辑)
        conn = get_conn(db)
        summary = apply_event(conn, ws, spec, t_min, rng)
        conn.commit()
        conn.close()
        alert = alert_station_for(ws, ent["id"]) or ws["stations"][0]["id"]
        # 本次注入实际污染到的断面(峰值增量为正),用于"有没有发现这次污染"的口径
        polluted = {s["station_id"] for s in summary if s["peak_delta"] > 0}

        # 监测 Agent 扫描:线上告警由它产生,故注入后先扫再建事件行
        detected = scan_for_events(db, ws, window_h=24, method=settings.monitor_method)
        # 合并后一条事件覆盖多个断面,故取全部波及断面
        alerted = {st for d in detected for st in d.get("stations", [d["station_id"]])}
        alerted_pairs = _alarmed_pairs(detected)
        # 严格口径:最有溯源价值的首达断面被检出;宽松口径:任一受污染断面被检出
        hit = alert in alerted
        hit_any = bool(alerted & polluted)
        # 归因口径:扣掉干净基线上本来就报的常驻告警,只算本次注入带来的新检出
        new_pairs = alerted_pairs - chronic
        hit_attr = any((alert, ind) in new_pairs for ind in
                       {s["indicator"] for s in summary
                        if s["station_id"] == alert and s["peak_delta"] > 0})

        # 清掉本轮监测告警,再用同一断面建调查用事件行(走与线上一致的调查链路)
        conn = get_conn(db)
        conn.execute("DELETE FROM events WHERE id LIKE 'evt_scan_%'")
        ev_id = f"evalevt_{i:03d}"
        # onset 绝对时间 = T0 + 相对分钟×60(与 readings.ts 同基准)
        onset_ts = T0 + spec["onset_day"] * 1440 * 60
        conn.execute(
            "INSERT OR REPLACE INTO events (id,station_id,indicators,onset_ts,severity,"
            "etype,truth_source,status) VALUES (?,?,?,?,?,?,?,?)",
            (ev_id, alert, json.dumps(["cod"]), onset_ts, sev, etype, ent["id"], "open"))
        # 生成事件观测(与 seed 同路径):现场 EEM/污染物以真凶指纹为主导。
        # 没有它调查只能拿到无标签背景观测,EEM 得分反映的是基线而非案发现场
        upsert_event_observation(conn, ws, ev_id, alert, ent["id"], 42 + i)
        conn.commit()
        conn.close()

        # 完整调查(与线上同链路)
        conn = get_conn(db)
        row = conn.execute("SELECT * FROM events WHERE id=?", (ev_id,)).fetchone()
        conn.close()
        t0 = time.time()
        state = run_investigation(dict(row), db, ws)
        dur = time.time() - t0

        concl = state.get("conclusion") or {}
        hyps = state.get("hypotheses") or []
        truth = ent["id"]
        # 候选排名:最终仍为 candidate 的按得分降序(与 conclude 同序)
        cands = sorted((h for h in hyps if h["status"] == "candidate"),
                       key=lambda h: h["score"], reverse=True)
        rank_ids = [h["target_id"] for h in cands]
        rank = rank_ids.index(truth) + 1 if truth in rank_ids else None

        # 传播时间误差(§8 指标):调查的拓扑估时 travel_hours vs 高斯烟团峰值时刻。
        # 两者都是确定性引擎产出:估时是最短路径距离/流速,真值是烟团浓度峰值 t=argmax c(t)
        st_node = next(s["node_id"] for s in ws["stations"] if s["id"] == alert)
        pred_h = tools.travel_hours(ws, ent["node_id"], st_node)
        t_grid = np.linspace(0.1, 24.0, 480)
        c_curve = puff_at(ws, ent["node_id"], st_node, 80.0, t_grid)
        true_h = float(t_grid[int(np.argmax(c_curve))]) if c_curve.max() > 1e-9 else None
        travel_err = abs(pred_h - true_h) if (pred_h is not None and true_h) else None

        results.append({
            "round": i + 1, "etype": etype, "severity": sev,
            "truth": ent["id"], "truth_name": ent["name"],
            "alert_station": alert, "detected": hit, "detected_any": hit_any,
            "detected_attributable": hit_attr,
            "polluted_stations": sorted(polluted),
            "n_hypotheses": len(hyps),
            "recall_upstream": truth in [h["target_id"] for h in hyps],
            "rank": rank,
            "top1": rank == 1, "top3": rank is not None and rank <= 3,
            "locked": concl.get("source_id") == truth,
            "confidence": concl.get("confidence", 0.0),
            "status": concl.get("status", "failed"),
            "travel_pred_h": pred_h, "travel_true_h": true_h,
            "travel_err_h": round(travel_err, 2) if travel_err is not None else None,
            "duration_s": round(dur, 2),
        })
        r = results[-1]
        print(f"  [{i+1:2d}] {etype:8s} {sev:6s} 真凶={ent['name'][:10]:12s} "
              f"排名={rank or '-'} 锁定={'✓' if r['locked'] else '✗'} "
              f"conf={r['confidence']:.2f} 传播={r['travel_err_h']}h {r['duration_s']}s")

        # 清理本轮事件；下一轮会从基线恢复全部 readings。
        conn = get_conn(db)
        conn.execute("DELETE FROM events WHERE id=?", (ev_id,))
        conn.execute("DELETE FROM event_observations WHERE event_id=?", (ev_id,))
        # 同时清掉监测 Agent 可能生成的 evt_* 检测事件(避免污染告警面板)
        conn.execute("DELETE FROM events WHERE id LIKE 'evt_%' AND etype='detected'")
        conn.commit()
        conn.close()

    # ---------- 汇总 ----------
    n = len(results)
    top1 = sum(r["top1"] for r in results)
    top3 = sum(r["top3"] for r in results)
    locked = sum(r["locked"] for r in results)
    recall_up = sum(r["recall_upstream"] for r in results)
    detected_n = sum(r["detected"] for r in results)
    detected_any_n = sum(r["detected_any"] for r in results)
    detected_attr_n = sum(r["detected_attributable"] for r in results)
    mrr = sum(1.0 / r["rank"] for r in results if r["rank"]) / n
    confs = [r["confidence"] for r in results if r["locked"]]
    errs = [r["travel_err_h"] for r in results if r["travel_err_h"] is not None]

    print("\n===== 汇总指标 =====")
    print(f"轮数:              {n}")
    print(f"预警检出率(首达断面): {detected_n}/{n} = {detected_n/n:.0%}")
    print(f"预警检出率(任一受污染断面): {detected_any_n}/{n} = {detected_any_n/n:.0%}")
    print(f"预警检出率(归因,扣常驻告警): {detected_attr_n}/{n} = {detected_attr_n/n:.0%}")
    print(f"上游候选召回率:    {recall_up}/{n} = {recall_up/n:.0%}")
    print(f"Top-1 命中率:      {top1}/{n} = {top1/n:.0%}")
    print(f"Top-3 命中率:      {top3}/{n} = {top3/n:.0%}")
    print(f"最终锁定命中率:    {locked}/{n} = {locked/n:.0%}")
    print(f"MRR:               {mrr:.3f}")
    if confs:
        print(f"命中样本置信度:    均值 {np.mean(confs):.2f} / 最小 {min(confs):.2f}")
    if errs:
        print(f"传播时间误差(h):   均值 {np.mean(errs):.2f} / 最大 {max(errs):.2f} "
              f"(有效样本 {len(errs)}/{n})")

    print("\n===== 按事件类型分组 =====")
    for et in ETYPES:
        sub = [r for r in results if r["etype"] == et]
        if not sub:
            continue
        t1 = sum(r["top1"] for r in sub)
        lk = sum(r["locked"] for r in sub)
        de = sum(r["detected"] for r in sub)
        da = sum(r["detected_any"] for r in sub)
        dat = sum(r["detected_attributable"] for r in sub)
        print(f"{et:8s}: 检出(首达) {de}/{len(sub)} ({de/len(sub):.0%}), "
              f"检出(归因) {dat}/{len(sub)} ({dat/len(sub):.0%}), "
              f"检出(任一) {da}/{len(sub)} ({da/len(sub):.0%}), "
              f"Top-1 {t1}/{len(sub)} ({t1/len(sub):.0%}), "
              f"锁定 {lk}/{len(sub)} ({lk/len(sub):.0%})")

    print("\n===== 按严重度分组(与类型已解绑)=====")
    for sv in SEVERITIES:
        sub = [r for r in results if r["severity"] == sv]
        if not sub:
            continue
        de = sum(r["detected"] for r in sub)
        t1 = sum(r["top1"] for r in sub)
        print(f"{sv:8s}: 检出(首达) {de}/{len(sub)} ({de/len(sub):.0%}), "
              f"Top-1 {t1}/{len(sub)} ({t1/len(sub):.0%})")

    print("\n===== 按类型×严重度(每格样本数少,仅用于归因)=====")
    for et in ETYPES:
        cells = []
        for sv in SEVERITIES:
            sub = [r for r in results if r["etype"] == et and r["severity"] == sv]
            if not sub:
                continue
            de = sum(r["detected"] for r in sub)
            cells.append(f"{sv} {de}/{len(sub)}")
        print(f"{et:8s}: " + " | ".join(cells))

    # 落盘评测报告
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "rounds": n,
        "methodology": {
            "monitor_method": settings.monitor_method,
            "round_isolation": "SQLite backup restored before every injection",
            "detection": "First arrival station appears in new alerts within the latest 24 hours",
            "detection_any_station": "Any polluted station appears in new alerts within the latest 24 hours",
            "investigation": "All injected events investigated independently of detection",
            "sampling": "Seed 42; random enterprise; cyclic type/severity pairs",
        },
        "summary": {
            "detection_rate": detected_n / n,
            "detection_rate_any_station": detected_any_n / n,
            "detection_rate_attributable": detected_attr_n / n,
            "chronic_alerts": len(chronic),
            "upstream_recall": recall_up / n,
            "top1": top1 / n, "top3": top3 / n,
            "locked": locked / n, "mrr": round(mrr, 4),
            "confidence_mean": round(float(np.mean(confs)), 3) if confs else None,
            "confidence_min": round(min(confs), 3) if confs else None,
            "travel_err_mean_h": round(float(np.mean(errs)), 2) if errs else None,
            "travel_err_max_h": round(max(errs), 2) if errs else None,
            "travel_err_samples": len(errs),
        },
        "results": results,
    }
    out_path = output_path or BACKEND.parent / "data" / "processed" / "batch_eval_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n评测报告已写入: {out_path}")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
