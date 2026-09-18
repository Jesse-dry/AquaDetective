"""仿真控制：重置世界 / 运行时注入事件。"""
from __future__ import annotations

import json
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, HTTPException

from ..config import settings
from ..context import get_db_path, get_watershed
from ..data import seed as seed_mod
from ..data.event_observations import upsert_event_observation
from ..data.series_generator import T0, alert_station_for, apply_event
from ..db import get_conn

router = APIRouter(tags=["simulate"])

VALID_ETYPES = {"sudden", "periodic", "gradual"}


@router.post("/simulate/reset")
def reset_world(seed: int | None = None):
    """一键重建世界（同 seed 可复现）。"""
    summary = seed_mod.run(settings, seed=seed)
    return {"ok": True, **summary}


@router.post("/simulate/inject")
def inject_event(body: dict):
    """运行时注入污染事件（现场演示按钮）。

    body: {etype, source_id, severity, onset_day, duration_d, mass_kg?, notify?}

    notify=False 为"静默注入":只写时序,不建告警事件 —— 供演示监测 Agent
    自己从数据里发现污染(点"立即扫描"后由它生成 evt_scan_NNN)。
    此时 onset_day 默认落在序列末端,否则注入的污染不在扫描窗口内、扫不出来。
    """
    etype = body.get("etype")
    source_id = body.get("source_id")
    severity = body.get("severity", "high")
    notify = body.get("notify", True)
    if etype not in VALID_ETYPES:
        raise HTTPException(400, f"etype 必须为 {sorted(VALID_ETYPES)}")
    ws = get_watershed()
    if not any(e["id"] == source_id for e in ws["enterprises"]):
        raise HTTPException(404, "企业不存在")
    days = 90
    spec = {k: v for k, v in body.items() if k in
            ("etype", "source_id", "severity", "onset_day", "duration_d", "mass_kg")}
    if notify:
        spec.setdefault("onset_day", 30)
    else:
        # 静默注入要能被"最近 24h"扫描窗口看见,故默认落在末日
        conn = get_conn(get_db_path())
        ts_max = conn.execute("SELECT MAX(ts) FROM readings").fetchone()[0]
        conn.close()
        spec.setdefault("onset_day", max(0, (ts_max - T0) // 86400))
    spec.setdefault("duration_d", 3 if etype != "gradual" else 15)
    spec.setdefault("mass_kg", 80)  # sudden 事件需要,前端不传时用默认值
    if not (0 <= spec["onset_day"] < days):
        raise HTTPException(400, "onset_day 超出范围")
    conn = get_conn(get_db_path())
    rng = np.random.default_rng(settings.seed)
    t_min = np.arange(days * 1440) * 15
    summary = apply_event(conn, ws, spec, t_min, rng)
    # 注入是"改写已有时间戳上的读数"(UPDATE ... SET value = value + ?),不是追加新数据。
    # 增量扫描的游标会认为这些序列已经看过而整条跳过 —— 实测静默注入后扫描
    # 显示"扫描 0 条 / 跳过 50 条"、什么也发现不了。读数被改写即进度失效,须清游标。
    conn.execute("DELETE FROM monitor_cursors")
    conn.commit()
    conn.close()
    if not summary:
        raise HTTPException(400, "事件未影响任何断面")
    alert = alert_station_for(ws, source_id)
    inds = sorted({s["indicator"] for s in summary})
    onset_ts = T0 + spec["onset_day"] * 86400
    if not notify:
        # 静默注入:时序已写入,不建事件 —— 等监测 Agent 自己扫出来
        return {"ok": True, "silent": True, "alert_station": alert,
                "onset_ts": onset_ts, "summary": summary}
    # 可读递增 id:evt_inj_001(避免 uuid 乱码,前端展示为"现场注入N")
    conn = get_conn(get_db_path())
    nums = [int(r[0].rsplit("_", 1)[1]) for r in conn.execute(
        "SELECT id FROM events WHERE id LIKE 'evt_inj_%'").fetchall()
        if r[0].rsplit("_", 1)[1].isdigit()]
    ev_id = f"evt_inj_{(max(nums) + 1 if nums else 1):03d}"
    # 波及断面按 apply_event 已算出的增量写入:监测 Agent 的去重靠它认出
    # "这次污染已经报过了",否则下游断面的检出会凑成第二条重复事件
    affected = [{"station_id": s["station_id"], "indicator": s["indicator"],
                 "ts": onset_ts, "severity": severity}
                for s in summary if abs(s["peak_delta"]) > 0]
    conn.execute(
        "INSERT INTO events (id,station_id,indicators,onset_ts,severity,etype,"
        "truth_source,status,affected_stations) VALUES (?,?,?,?,?,?,?,?,?)",
        (ev_id, alert, json.dumps(inds), onset_ts,
         severity, etype, source_id, "open",
         json.dumps(affected, ensure_ascii=False)))
    upsert_event_observation(conn, ws, ev_id, alert, source_id, settings.seed)
    conn.commit()
    conn.close()
    return {"ok": True, "event_id": ev_id, "alert_station": alert, "summary": summary}


@router.delete("/simulate/events/{event_id}")
def delete_injected_event(event_id: str):
    """删除手动注入的事件(仅 evt_inj_ 前缀,预置事件受保护)。
    删除事件行 + 事件观测;readings 时序保留(回放仍可看)。"""
    if not event_id.startswith("evt_inj_"):
        raise HTTPException(400, "仅支持删除手动注入事件(evt_inj_ 前缀)")
    conn = get_conn(get_db_path())
    row = conn.execute("SELECT id FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "事件不存在")
    conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.execute("DELETE FROM event_observations WHERE event_id=?", (event_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "deleted": event_id}
