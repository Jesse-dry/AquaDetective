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
    return {"recordings": rec_mod.list_recordings()}


@router.get("/recordings/{inv_id}")
def get_recording(inv_id: str):
    msgs = rec_mod.replay(inv_id)
    if not msgs:
        raise HTTPException(404, "记录不存在")
    return {"investigation_id": inv_id, "stream": msgs}
