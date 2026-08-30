"""推理过程落盘（JSONL 回放）与报告文件。"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import BASE_DIR

REC_DIR = BASE_DIR / "data" / "recordings"


def _path(inv_id: str) -> Path:
    REC_DIR.mkdir(parents=True, exist_ok=True)
    return REC_DIR / f"{inv_id}.jsonl"


def record(inv_id: str, msg: dict) -> None:
    with open(_path(inv_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")


def replay(inv_id: str) -> list[dict]:
    p = _path(inv_id)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_report(inv_id: str, markdown: str) -> Path:
    p = REC_DIR / f"{inv_id}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown, encoding="utf-8")
    return p


def report_path(inv_id: str) -> Path | None:
    p = REC_DIR / f"{inv_id}.md"
    return p if p.exists() else None


def list_recordings() -> list[str]:
    REC_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in REC_DIR.glob("*.jsonl"))


def delete_recording(inv_id: str) -> bool:
    """删除一条录音(jsonl + 报告 md)。返回是否存在过。"""
    # 校验 id 防路径穿越(仅允许字母数字下划线)
    if not inv_id or not inv_id.replace("_", "").isalnum():
        return False
    existed = False
    for suffix in (".jsonl", ".md"):
        p = REC_DIR / f"{inv_id}{suffix}"
        if p.exists():
            p.unlink()
            existed = True
    return existed
