"""监测 Agent：轮询断面时序，异常检测并生成预警事件（truth_source 未知，待溯源）。"""
from __future__ import annotations

import json
from uuid import uuid4

import numpy as np

from ..db import get_conn
from ..engine.anomaly import detect


def scan_for_events(db_path: str, ws: dict, window_h: int = 24, method: str = "cusum") -> list[dict]:
    conn = get_conn(db_path)
    now_max = conn.execute("SELECT MAX(ts) FROM readings").fetchone()[0]
    since = now_max - window_h * 3600
    created = []
    for st in ws["stations"]:
        for ind in st["indicators"]:
            rows = conn.execute(
                "SELECT ts, value FROM readings WHERE station_id=? AND indicator=? AND ts>=? "
                "ORDER BY ts", (st["id"], ind, since)).fetchall()
            if len(rows) < 48:
                continue
            ts = np.array([r["ts"] for r in rows], dtype=np.int64)
            x = np.array([r["value"] for r in rows], dtype=float)
            anoms = detect(x, ts, method=method)
            severe = [a for a in anoms if a["severity"] in ("medium", "high")]
            if not severe:
                continue
            dup = conn.execute(
                "SELECT COUNT(*) c FROM events WHERE station_id=? AND status='open' AND onset_ts > ?",
                (st["id"], now_max - 48 * 3600)).fetchone()["c"]
            if dup:
                continue
            ev_id = f"evt_{uuid4().hex[:6]}"
            a = severe[0]
            conn.execute(
                "INSERT INTO events (id,station_id,indicators,onset_ts,severity,etype,truth_source,status) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (ev_id, st["id"], json.dumps([ind]), int(a["ts"]), a["severity"],
                 "detected", None, "open"))
            created.append({"id": ev_id, "station_id": st["id"], "indicator": ind,
                            "ts": int(a["ts"]), "severity": a["severity"],
                            "zscore": a["zscore"]})
    conn.commit()
    conn.close()
    return created
