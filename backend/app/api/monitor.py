"""Manual monitoring trigger and scheduler status."""
from __future__ import annotations

import logging
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..monitoring import ScanBusy
from .time import epoch_ms

router = APIRouter(tags=["monitor"])
logger = logging.getLogger(__name__)


class MonitorConfig(BaseModel):
    enabled: bool | None = None
    interval_s: int | None = Field(default=None, ge=10, le=86400)
    window_h: int | None = Field(default=None, ge=1, le=2160)
    method: Literal["cusum", "ewma", "threesigma", "seasonal"] | None = None


def public_result(result):
    return {**result, "created_count": len(result["events"]),
            "latest_data_ts": epoch_ms(result["latest_data_ts"]),
            "events": [{**event, "ts": epoch_ms(event["ts"])} for event in result["events"]]}


@router.post("/monitor/scan")
def scan_now(request: Request):
    try:
        service = request.app.state.monitor
        result = public_result(service.run())
        return {**result, "created": result["events"], "count": result["created_count"],
                "duration_ms": service.status()["last_duration_ms"]}
    except ScanBusy:
        raise HTTPException(409, "Monitoring scan already running") from None
    except Exception:
        logger.exception("Manual monitoring scan failed")
        raise HTTPException(500, "Monitoring scan failed; check server logs") from None


@router.get("/monitor/status")
def monitor_status(request: Request):
    status = request.app.state.monitor.status()
    next_scan_ms = epoch_ms(status.pop("next_scan_at"))
    return {**status,
            "last_started_at": epoch_ms(status["last_started_at"]),
            "last_finished_at": epoch_ms(status["last_finished_at"]),
            "last_result": public_result(status["last_result"]) if status["last_result"] else None,
            "last_scan_ms": epoch_ms(status["last_finished_at"]),
            "next_scan_ms": next_scan_ms,
            "recent": [{**event, "ts": epoch_ms(event["ts"])} for event in status["recent"]],
            "server_ms": int(time.time() * 1000)}


@router.post("/monitor/config")
def configure_monitor(body: MonitorConfig, request: Request):
    request.app.state.monitor.configure(**body.model_dump(exclude_none=True))
    return monitor_status(request)
