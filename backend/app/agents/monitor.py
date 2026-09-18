"""监测 Agent：轮询断面时序，异常检测并生成预警事件（truth_source 未知，待溯源）。"""
from __future__ import annotations

import json
import re
from contextlib import closing
from statistics import median

import numpy as np

from ..db import get_conn
from ..engine.anomaly import detect, significant


METHODS = {"cusum", "ewma", "threesigma", "seasonal"}
_SCAN_ID_RE = re.compile(r"^evt_scan_(\d+)$")


def _next_scan_seq(conn) -> int:
    rows = conn.execute("SELECT id FROM events WHERE id LIKE 'evt_scan_%'").fetchall()
    return max((int(m.group(1)) for row in rows
                if (m := _SCAN_ID_RE.match(row["id"]))), default=0) + 1


def scan(db_path: str, ws: dict, window_h: int = 24, method: str = "cusum", *,
         incremental: bool = True) -> dict:
    """Scan each series at its own latest timestamp; timestamps are epoch seconds.

    Extend short windows for low-frequency observations. Persist progress and
    events in one transaction so concurrent scans cannot duplicate alerts.
    """
    if method not in METHODS or not 1 <= window_h <= 2160:
        raise ValueError("Invalid monitoring method or window (1..2160 hours)")
    result = {"events": [], "scanned_series": 0, "unchanged_series": 0,
              "insufficient_series": 0, "extended_series": 0, "latest_data_ts": None}
    with closing(get_conn(db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        seq = _next_scan_seq(conn)
        for st in ws["stations"]:
            for ind in st["indicators"]:
                tail = conn.execute(
                    "SELECT ts,value FROM readings WHERE station_id=? AND indicator=? "
                    "ORDER BY ts DESC LIMIT 48", (st["id"], ind)).fetchall()
                if not tail:
                    result["insufficient_series"] += 1
                    continue
                latest = int(tail[0]["ts"])
                result["latest_data_ts"] = max(result["latest_data_ts"] or latest, latest)
                cursor = conn.execute(
                    "SELECT last_ts FROM monitor_cursors WHERE station_id=? AND indicator=?",
                    (st["id"], ind)).fetchone() if incremental else None
                if cursor and cursor["last_ts"] >= latest:
                    result["unchanged_series"] += 1
                    continue
                intervals = [a["ts"] - b["ts"] for a, b in zip(tail, tail[1:])]
                interval = median(intervals) if intervals else st.get("interval_min", 15) * 60
                period = max(1, round(86400 / max(interval, 1)))
                minimum = 144 if method == "threesigma" else 48
                if method == "seasonal":
                    minimum = max(minimum, period * 8)
                since = latest - window_h * 3600
                rows = conn.execute(
                    "SELECT ts,value FROM readings WHERE station_id=? AND indicator=? "
                    "AND ts>=? ORDER BY ts", (st["id"], ind, since)).fetchall()
                if len(rows) < minimum:
                    rows = list(reversed(conn.execute(
                        "SELECT ts,value FROM readings WHERE station_id=? AND indicator=? "
                        "ORDER BY ts DESC LIMIT ?", (st["id"], ind, minimum)).fetchall()))
                    if rows and rows[0]["ts"] < since:
                        result["extended_series"] += 1
                ts = np.array([r["ts"] for r in rows], dtype=np.int64)
                x = np.array([r["value"] for r in rows], dtype=float)
                finite = np.isfinite(x)
                ts, x = ts[finite], x[finite]
                if len(x) < minimum:
                    result["insufficient_series"] += 1
                    continue
                kw = {"period": period} if method == "seasonal" else {}
                anomalies = significant(detect(x, ts, method=method, **kw), x)
                result["scanned_series"] += 1
                for anomaly in anomalies:
                    onset = int(anomaly["ts"])
                    if anomaly["severity"] not in ("medium", "high"):
                        continue
                    if cursor and onset <= cursor["last_ts"]:
                        continue
                    if method == "seasonal" and onset < int(ts[min(period * 7, len(ts) - 1)]):
                        continue
                    # Suppress the same indicator within 48h, even after resolution.
                    existing = conn.execute(
                        "SELECT indicators FROM events WHERE station_id=? "
                        "AND onset_ts BETWEEN ? AND ?",
                        (st["id"], onset - 48 * 3600, onset + 48 * 3600)).fetchall()
                    if any(ind in json.loads(row["indicators"]) for row in existing):
                        continue
                    ev_id = f"evt_scan_{seq:03d}"
                    seq += 1
                    conn.execute(
                        "INSERT INTO events "
                        "(id,station_id,indicators,onset_ts,severity,etype,truth_source,status) "
                        "VALUES (?,?,?,?,?,'detected',NULL,'open')",
                        (ev_id, st["id"], json.dumps([ind]), onset, anomaly["severity"]))
                    result["events"].append({
                        "id": ev_id, "station_id": st["id"], "indicator": ind,
                        "ts": onset, "severity": anomaly["severity"],
                        "zscore": anomaly["zscore"],
                    })
                if incremental:
                    conn.execute(
                        "INSERT INTO monitor_cursors (station_id,indicator,last_ts) VALUES (?,?,?) "
                        "ON CONFLICT(station_id,indicator) DO UPDATE SET last_ts=excluded.last_ts",
                        (st["id"], ind, latest))
    return result


def scan_for_events(db_path: str, ws: dict, window_h: int = 24,
                    method: str = "cusum") -> list[dict]:
    # Offline evaluations rewrite historical readings, so must not consume live cursors.
    return scan(db_path, ws, window_h, method, incremental=False)["events"]
