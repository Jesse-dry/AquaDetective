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

    body: {etype, source_id, severity, onset_day, duration_d, mass_kg?}
    """
    etype = body.get("etype")
    source_id = body.get("source_id")
    severity = body.get("severity", "high")
    if etype not in VALID_ETYPES:
        raise HTTPException(400, f"etype 必须为 {sorted(VALID_ETYPES)}")
    ws = get_watershed()
    if not any(e["id"] == source_id for e in ws["enterprises"]):
        raise HTTPException(404, "企业不存在")
    days = 90
    spec = {k: v for k, v in body.items() if k in
            ("etype", "source_id", "severity", "onset_day", "duration_d", "mass_kg")}
    spec.setdefault("onset_day", 30)
    spec.setdefault("duration_d", 3 if etype != "gradual" else 15)
    spec.setdefault("mass_kg", 80)  # sudden 事件需要,前端不传时用默认值
    if not (0 <= spec["onset_day"] < days):
        raise HTTPException(400, "onset_day 超出范围")
    conn = get_conn(get_db_path())
    rng = np.random.default_rng(settings.seed)
    t_min = np.arange(days * 1440) * 15
    summary = apply_event(conn, ws, spec, t_min, rng)
    conn.close()
    if not summary:
        raise HTTPException(400, "事件未影响任何断面")
    alert = alert_station_for(ws, source_id)
    inds = sorted({s["indicator"] for s in summary})
    # 可读递增 id:evt_inj_001(避免 uuid 乱码,前端展示为"现场注入N")
    conn = get_conn(get_db_path())
    nums = [int(r[0].rsplit("_", 1)[1]) for r in conn.execute(
        "SELECT id FROM events WHERE id LIKE 'evt_inj_%'").fetchall()
        if r[0].rsplit("_", 1)[1].isdigit()]
    ev_id = f"evt_inj_{(max(nums) + 1 if nums else 1):03d}"
    conn.execute(
        "INSERT INTO events (id,station_id,indicators,onset_ts,severity,etype,truth_source,status) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (ev_id, alert, json.dumps(inds), T0 + spec["onset_day"] * 86400,
         severity, etype, source_id, "open"))
    upsert_event_observation(conn, ws, ev_id, alert, source_id, settings.seed)
    conn.commit()
    conn.close()
    return {"ok": True, "event_id": ev_id, "alert_station": alert, "summary": summary}
