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
        # 传 get_llm 工厂:各节点按 Agent 取客户端(未配 AQ_LLM_<AGENT>_* 时等同全局默认)
        args=(inv_id, ev, get_llm, get_db_path(), get_watershed(), push, done),
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
        for row in conn.execute(
            "SELECT id, event_id, started_at, status, conclusion FROM investigations").fetchall()
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
            entry["status"] = row["status"]
            concl = json.loads(row["conclusion"]) if row.get("conclusion") else None
            if isinstance(concl, dict):
                entry["source_id"] = concl.get("source_id")
                entry["confidence"] = concl.get("confidence")
        else:
            # 兜底:investigations 表已重建(seed --force)的历史录音,
            # 从 stream 里恢复事件字段与结论(对标页据此判定是否运行过)
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
                        raw_onset = ev_data.get("onset_ts")
                        if raw_onset:
                            # parse 步证据里的 onset_ts 已是毫秒,不能再 epoch_ms(会变微秒)
                            entry["started_at"] = int(raw_onset) if raw_onset > 1e11 \
                                else epoch_ms(raw_onset)
                elif msg.get("type") == "conclusion":
                    entry["status"] = "resolved"
                    entry["source_id"] = data.get("source_id")
                    entry["confidence"] = data.get("confidence")
                elif msg.get("type") == "failed":
                    entry["status"] = "failed"
        recordings.append(entry)
    # 同一事件多次调查只保留最新一条(按 started_at 降序取首条),
    # 避免回放列表里同一事件重复刷屏;无 event_id 的历史录音各自独立保留
    best: dict[str, dict] = {}
    others: list[dict] = []
    for rec in recordings:
        eid = rec.get("event_id")
        if not eid:
            others.append(rec)
            continue
        cur = best.get(eid)
        if cur is None or (rec.get("started_at") or 0) > (cur.get("started_at") or 0):
            best[eid] = rec
    # 去重后按调查时间降序(最新在前),无时间戳的排末尾
    merged = sorted(best.values(), key=lambda r: r.get("started_at") or 0, reverse=True)
    return {"recordings": merged + others}


@router.get("/recordings/{inv_id}")
def get_recording(inv_id: str):
    msgs = rec_mod.replay(inv_id)
    if not msgs:
        raise HTTPException(404, "记录不存在")
    return {"investigation_id": inv_id, "stream": msgs}


@router.delete("/recordings/{inv_id}")
def delete_recording(inv_id: str):
    """删除一条历史录音(jsonl + 报告 md)。
    列表按事件去重显示,故同事件的其余录音一并删除,避免删后旧的又被展示出来。"""
    conn = get_conn(get_db_path())
    row = conn.execute("SELECT event_id FROM investigations WHERE id=?", (inv_id,)).fetchone()
    event_id = row["event_id"] if row else None
    conn.close()
    deleted = []
    if rec_mod.delete_recording(inv_id):
        deleted.append(inv_id)
    if event_id:
        conn2 = get_conn(get_db_path())
        sibs = [r["id"] for r in conn2.execute(
            "SELECT id FROM investigations WHERE event_id=? AND id!=?",
            (event_id, inv_id)).fetchall()]
        conn2.close()
        for sid in sibs:
            if rec_mod.delete_recording(sid):
                deleted.append(sid)
    if not deleted:
        raise HTTPException(404, "记录不存在")
    return {"deleted": deleted}
