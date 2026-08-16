"""WebSocket：推理过程流式推送。"""
from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])

# inv_id -> {"queue": asyncio.Queue, "done": threading.Event}
INVESTIGATIONS: dict[str, dict] = {}


@router.websocket("/ws")
async def ws_stream(websocket: WebSocket, investigation_id: str = ""):
    await websocket.accept()
    reg = INVESTIGATIONS.get(investigation_id)
    if reg is None:
        await websocket.send_json({"type": "error", "data": {"reason": "调查不存在"}})
        await websocket.close()
        return
    queue: asyncio.Queue = reg["queue"]
    done: threading.Event = reg["done"]
    await websocket.send_json({"type": "connected", "data": {"investigation_id": investigation_id}})
    try:
        while True:
            if done.is_set() and queue.empty():
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=0.5)
                await websocket.send_json(msg)
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        pass
    finally:
        INVESTIGATIONS.pop(investigation_id, None)
        await websocket.close()
