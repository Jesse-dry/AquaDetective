"""事件观测与评测真值隔离测试。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from app.agents import tools
from app.data.event_observations import upsert_event_observation
from app.data.watershed_builder import build_watershed
from app.db import get_conn, init_db


def _insert_event(conn, event_id: str, station_id: str, truth_source: str) -> None:
    conn.execute(
        "INSERT INTO events "
        "(id,station_id,indicators,onset_ts,severity,etype,truth_source,status) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (event_id, station_id, json.dumps(["cr6"]), 1, "high", "periodic",
         truth_source, "open"),
    )
    conn.commit()


def test_persisted_observation_does_not_change_with_truth_label():
    ws = build_watershed()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        conn = get_conn(db_path)
        init_db(conn)
        _insert_event(conn, "evt_test", "st_02", "ent_02")
        upsert_event_observation(conn, ws, "evt_test", "st_02", "ent_02", 7)
        conn.commit()
        conn.close()

        eem_before = tools.observed_eem_at(db_path, ws, "st_02", "evt_test")
        pollutants_before = tools.match_pollutants_at(db_path, ws, "st_02", "evt_test")

        conn = get_conn(db_path)
        conn.execute("UPDATE events SET truth_source='ent_09' WHERE id='evt_test'")
        conn.commit()
        conn.close()

        eem_after = tools.observed_eem_at(db_path, ws, "st_02", "evt_test")
        pollutants_after = tools.match_pollutants_at(db_path, ws, "st_02", "evt_test")
        assert eem_before == eem_after
        assert pollutants_before == pollutants_after


def test_missing_observation_cannot_reveal_truth_source():
    ws = build_watershed()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        conn = get_conn(db_path)
        init_db(conn)
        _insert_event(conn, "evt_test", "st_02", "ent_02")
        conn.close()

        event_eem = tools.observed_eem_at(db_path, ws, "st_02", "evt_test", seed=17)
        background_eem = tools.observed_eem_at(db_path, ws, "st_02", seed=17)
        assert np.array_equal(np.asarray(event_eem["eem"]), np.asarray(background_eem["eem"]))
