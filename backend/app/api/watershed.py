"""流域/断面/企业/指纹 只读接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..agents import tools
from ..context import get_watershed

router = APIRouter(tags=["watershed"])


@router.get("/watershed")
def get_watershed_full():
    return get_watershed()


@router.get("/watershed/enterprises/{ent_id}/fingerprint")
def enterprise_fingerprint(ent_id: str):
    ws = get_watershed()
    ent = tools.get_enterprise_profile(ws, ent_id)
    if not ent:
        raise HTTPException(404, "企业不存在")
    fp = ent.pop("fingerprint", None)
    return {"enterprise": ent, "fingerprint": fp}


@router.get("/stations/{station_id}/eem")
def station_eem(station_id: str, event_id: str | None = None, seed: int = 7):
    from ..context import get_db_path
    ws = get_watershed()
    if not any(s["id"] == station_id for s in ws["stations"]):
        raise HTTPException(404, "断面不存在")
    return tools.observed_eem_at(get_db_path(), ws, station_id, event_id, seed=seed)
