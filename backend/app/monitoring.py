"""Monitoring lifecycle shared by manual scans and the optional scheduler."""
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
                 window_h=24, method="cusum"):
        self.db_path = db_path
        self.watershed = watershed
        self.enabled = enabled
        self.interval_s = interval_s
        self.window_h = window_h
        self.method = method
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._status = {"running": False, "last_started_at": None,
                        "last_finished_at": None, "last_result": None, "last_error": None}

    def status(self):
        return {"enabled": self.enabled, "interval_s": self.interval_s,
                "window_h": self.window_h, "method": self.method, **self._status}

    def run(self):
        if not self._lock.acquire(blocking=False):
            raise ScanBusy()
        self._status = {**self._status, "running": True,
                        "last_started_at": time.time(), "last_error": None}
        try:
            result = scan(self.db_path, self.watershed(), self.window_h, self.method)
            self._status = {**self._status, "last_result": result}
            return result
        except Exception:
            self._status = {**self._status, "last_error": "Monitoring scan failed; check server logs."}
            raise
        finally:
            self._status = {**self._status, "running": False, "last_finished_at": time.time()}
            self._lock.release()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.run()
            except ScanBusy:
                pass
            except Exception:
                logger.exception("Scheduled monitoring scan failed")
            self._stop.wait(self.interval_s)

    def start(self):
        if self.enabled and self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="water-monitor", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
