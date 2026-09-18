"""Manual monitoring trigger and scheduler status."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from ..monitoring import ScanBusy
from .time import epoch_ms

router = APIRouter(tags=["monitor"])
logger = logging.getLogger(__name__)


def public_result(result):
    return {**result, "created_count": len(result["events"]),
            "latest_data_ts": epoch_ms(result["latest_data_ts"]),
            "events": [{**event, "ts": epoch_ms(event["ts"])} for event in result["events"]]}


@router.post("/monitor/scan")
def scan_now(request: Request):
    try:
        return public_result(request.app.state.monitor.run())
    except ScanBusy:
        raise HTTPException(409, "Monitoring scan already running") from None
    except Exception:
        logger.exception("Manual monitoring scan failed")
        raise HTTPException(500, "Monitoring scan failed; check server logs") from None


@router.get("/monitor/status")
def monitor_status(request: Request):
    status = request.app.state.monitor.status()
    return {**status,
            "last_started_at": epoch_ms(status["last_started_at"]),
            "last_finished_at": epoch_ms(status["last_finished_at"]),
            "last_result": public_result(status["last_result"]) if status["last_result"] else None}
