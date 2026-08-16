"""时序数据接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..agents import tools
from ..context import get_db_path, get_watershed

router = APIRouter(tags=["series"])


@router.get("/series")
def series(station: str, indicator: str,
           from_: int | None = Query(None, alias="from"),
           to: int | None = Query(None, alias="to"),
           step: int = 1):
    ws = get_watershed()
    if not any(s["id"] == station for s in ws["stations"]):
        raise HTTPException(404, "断面不存在")
    rows = tools.query_station_series(get_db_path(), station, indicator,
                                      from_ or 0, limit=200000)
    rows = [r for r in rows if (to is None or r["ts"] <= to)]
    if step > 1:
        rows = rows[::step]
    return {"station": station, "indicator": indicator, "count": len(rows), "data": rows}
