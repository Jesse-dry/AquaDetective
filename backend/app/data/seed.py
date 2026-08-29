"""seed：一键构建"世界"（流域 + 90 天时序 + 3 条预置污染事件）。

用法: python -m app.data.seed
同 seed 可完全复现；数据库存在且非空时自动跳过（重建用 --force）。
"""
from __future__ import annotations

import sys
import time

import numpy as np

from ..config import settings
from ..db import db_is_empty, get_conn, init_db
from . import watershed_builder
from .event_observations import backfill_event_observations, upsert_event_observation
from .series_generator import T0, alert_station_for, apply_event, generate_all

# 预置演示事件（Ground Truth 已知）
SCRIPTED_EVENTS = [
    {
        "id": "evt_001", "etype": "periodic", "source_id": "ent_02",
        "severity": "high", "onset_day": 45, "duration_d": 10,
        "indicators": ["cr6", "cod"], "title": "耀光金属夜间偷排（电镀废水）",
    },
    {
        "id": "evt_002", "etype": "sudden", "source_id": "ent_09",
        "severity": "high", "onset_day": 60, "duration_d": 2, "mass_kg": 80,
        "indicators": ["cod", "ammonia"], "title": "恒泰精细化工泄漏（突发）",
    },
    {
        "id": "evt_003", "etype": "gradual", "source_id": "ent_15",
        "severity": "medium", "onset_day": 20, "duration_d": 30,
        "indicators": ["cod", "ammonia"], "title": "城东污水处理厂处理能力下降（渐变）",
    },
]


def run(settings_=settings, days: int = 90, seed: int | None = None) -> dict:
    t0 = time.time()
    settings_.ensure_dirs()
    seed = settings_.seed if seed is None else seed
    ws = watershed_builder.save_watershed(settings_.watershed_config_abs)
    conn = get_conn(str(settings_.db_path_abs))
    init_db(conn)
    for tbl in ["readings", "event_observations", "events", "investigations", "fingerprints",
                "enterprises", "stations", "edges", "nodes"]:
        conn.execute(f"DELETE FROM {tbl}")
    conn.executemany(
        "INSERT INTO nodes (id,name,kind,x,y,flow,velocity,k) VALUES (?,?,?,?,?,?,?,?)",
        [(n["id"], n["name"], n["kind"], n["x"], n["y"], n["flow"], n["velocity"], n["k"])
         for n in ws["nodes"]])
    conn.executemany(
        "INSERT INTO edges (from_node,to_node,distance_m) VALUES (?,?,?)",
        [(e["from_node"], e["to_node"], e["distance_m"]) for e in ws["edges"]])
    conn.executemany(
        "INSERT INTO stations (id,node_id,interval_min,indicators) VALUES (?,?,?,?)",
        [(s["id"], s["node_id"], s["interval_min"],
          __import__("json").dumps(s["indicators"])) for s in ws["stations"]])
    conn.executemany(
        "INSERT INTO enterprises (id,name,industry,node_id,discharge_pattern) VALUES (?,?,?,?,?)",
        [(e["id"], e["name"], e["industry"], e["node_id"],
          __import__("json").dumps(e["discharge_pattern"])) for e in ws["enterprises"]])
    conn.executemany(
        "INSERT INTO fingerprints (enterprise_id,spectrum,pollutants) VALUES (?,?,?)",
        [(f["enterprise_id"], __import__("json").dumps(f["spectrum"]),
          __import__("json").dumps(f["pollutants"])) for f in ws["fingerprints"]])
    conn.commit()

    n_rows = generate_all(conn, ws, seed=seed, days=days)
    rng = np.random.default_rng(seed)
    n_min = days * 1440
    t_min = np.arange(n_min) * 15
    event_rows = []
    for ev in SCRIPTED_EVENTS:
        spec = {k: v for k, v in ev.items() if k not in ("id", "indicators", "title")}
        summary = apply_event(conn, ws, spec, t_min, rng)
        alert = alert_station_for(ws, ev["source_id"])
        event_rows.append((
            ev["id"], alert, __import__("json").dumps(ev["indicators"]),
            T0 + ev["onset_day"] * 86400, ev["severity"], ev["etype"],
            ev["source_id"], "open"))
        print(f"  [event] {ev['id']} {ev['title']} -> 首达断面 {alert} "
              f"(峰值增量 {max(s['peak_delta'] for s in summary)} mg/L)")
    conn.executemany(
        "INSERT INTO events (id,station_id,indicators,onset_ts,severity,etype,truth_source,status) "
        "VALUES (?,?,?,?,?,?,?,?)", event_rows)
    for ev, row in zip(SCRIPTED_EVENTS, event_rows):
        upsert_event_observation(
            conn, ws, ev["id"], row[1], ev["source_id"], seed)
    conn.commit()
    conn.close()
    print(f"done in {time.time()-t0:.1f}s: readings={n_rows:,} events={len(event_rows)}")
    return {"readings": n_rows, "events": len(event_rows)}


def ensure_db(settings_=settings) -> None:
    """服务启动时调用：库不存在/为空则构建。"""
    settings_.ensure_dirs()
    conn = get_conn(str(settings_.db_path_abs))
    init_db(conn)
    if db_is_empty(conn):
        conn.close()
        run(settings_)
    else:
        ws = watershed_builder.load_watershed(settings_.watershed_config_abs)
        backfill_event_observations(conn, ws, settings_.seed)
        conn.close()


if __name__ == "__main__":
    if "--force" in sys.argv:
        # 强制重建：删库重来
        settings.db_path_abs.unlink(missing_ok=True)
        for suf in ("-wal", "-shm"):
            settings.db_path_abs.with_name(settings.db_path_abs.name + suf).unlink(missing_ok=True)
    run()
