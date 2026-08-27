"""调查运行器：后台线程跑 LangGraph，流式消息经 push 回调转发（WS），并落盘/落库。"""
from __future__ import annotations

import json
import traceback

from ..db import get_conn
from . import recorder


def run_investigation(inv_id: str, event: dict, llm, db_path: str, ws: dict,
                      push, done_event) -> None:
    from .graph import build_graph

    state = {
        "event": event, "hypotheses": [], "evidence_log": [],
        "conclusion": None, "report": None, "stream": [], "round": 0,
        "done": False, "investigation_id": inv_id,
    }
    last_chunk: dict | None = None
    try:
        graph = build_graph(llm, db_path, ws)
        last = 0
        for chunk in graph.stream(state, stream_mode="values"):
            last_chunk = chunk
            stream = chunk.get("stream") or []
            for msg in stream[last:]:
                recorder.record(inv_id, msg)
                push(msg)
            last = len(stream)
        conclusion = (last_chunk or {}).get("conclusion") or {}
        report = (last_chunk or {}).get("report")
        ok = conclusion.get("status") == "resolved"
        conn = get_conn(db_path)
        conn.execute("UPDATE investigations SET status=?, conclusion=? WHERE id=?",
                     ("resolved" if ok else "failed",
                      json.dumps(conclusion, ensure_ascii=False), inv_id))
        conn.execute("UPDATE events SET status=? WHERE id=?",
                     ("resolved" if ok else "open", event.get("id")))
        conn.commit()
        conn.close()
        if report:
            recorder.save_report(inv_id, report)
            # 报告落盘后再推送 report_ready,保证前端收到信号时报告文件已可读
            ready_msg = {"type": "report_ready", "data": {"report_id": inv_id}}
            recorder.record(inv_id, ready_msg)
            push(ready_msg)
    except Exception as exc:  # noqa: BLE001 —— 保证 done_event 一定触发
        msg = {"type": "failed", "data": {"reason": f"调查引擎异常：{exc}",
                                          "suggestions": ["查看服务日志"]}}
        recorder.record(inv_id, msg)
        try:
            push(msg)
        except Exception:
            pass
        try:
            conn = get_conn(db_path)
            conn.execute("UPDATE investigations SET status='failed' WHERE id=?", (inv_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass
        traceback.print_exc()
    finally:
        done_event.set()
