"""监测 Agent：轮询断面时序，异常检测并生成预警事件（truth_source 未知，待溯源）。"""
from __future__ import annotations

import json
import re
from contextlib import closing
from statistics import median

import numpy as np

from ..db import get_conn
from ..engine.anomaly import detect, significant
from ..engine.topology import group_detections, upstream_most


METHODS = {"cusum", "ewma", "threesigma", "seasonal"}
_SCAN_ID_RE = re.compile(r"^evt_scan_(\d+)$")

# 合并后的事件严重度取组内最高:按最重的那条报
_SEV_RANK = {"low": 0, "medium": 1, "high": 2}


def _already_alerted(conn, station_id: str, indicator: str, onset: int,
                     window_s: int = 48 * 3600) -> bool:
    """该(断面,指标)在 onset 前后 48h 内是否已报过(任何状态)。

    合并后的事件只落在锚点断面上,其余断面记在 affected_stations 里,
    只看 events.station_id 会让下游断面在下一轮重复报警。
    """
    rows = conn.execute(
        "SELECT station_id, indicators, affected_stations FROM events "
        "WHERE onset_ts BETWEEN ? AND ?",
        (onset - window_s, onset + window_s)).fetchall()
    for row in rows:
        if row["affected_stations"]:
            pairs = {(a["station_id"], a["indicator"])
                     for a in json.loads(row["affected_stations"])}
        else:
            pairs = {(row["station_id"], i) for i in json.loads(row["indicators"])}
        if (station_id, indicator) in pairs:
            return True
    return False


def _dedupe_detections(detections: list[dict]) -> list[dict]:
    """同一(断面,指标)只留一条:取最早触发时刻与最高严重度。

    seasonal 等方法会对同一次抬升报出多个越限采样点,不去重会让波及清单按
    采样点膨胀(实测一次污染在 affected_stations 里存了 90 条),也让传播关系
    配对的开销随点数平方增长。
    """
    best: dict[tuple[str, str], dict] = {}
    for d in detections:
        key = (d["station_id"], d["indicator"])
        cur = best.get(key)
        if cur is None:
            best[key] = dict(d)
            continue
        if d["ts"] < cur["ts"]:
            cur["ts"], cur["zscore"] = d["ts"], d["zscore"]
        if _SEV_RANK.get(d["severity"], 0) > _SEV_RANK.get(cur["severity"], 0):
            cur["severity"] = d["severity"]
    return list(best.values())


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
    detections: list[dict] = []
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
                    if _already_alerted(conn, st["id"], ind, onset):
                        continue
                    # 先只收集,等全部序列扫完再按传播关系合并成事件
                    detections.append({
                        "station_id": st["id"], "indicator": ind, "ts": onset,
                        "severity": anomaly["severity"], "zscore": anomaly["zscore"],
                    })
                if incremental:
                    conn.execute(
                        "INSERT INTO monitor_cursors (station_id,indicator,last_ts) VALUES (?,?,?) "
                        "ON CONFLICT(station_id,indicator) DO UPDATE SET last_ts=excluded.last_ts",
                        (st["id"], ind, latest))

        # 一次污染会同时顶起多个断面,逐条建事件会在告警面板刷出好几条;
        # 按河网传播关系合并,一条污染只报一条事件(见 group_detections)
        for group in group_detections(ws, _dedupe_detections(detections)):
            stations = sorted({d["station_id"] for d in group})
            indicators = sorted({d["indicator"] for d in group})
            onset = min(d["ts"] for d in group)
            severity = max((d["severity"] for d in group),
                           key=lambda s: _SEV_RANK.get(s, 0))
            ev_id = f"evt_scan_{seq:03d}"
            seq += 1
            affected = [{"station_id": d["station_id"], "indicator": d["indicator"],
                         "ts": d["ts"], "severity": d["severity"]} for d in group]
            conn.execute(
                "INSERT INTO events "
                "(id,station_id,indicators,onset_ts,severity,etype,truth_source,status,"
                "affected_stations) VALUES (?,?,?,?,?,'detected',NULL,'open',?)",
                (ev_id, upstream_most(ws, stations), json.dumps(indicators), onset,
                 severity, json.dumps(affected, ensure_ascii=False)))
            result["events"].append({
                "id": ev_id, "station_id": upstream_most(ws, stations),
                "indicator": indicators[0], "indicators": indicators,
                "stations": stations, "n_stations": len(stations),
                "ts": onset, "severity": severity, "affected": affected,
                "zscore": group[0]["zscore"],
            })
    return result


def scan_for_events(db_path: str, ws: dict, window_h: int = 24,
                    method: str = "cusum") -> list[dict]:
    # Offline evaluations rewrite historical readings, so must not consume live cursors.
    return scan(db_path, ws, window_h, method, incremental=False)["events"]
