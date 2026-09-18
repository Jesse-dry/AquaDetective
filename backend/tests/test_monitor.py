"""Monitoring: real detection, persistent deduplication, API and lifecycle."""
from concurrent.futures import ThreadPoolExecutor
import importlib
import threading

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.agents import monitor
from app.db import get_conn, init_db
from app.monitoring import MonitorService, ScanBusy

T0 = 1_750_000_000


@pytest.fixture
def source(tmp_path):
    db = str(tmp_path / "monitor.db")
    conn = get_conn(db)
    init_db(conn)
    conn.close()
    ws = {"stations": [{"id": "st_01", "indicators": ["cod"], "interval_min": 15}]}
    return db, ws


def readings(db, *, station="st_01", indicator="cod", interval=900, count=96,
             start=T0, spike=True):
    values = 10 + np.sin(np.arange(count)) * 0.1 if spike else np.full(count, 10.0)
    if spike:
        values[-8:] = 35
    conn = get_conn(db)
    conn.executemany("INSERT OR REPLACE INTO readings VALUES (?,?,?,?)", [
        (station, start + i * interval, indicator, float(value))
        for i, value in enumerate(values)])
    conn.commit()
    conn.close()


def test_empty_and_short_data_are_reported(source):
    db, ws = source
    result = monitor.scan(db, ws)
    assert result["events"] == []
    assert result["latest_data_ts"] is None
    assert result["insufficient_series"] == 1
    readings(db, count=12)
    assert monitor.scan(db, ws)["insufficient_series"] == 1
    readings(db)
    assert len(monitor.scan(db, ws)["events"]) == 1


@pytest.mark.parametrize("status", ["open", "investigating", "resolved"])
def test_detection_is_persisted_and_not_repeated_after_restart(source, status):
    db, ws = source
    readings(db)
    events = monitor.scan(db, ws)["events"]
    assert len(events) == 1
    conn = get_conn(db)
    row = conn.execute("SELECT * FROM events").fetchone()
    assert row["etype"] == "detected"
    assert row["truth_source"] is None
    conn.execute("UPDATE events SET status=?", (status,))
    conn.commit()
    conn.close()
    restarted = MonitorService(db, lambda: ws)
    assert restarted.run()["events"] == []
    assert restarted.status()["last_result"]["unchanged_series"] == 1
    # Even an offline rescan without cursors cannot duplicate the resolved alert.
    assert monitor.scan_for_events(db, ws) == []


def test_four_hour_data_uses_additional_history(source):
    db, ws = source
    readings(db, interval=4 * 3600, count=48)
    result = monitor.scan(db, ws)
    assert result["extended_series"] == 1
    assert result["scanned_series"] == 1
    assert len(result["events"]) == 1


def test_indicators_and_station_clocks_are_independent(source):
    db, ws = source
    ws["stations"][0]["indicators"].append("ammonia")
    ws["stations"].append({"id": "st_02", "indicators": ["cod"]})
    readings(db)
    readings(db, indicator="ammonia")
    readings(db, station="st_02", start=T0 + 30 * 86400)
    result = monitor.scan(db, ws)
    assert len(result["events"]) == 3
    assert result["scanned_series"] == 3


def test_new_data_can_create_a_later_alert(source):
    db, ws = source
    readings(db)
    assert len(monitor.scan(db, ws)["events"]) == 1
    readings(db, start=T0 + 4 * 86400)
    assert len(monitor.scan(db, ws)["events"]) == 1


def test_concurrent_scans_create_only_one_alert(source):
    db, ws = source
    readings(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: monitor.scan(db, ws), range(2)))
    assert sum(len(result["events"]) for result in results) == 1


def test_failed_scan_rolls_back_events_and_progress(source, monkeypatch):
    db, ws = source
    readings(db)
    readings(db, indicator="ammonia")
    ws["stations"][0]["indicators"].append("ammonia")
    original = monitor.detect
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("detector unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(monitor, "detect", fail_second)
    with pytest.raises(RuntimeError):
        monitor.scan(db, ws)
    conn = get_conn(db)
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM monitor_cursors").fetchone()[0] == 0
    conn.close()
    monkeypatch.setattr(monitor, "detect", original)
    assert len(monitor.scan(db, ws)["events"]) == 2


@pytest.mark.parametrize("method", ["cusum", "ewma", "threesigma", "seasonal"])
def test_supported_methods_accept_low_frequency_baseline(source, method):
    db, ws = source
    readings(db, interval=4 * 3600, count=160, spike=False)
    result = monitor.scan(db, ws, method=method)
    assert result["scanned_series"] == 1
    assert result["events"] == []


def test_offline_evaluation_does_not_consume_live_progress(source):
    db, ws = source
    readings(db)
    assert len(monitor.scan_for_events(db, ws)) == 1
    conn = get_conn(db)
    assert conn.execute("SELECT COUNT(*) FROM monitor_cursors").fetchone()[0] == 0
    conn.close()


def test_api_creates_visible_events_and_uses_milliseconds(source, monkeypatch):
    db, ws = source
    readings(db)
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "ensure_db", lambda _: None)
    monkeypatch.setattr(main, "get_db_path", lambda: db)
    monkeypatch.setattr(main, "get_watershed", lambda: ws)
    monkeypatch.setattr(main.settings, "monitor_enabled", False)
    monkeypatch.setattr(main.investigate, "get_db_path", lambda: db)
    with TestClient(main.app) as client:
        assert client.get("/api/v1/monitor/status").json()["last_result"] is None
        response = client.post("/api/v1/monitor/scan")
        assert response.status_code == 200
        result = response.json()
        assert result["created_count"] == 1
        assert result["latest_data_ts"] == (T0 + 95 * 900) * 1000
        event = client.get("/api/v1/events").json()[0]
        assert event["id"] == result["events"][0]["id"]
        assert event["onset_ts"] == result["events"][0]["ts"]
        status = client.get("/api/v1/monitor/status").json()
        assert status["last_finished_at"] > 1e12
        assert status["last_result"] == {key: result[key] for key in status["last_result"]}
        assert result["created"] == result["events"]
        assert result["count"] == result["created_count"]
        assert status["recent"][0]["ts"] == event["onset_ts"]
        assert event["id"] == "evt_scan_001"
        assert status["scheduler_running"]
        enabled = client.post("/api/v1/monitor/config", json={"enabled": True, "interval_s": 10})
        assert enabled.status_code == 200
        assert enabled.json()["next_scan_ms"] > enabled.json()["server_ms"]
        paused = client.post("/api/v1/monitor/config", json={"enabled": False}).json()
        assert paused["next_scan_ms"] is None
        assert not paused["enabled"]
        for config in ({"interval_s": 0}, {"window_h": 0}, {"method": "unknown"}):
            assert client.post("/api/v1/monitor/config", json=config).status_code == 422
        service = main.app.state.monitor
        service._lock.acquire()
        try:
            assert client.post("/api/v1/monitor/scan").status_code == 409
        finally:
            service._lock.release()


def test_scheduler_recovers_after_error_and_stops(source, monkeypatch):
    db, ws = source
    readings(db)
    module = importlib.import_module("app.monitoring")
    original = module.scan
    finished = threading.Event()
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary failure")
        result = original(*args, **kwargs)
        finished.set()
        return result

    monkeypatch.setattr(module, "scan", fail_once)
    service = MonitorService(db, lambda: ws, enabled=True, interval_s=0.01)
    service.start()
    try:
        assert finished.wait(5)
    finally:
        service.stop()
    assert not service._thread.is_alive()
    assert service.status()["last_error"] is None
    assert not service.status()["running"]


def test_scan_failure_releases_lock_and_exposes_status(source, monkeypatch):
    db, ws = source
    service = MonitorService(db, lambda: ws)
    module = importlib.import_module("app.monitoring")

    def fail(*args):
        raise RuntimeError("failure")

    monkeypatch.setattr(module, "scan", fail)
    with pytest.raises(RuntimeError):
        service.run()
    assert service.status()["last_error"]
    assert not service.status()["running"]
    assert service._lock.acquire(blocking=False)
    try:
        with pytest.raises(ScanBusy):
            service.run()
    finally:
        service._lock.release()


def test_scheduler_can_be_enabled_after_disabled_start(source, monkeypatch):
    db, ws = source
    service = MonitorService(db, lambda: ws, enabled=False, interval_s=0.01)
    scanned = threading.Event()
    module = importlib.import_module("app.monitoring")
    original = module.scan

    def record_scan(*args, **kwargs):
        result = original(*args, **kwargs)
        scanned.set()
        return result

    monkeypatch.setattr(module, "scan", record_scan)
    service.start()
    try:
        assert not scanned.wait(0.15)
        service.configure(enabled=True)
        assert scanned.wait(2)
        service.configure(enabled=False)
        assert service.status()["next_scan_at"] is None
    finally:
        service.stop()
