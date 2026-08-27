"""时间戳边界转换：数据库/计算引擎用秒，公开 API 用毫秒。"""
from __future__ import annotations


def epoch_ms(value: int | None) -> int | None:
    """Convert an internal epoch-second value to the public epoch-millisecond form."""
    return None if value is None else int(value) * 1000


def epoch_seconds(value_ms: int | None) -> int:
    """Convert a public epoch-millisecond query bound to epoch seconds."""
    return 0 if value_ms is None else int(value_ms // 1000)
