"""One service for scheduled scans, manual scans and live controls."""
from __future__ import annotations

import logging
import threading
import time

from .agents.monitor import scan

logger = logging.getLogger(__name__)


class ScanBusy(Exception):
    pass


class MonitorService:
    def __init__(self, db_path, watershed, *, enabled=False, interval_s=300,
                 window_h=24, method="seasonal"):
        self.db_path = db_path
        self.watershed = watershed
        self.enabled = enabled
        self.interval_s = interval_s
        self.window_h = window_h
        self.method = method
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._status = {"running": False, "last_started_at": None,
                        "last_finished_at": None, "last_result": None, "last_error": None,
                        "scan_count": 0, "total_created": 0, "last_duration_ms": None,
                        "last_created": 0, "recent": [], "next_scan_at": None}

    def _schedule(self):
        self._status["next_scan_at"] = time.time() + self.interval_s if self.enabled else None

    def status(self):
        with self._state_lock:
            return {"enabled": self.enabled, "interval_s": self.interval_s,
                    "window_h": self.window_h, "method": self.method,
                    "scheduler_running": bool(self._thread and self._thread.is_alive()),
                    **self._status}

    def reset_status(self):
        """世界重建后清空运行统计。

        这些计数只在内存里,重建世界不会动它们,于是状态条会继续显示上一个世界的
        检出记录与累计数(实测残留 4 条同名事件,因为 evt_scan_NNN 编号会复用)。
        """
        with self._state_lock:
            self._status.update(last_result=None, last_created=0, total_created=0,
                                scan_count=0, last_error=None, recent=[],
                                last_started_at=None, last_finished_at=None,
                                last_duration_ms=None)
            self._schedule()
        self._wake.set()
        return self.status()

    def configure(self, **changes):
        with self._state_lock:
            for key in ("enabled", "interval_s", "window_h", "method"):
                if changes.get(key) is not None:
                    setattr(self, key, changes[key])
            self._schedule()
        self._wake.set()
        return self.status()

    def run(self):
        if not self._lock.acquire(blocking=False):
            raise ScanBusy()
        started = time.monotonic()
        with self._state_lock:
            self._status.update(running=True, last_started_at=time.time(), last_error=None,
                                last_created=0)
            window_h, method = self.window_h, self.method
        try:
            result = scan(self.db_path, self.watershed(), window_h, method)
            with self._state_lock:
                events = result["events"]
                self._status.update(last_result=result, last_created=len(events))
                self._status["total_created"] += len(events)
                self._status["recent"] = (list(reversed(events)) + self._status["recent"])[:20]
            return result
        except Exception:
            with self._state_lock:
                self._status["last_error"] = "Monitoring scan failed; check server logs."
            raise
        finally:
            with self._state_lock:
                self._status.update(running=False, last_finished_at=time.time(),
                                    last_duration_ms=int((time.monotonic() - started) * 1000))
                self._status["scan_count"] += 1
                self._schedule()
            self._lock.release()
            self._wake.set()

    def _loop(self):
        while not self._stop.is_set():
            with self._state_lock:
                deadline = self._status["next_scan_at"]
                due = self.enabled and deadline is not None and time.time() >= deadline
            if due:
                try:
                    self.run()
                except ScanBusy:
                    pass
                except Exception:
                    logger.exception("Scheduled monitoring scan failed")
            self._wake.wait(0.1)
            self._wake.clear()

    def start(self):
        if self._thread is None:
            with self._state_lock:
                self._schedule()
            self._thread = threading.Thread(target=self._loop, name="water-monitor", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join()
        with self._state_lock:
            self._status["next_scan_at"] = None
