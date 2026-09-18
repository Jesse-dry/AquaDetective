"""监测 Agent 运行时:后台定时扫描 + 运行状态(供状态条展示)。

`scan_for_events` 是纯检测逻辑(见 agents/monitor.py);本模块负责"什么时候扫、
扫完记什么",并把状态暴露给 API 与前端状态条。
"""
from __future__ import annotations

import asyncio
import time

from .agents.monitor import scan_for_events
from .config import settings
from .context import get_db_path, get_watershed

# 最近检出事件在状态里保留的条数(只用于展示)
_RECENT_MAX = 20


def _now_ms() -> int:
    return int(time.time() * 1000)


# 运行状态:定时任务写、API 读。字段均为简单类型,单线程写 + 事件循环读足够安全
MONITOR_STATE: dict = {
    "enabled": settings.monitor_enabled,
    "interval_s": settings.monitor_interval_s,
    "window_h": settings.monitor_window_h,
    "running": False,        # 后台循环是否存活
    "scan_count": 0,         # 累计扫描次数
    "total_created": 0,      # 累计生成事件数
    "last_scan_ms": None,    # 上次扫描完成时刻(毫秒 epoch)
    "last_duration_ms": None,
    "last_created": 0,
    "last_error": None,
    "next_scan_ms": None,    # 下次扫描时刻(暂停时为 None)
    "recent": [],            # 最近检出的事件摘要
}


def scan_once(db_path: str | None = None, ws: dict | None = None,
              window_h: int | None = None) -> list[dict]:
    """执行一次扫描并记录状态;失败时把错误写入 last_error 后原样抛出。"""
    db_path = db_path or get_db_path()
    ws = ws or get_watershed()
    window_h = int(window_h or MONITOR_STATE["window_h"])
    t0 = time.time()
    try:
        created = scan_for_events(db_path, ws, window_h=window_h)
    except Exception as e:  # 记状态后交给调用方决定(后台循环吞掉,API 返回 500)
        MONITOR_STATE["last_error"] = f"{type(e).__name__}: {e}"
        MONITOR_STATE["scan_count"] += 1
        MONITOR_STATE["last_scan_ms"] = _now_ms()
        MONITOR_STATE["last_duration_ms"] = int((time.time() - t0) * 1000)
        raise
    MONITOR_STATE["last_error"] = None
    MONITOR_STATE["scan_count"] += 1
    MONITOR_STATE["last_scan_ms"] = _now_ms()
    MONITOR_STATE["last_duration_ms"] = int((time.time() - t0) * 1000)
    MONITOR_STATE["last_created"] = len(created)
    MONITOR_STATE["total_created"] += len(created)
    if created:
        MONITOR_STATE["recent"] = (created + MONITOR_STATE["recent"])[:_RECENT_MAX]
    return created


def configure(enabled: bool | None = None, interval_s: int | None = None,
              window_h: int | None = None) -> dict:
    """调整监测参数(状态条上的开关/间隔)。"""
    if enabled is not None:
        MONITOR_STATE["enabled"] = bool(enabled)
    if interval_s is not None:
        MONITOR_STATE["interval_s"] = max(int(interval_s), 30)
    if window_h is not None:
        MONITOR_STATE["window_h"] = max(int(window_h), 1)
    return MONITOR_STATE


async def monitor_loop() -> None:
    """后台定时扫描:启用时每 interval_s 扫一次,暂停时轻量轮询开关。

    首次扫描延迟一个间隔,避免与启动时的建库/建流域抢 SQLite。
    扫描是 CPU 密集的 numpy 计算,放线程池执行,不阻塞事件循环。
    """
    MONITOR_STATE["running"] = True
    try:
        while True:
            if not MONITOR_STATE["enabled"]:
                MONITOR_STATE["next_scan_ms"] = None
                await asyncio.sleep(1)
                continue
            # 分片等待:暂停或改间隔能立即生效,不必等满一个周期
            interval = max(int(MONITOR_STATE["interval_s"]), 30)
            deadline = time.time() + interval
            while MONITOR_STATE["enabled"] and time.time() < deadline:
                if max(int(MONITOR_STATE["interval_s"]), 30) != interval:
                    break  # 间隔被改动,重新计时
                MONITOR_STATE["next_scan_ms"] = int(deadline * 1000)
                await asyncio.sleep(1)
            if not MONITOR_STATE["enabled"] or time.time() < deadline:
                continue
            try:
                await asyncio.to_thread(scan_once)
            except Exception:
                pass  # 错误已记入 last_error,循环继续(单次失败不影响后续扫描)
    finally:
        MONITOR_STATE["running"] = False
        MONITOR_STATE["next_scan_ms"] = None
