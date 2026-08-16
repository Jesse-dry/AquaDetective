"""数据生成器测试：可复现性、取值范围、事件注入。"""
import sqlite3
import tempfile

import numpy as np

from app.data.series_generator import (T0, alert_station_for, apply_event,
                                       baseline_series, generate_all, station_series)
from app.data.watershed_builder import build_watershed
from app.engine.topology import impact_matrix


def _inmem():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE readings (station_id TEXT, ts INTEGER, indicator TEXT, "
                 "value REAL, PRIMARY KEY (station_id, ts, indicator))")
    return conn


def test_reproducible():
    ws = build_watershed()
    t_min = np.arange(96 * 5) * 15
    st = ws["stations"][0]
    a = station_series(ws, st, "cod", t_min, np.random.default_rng(7), impact_matrix(ws))
    b = station_series(ws, st, "cod", t_min, np.random.default_rng(7), impact_matrix(ws))
    assert np.array_equal(a, b), "同 seed 必须完全一致"


def test_baseline_ranges():
    rng = np.random.default_rng(0)
    t_min = np.arange(96 * 5) * 15
    cod = baseline_series("cod", t_min, rng)
    ph = baseline_series("ph", t_min, rng)
    assert cod.min() > 5 and cod.max() < 60
    assert ph.min() >= 6.5 and ph.max() <= 8.0


def test_event_injection_visible():
    ws = build_watershed()
    conn = _inmem()
    days = 30
    t_min = np.arange(days * 1440) * 15
    generate_all(conn, ws, seed=1, days=days)
    rng = np.random.default_rng(1)
    spec = {"etype": "periodic", "source_id": "ent_02", "severity": "high",
            "onset_day": 10, "duration_d": 5}
    summary = apply_event(conn, ws, spec, t_min, rng)
    assert summary, "事件应影响断面"
    alert = alert_station_for(ws, "ent_02")
    before = conn.execute(
        "SELECT AVG(value) m FROM readings WHERE station_id=? AND indicator='cr6' "
        "AND ts < ?", (alert, T0 + 10 * 86400)).fetchone()[0]
    after = conn.execute(
        "SELECT MAX(value) m FROM readings WHERE station_id=? AND indicator='cr6' "
        "AND ts >= ?", (alert, T0 + 10 * 86400)).fetchone()[0]
    assert after > before * 3, "事件后 Cr6 应显著抬升"
    conn.close()
