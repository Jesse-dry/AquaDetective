"""监测 Agent：轮询断面时序，异常检测并生成预警事件（truth_source 未知，待溯源）。"""
from __future__ import annotations

import json
import re

import numpy as np

from ..db import get_conn
from ..engine.anomaly import detect, significant

_SCAN_ID_RE = re.compile(r"^evt_scan_(\d+)$")


def _next_scan_seq(conn) -> int:
    """下一个可读的事件编号(evt_scan_001 递增),避免 uuid 乱码。"""
    rows = conn.execute("SELECT id FROM events WHERE id LIKE 'evt_scan_%'").fetchall()
    nums = [int(m.group(1)) for r in rows if (m := _SCAN_ID_RE.match(r["id"]))]
    return max(nums, default=0) + 1


def scan_for_events(db_path: str, ws: dict, window_h: int = 24, method: str = "cusum") -> list[dict]:
    """扫描最近 window_h 小时的断面时序,为异常断面生成待溯源事件。

    检出需通过 `significant` 门槛(排除量化噪声误报),且同断面 48h 内已有
    未处置事件时跳过(一次污染不在同一断面重复报警)。
    """
    conn = get_conn(db_path)
    now_max = conn.execute("SELECT MAX(ts) FROM readings").fetchone()[0]
    since = now_max - window_h * 3600
    seq = _next_scan_seq(conn)
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
            severe = significant([a for a in anoms if a["severity"] in ("medium", "high")], x)
            if not severe:
                continue
            dup = conn.execute(
                "SELECT COUNT(*) c FROM events WHERE station_id=? AND status='open' AND onset_ts > ?",
                (st["id"], now_max - 48 * 3600)).fetchone()["c"]
            if dup:
                continue
            ev_id = f"evt_scan_{seq:03d}"
            seq += 1
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
