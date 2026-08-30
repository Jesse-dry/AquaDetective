"""溯源调查：触发 / 状态查询 / 记录回放。"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ..agents import recorder as rec_mod
from ..agents.runner import run_investigation
from ..context import get_db_path, get_llm, get_watershed
from ..db import get_conn
from .time import epoch_ms
from .ws import INVESTIGATIONS

router = APIRouter(tags=["investigate"])


@router.get("/events")
def list_events(status: str | None = None, limit: int = 50):
    conn = get_conn(get_db_path())
    if status:
        rows = conn.execute(
            "SELECT * FROM events WHERE status=? ORDER BY onset_ts DESC LIMIT ?",
            (status, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM events ORDER BY onset_ts DESC LIMIT ?",
                            (limit,)).fetchall()
    conn.close()
    # API 契约:onset_ts 转毫秒(内部存秒)
    result = []
    for row in rows:
        event = dict(row)
        event["onset_ts"] = epoch_ms(event["onset_ts"])
        result.append(event)
    return result


@router.post("/events/{event_id}/investigate")
async def start_investigation(event_id: str):
    conn = get_conn(get_db_path())
    row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "事件不存在")
    ev = dict(row)
    inv_id = f"inv_{uuid4().hex[:8]}"
    conn.execute("UPDATE events SET status='investigating' WHERE id=?", (event_id,))
    conn.execute("INSERT INTO investigations (id,event_id,started_at,status) VALUES (?,?,?,?)",
                 (inv_id, event_id, int(time.time()), "running"))
    conn.commit()
    conn.close()

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    done = threading.Event()
    INVESTIGATIONS[inv_id] = {"queue": queue, "done": done}

    def push(msg: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    threading.Thread(
        target=run_investigation,
        args=(inv_id, ev, get_llm(), get_db_path(), get_watershed(), push, done),
        daemon=True).start()
    return {"investigation_id": inv_id, "event_id": event_id, "status": "running"}


@router.get("/investigations/{inv_id}")
def investigation_status(inv_id: str):
    conn = get_conn(get_db_path())
    row = conn.execute("SELECT * FROM investigations WHERE id=?", (inv_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "调查不存在")
    out = dict(row)
    out["started_at"] = epoch_ms(out["started_at"])
    out["conclusion"] = json.loads(out["conclusion"]) if out["conclusion"] else None
    out["stream"] = rec_mod.replay(inv_id)
    return out


@router.get("/recordings")
def list_recordings():
    # 附带事件摘要(事件id/断面/指标/调查时间),供前端渲染可读标签而非裸 inv_xxx
    conn = get_conn(get_db_path())
    events = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM events").fetchall()
    }
    inv_rows = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT id, event_id, started_at FROM investigations").fetchall()
    }
    conn.close()
    recordings = []
    for inv_id in rec_mod.list_recordings():
        entry: dict = {"investigation_id": inv_id}
        row = inv_rows.get(inv_id)
        if row:
            ev = events.get(row["event_id"])
            if ev:
                entry["event_id"] = ev["id"]
                entry["station_id"] = ev["station_id"]
                entry["indicators"] = json.loads(ev["indicators"]) if ev["indicators"] else []
            entry["started_at"] = epoch_ms(row["started_at"])
        else:
            # 兜底:investigations 表已重建(seed --force)的历史录音,
            # 从 stream 首条 parse step 的证据里恢复事件字段
            for msg in rec_mod.replay(inv_id):
                data = msg.get("data") or {}
                if data.get("step_id") == "parse":
                    ev_data = next(
                        (e["value"] for e in data.get("evidence", [])
                         if e.get("kind") == "event" and isinstance(e.get("value"), dict)),
                        None,
                    )
                    if ev_data:
                        entry["event_id"] = ev_data.get("id")
                        entry["station_id"] = ev_data.get("station_id")
                        raw_ind = ev_data.get("indicators")
                        if isinstance(raw_ind, str):
                            try:
                                raw_ind = json.loads(raw_ind)
                            except ValueError:
                                raw_ind = []
                        entry["indicators"] = raw_ind or []
                        if ev_data.get("onset_ts"):
                            entry["started_at"] = epoch_ms(ev_data["onset_ts"])
                    break
        recordings.append(entry)
    return {"recordings": recordings}


@router.get("/recordings/{inv_id}")
def get_recording(inv_id: str):
    msgs = rec_mod.replay(inv_id)
    if not msgs:
        raise HTTPException(404, "记录不存在")
    return {"investigation_id": inv_id, "stream": msgs}


@router.delete("/recordings/{inv_id}")
def delete_recording(inv_id: str):
    """删除一条历史录音(jsonl + 报告 md)。"""
    if not rec_mod.delete_recording(inv_id):
        raise HTTPException(404, "记录不存在")
    return {"deleted": inv_id}
