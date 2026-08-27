"""时序数据接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..agents import tools
from ..context import get_db_path, get_watershed
from .time import epoch_ms, epoch_seconds

router = APIRouter(tags=["series"])


@router.get("/series")
def series(station: str, indicator: str,
           from_: int | None = Query(None, alias="from"),
           to: int | None = Query(None, alias="to"),
           step: int = 1):
    if step < 1:
        raise HTTPException(400, "step 必须为正整数")
    ws = get_watershed()
    if not any(s["id"] == station for s in ws["stations"]):
        raise HTTPException(404, "断面不存在")
    from_s = epoch_seconds(from_)
    to_s = None if to is None else epoch_seconds(to)
    rows = tools.query_station_series(get_db_path(), station, indicator,
                                      from_s, limit=200000)
    rows = [
        {**row, "ts": epoch_ms(row["ts"])}
        for row in rows
        if to_s is None or row["ts"] <= to_s
    ]
    if step > 1:
        rows = rows[::step]
    return {"station": station, "indicator": indicator, "count": len(rows), "data": rows}
