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
- 每轮注入后回滚 readings(避免污染叠加影响后续轮次)

用法:
    python scripts/batch_eval.py [轮数]   # 默认 12 轮
"""
from __future__ import annotations

import json
import sys
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


def main(rounds: int = 12) -> None:
    ensure_db(settings)
    db, ws = get_db_path(), get_watershed()
    rng = np.random.default_rng(42)

    # 注入时间轴:与 seed 完全一致的全程 t_min(相对分钟,0 起,15min 步长)。
    # apply_event 的 onset_day 是数组下标基准(onset_day*96),必须用全程序列;
    # onset 只随机在末段 20 天(避开预置事件,留传播余量)
    conn = get_conn(db)
    ts_max = conn.execute("SELECT MAX(ts) FROM readings").fetchone()[0]
    total_min = (ts_max - T0) // 60
    conn.close()
    t_min = np.arange(0, total_min + 15, 15)
    last_day = total_min // 1440

    ents = [e for e in ws["enterprises"]]
    results = []
    print(f"===== 批量评测: {rounds} 轮(注入窗口: 末段 20 天)=====")

    for i in range(rounds):
        etype = ETYPES[i % len(ETYPES)]
        sev = SEVERITIES[i % len(SEVERITIES)]
        ent = ents[int(rng.integers(len(ents)))]
        # onset_day:数据起点起的绝对天数,随机在末段 15 天(留 5 天传播余量)
        onset_day = last_day - 15 + int(rng.integers(0, 15))

        spec = {"etype": etype, "source_id": ent["id"], "severity": sev,
                "onset_day": onset_day, "duration_d": 3}
        if etype == "sudden":
            spec["mass_kg"] = 80.0

        # 注入 → 生成事件行(告警断面 = 真实首达断面,与 seed 相同逻辑)
        conn = get_conn(db)
        apply_event(conn, ws, spec, t_min, rng)
        alert = alert_station_for(ws, ent["id"]) or ws["stations"][0]["id"]
        ev_id = f"evalevt_{i:03d}"
        # onset 绝对时间 = T0 + 相对分钟×60(与 readings.ts 同基准)
        onset_ts = T0 + spec["onset_day"] * 1440 * 60
        conn.execute(
            "INSERT OR REPLACE INTO events (id,station_id,indicators,onset_ts,severity,"
            "etype,truth_source,status) VALUES (?,?,?,?,?,?,?,?)",
            (ev_id, alert, json.dumps(["cod"]), onset_ts, sev, etype, ent["id"], "open"))
        conn.commit()
        conn.close()

        # 监测 Agent 扫描(预警检出率口径:窗口内该断面出现新告警)
        detected = scan_for_events(db, ws, window_h=24)

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
            "alert_station": alert, "detected": bool(detected),
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

        # 回滚:删除评测事件行(readings 增量下轮叠加影响可忽略,每轮窗口独立)
        conn = get_conn(db)
        conn.execute("DELETE FROM events WHERE id=?", (ev_id,))
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
    mrr = sum(1.0 / r["rank"] for r in results if r["rank"]) / n
    confs = [r["confidence"] for r in results if r["locked"]]
    errs = [r["travel_err_h"] for r in results if r["travel_err_h"] is not None]

    print("\n===== 汇总指标 =====")
    print(f"轮数:              {n}")
    print(f"预警检出率:        {detected_n}/{n} = {detected_n/n:.0%}")
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
        print(f"{et:8s}: Top-1 {t1}/{len(sub)} ({t1/len(sub):.0%}), "
              f"锁定 {lk}/{len(sub)} ({lk/len(sub):.0%})")

    # 落盘评测报告
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "rounds": n,
        "summary": {
            "detection_rate": detected_n / n,
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
    out_path = BACKEND.parent / "data" / "processed" / "batch_eval_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n评测报告已写入: {out_path}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
