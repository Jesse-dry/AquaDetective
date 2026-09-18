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
    # 本例考的是 API 契约(毫秒时间戳/计数/409/参数校验),与默认检测方法无关;
    # 数据只有 96 个点,季节基线需要 8 天(768 点)历史,故显式固定为 cusum
    monkeypatch.setattr(main.settings, "monitor_method", "cusum")
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


def test_dedupe_detections_keeps_one_per_series():
    """同一(断面,指标)只留一条,取最早触发时刻与最高严重度。

    seasonal 会对同一次抬升报出多个越限采样点;不去重会让 affected_stations
    按采样点膨胀(实测一次污染存了 90 条),传播关系配对开销也随点数平方增长。
    """
    dets = [
        {"station_id": "st_01", "indicator": "cod", "ts": 300, "severity": "medium", "zscore": 3.0},
        {"station_id": "st_01", "indicator": "cod", "ts": 100, "severity": "high", "zscore": 9.0},
        {"station_id": "st_01", "indicator": "cod", "ts": 200, "severity": "low", "zscore": 1.0},
        {"station_id": "st_02", "indicator": "cod", "ts": 150, "severity": "medium", "zscore": 4.0},
    ]
    out = monitor._dedupe_detections(dets)
    assert len(out) == 2, f"应每个(断面,指标)一条,实际 {out}"
    st1 = next(d for d in out if d["station_id"] == "st_01")
    assert st1["ts"] == 100, "应取最早触发时刻"
    assert st1["severity"] == "high", "应取最高严重度"


def test_reset_status_clears_counters(source):
    """世界重建后统计须清零:否则状态条继续显示上一个世界的检出与累计数。

    这些计数只在内存里,重建世界不会动它们;而 evt_scan_NNN 编号会复用,
    残留记录看起来就像同一条事件重复报了多次。
    """
    db, ws = source
    readings(db)
    # 数据只有 96 点,季节基线需要 8 天历史;本例考的是统计清零,固定用 cusum
    service = MonitorService(db, lambda: ws, method="cusum")
    service.run()
    assert service.status()["total_created"] == 1
    assert service.status()["recent"]
    cleared = service.reset_status()
    assert cleared["total_created"] == 0
    assert cleared["scan_count"] == 0
    assert cleared["recent"] == []
    assert cleared["last_result"] is None
