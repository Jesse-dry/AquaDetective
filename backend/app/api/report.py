"""调查报告接口（Markdown）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from ..agents import recorder

router = APIRouter(tags=["report"])


@router.get("/investigations/{inv_id}/report")
def get_report(inv_id: str):
    p = recorder.report_path(inv_id)
    if p is None:
        raise HTTPException(404, "报告尚未生成")
    return PlainTextResponse(p.read_text(encoding="utf-8"),
                             media_type="text/markdown; charset=utf-8")
