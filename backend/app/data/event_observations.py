"""模拟事件观测的生成与持久化。

真值仅在本数据生成模块中用于合成观测。调查引擎只读取 event_observations，
不得通过 events.truth_source 重建证据。
"""
from __future__ import annotations

import hashlib
import json

from .fingerprint_lib import observed_eem, observed_pollutants


def _event_seed(base_seed: int, event_id: str) -> int:
    digest = hashlib.sha256(event_id.encode("utf-8")).digest()
    return (base_seed + int.from_bytes(digest[:4], "big")) % (2**32)


def build_event_observation(watershed: dict, event_id: str, station_id: str,
                            source_id: str, base_seed: int) -> dict:
    """由模拟真值生成一次不可变现场观测，返回内容不包含来源标签。"""
    seed = _event_seed(base_seed, event_id)
    eem = observed_eem(watershed, station_id, seed=seed, event_source=source_id)
    return {
        "event_id": event_id,
        "station_id": station_id,
        "eem": {key: eem[key] for key in ("lex", "lem", "eem")},
        "pollutants": observed_pollutants(
            watershed, station_id, seed=seed + 1, event_source=source_id),
    }


def upsert_event_observation(conn, watershed: dict, event_id: str, station_id: str,
                             source_id: str, base_seed: int) -> dict:
    observation = build_event_observation(
        watershed, event_id, station_id, source_id, base_seed)
    conn.execute(
        "INSERT OR REPLACE INTO event_observations "
        "(event_id,station_id,eem,pollutants) VALUES (?,?,?,?)",
        (event_id, station_id,
         json.dumps(observation["eem"], ensure_ascii=False),
         json.dumps(observation["pollutants"], ensure_ascii=False)),
    )
    return observation


def load_event_observation(conn, event_id: str) -> dict | None:
    row = conn.execute(
        "SELECT event_id,station_id,eem,pollutants FROM event_observations WHERE event_id=?",
        (event_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "event_id": row["event_id"],
        "station_id": row["station_id"],
        "eem": json.loads(row["eem"]),
        "pollutants": json.loads(row["pollutants"]),
    }


def backfill_event_observations(conn, watershed: dict, base_seed: int) -> int:
    """为旧版模拟数据库补齐观测；真实事件（无 truth_source）保持缺省。"""
    rows = conn.execute(
        "SELECT e.id,e.station_id,e.truth_source FROM events e "
        "LEFT JOIN event_observations o ON o.event_id=e.id "
        "WHERE o.event_id IS NULL AND e.truth_source IS NOT NULL"
    ).fetchall()
    for row in rows:
        upsert_event_observation(
            conn, watershed, row["id"], row["station_id"], row["truth_source"], base_seed)
    if rows:
        conn.commit()
    return len(rows)
