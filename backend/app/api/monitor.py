"""监测 Agent 状态与手动触发接口。"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..monitor_service import MONITOR_STATE, configure, scan_once

router = APIRouter(tags=["monitor"])


class MonitorConfig(BaseModel):
    enabled: bool | None = None
    interval_s: int | None = None
    window_h: int | None = None


@router.get("/monitor/status")
def monitor_status():
    """监测 Agent 运行状态(前端状态条轮询)。时间戳为毫秒 epoch。"""
    return {**MONITOR_STATE, "server_ms": int(time.time() * 1000)}


@router.post("/monitor/scan")
def monitor_scan():
    """立即执行一次扫描(不等定时器)。"""
    try:
        created = scan_once()
    except Exception as e:
        raise HTTPException(500, f"扫描失败:{e}") from e
    return {"created": created, "count": len(created),
            "duration_ms": MONITOR_STATE["last_duration_ms"]}


@router.post("/monitor/config")
def monitor_config(body: MonitorConfig):
    """调整监测开关/间隔/扫描窗口。"""
    state = configure(body.enabled, body.interval_s, body.window_h)
    return {**state, "server_ms": int(time.time() * 1000)}
