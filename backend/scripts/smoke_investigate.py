"""侦探流程冒烟测试（不依赖 langgraph）：手动按状态机顺序驱动节点函数，
验证"偷排事件 → 假设生成 → 证据校核 → 锁定 → 法规/处置/报告"全链路。

用法: python scripts/smoke_investigate.py [event_id]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.agents.compliance import compliance_review  # noqa: E402
from app.agents.investigator import (conclude, generate_hypotheses,  # noqa: E402
                                     parse_event, verify_hypotheses)
from app.agents.reporter import build_report  # noqa: E402
from app.agents.responder import response_plan  # noqa: E402
from app.config import settings  # noqa: E402
from app.context import get_db_path, get_watershed  # noqa: E402
from app.data.seed import ensure_db  # noqa: E402
from app.db import get_conn  # noqa: E402

NODES = [parse_event, generate_hypotheses, verify_hypotheses, conclude,
         compliance_review, response_plan, build_report]


def run(event_id: str) -> dict:
    ensure_db(settings)
    db, ws = get_db_path(), get_watershed()
    conn = get_conn(db)
    row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    conn.close()
    if not row:
        raise SystemExit(f"事件不存在: {event_id}")
    state = {
        "event": dict(row), "hypotheses": [], "evidence_log": [], "conclusion": None,
        "report": None, "stream": [], "round": 0, "done": False,
        "investigation_id": "smoke_test",
    }
    for fn in NODES:
        update = fn(state, None, db, ws)  # llm=None → 模板降级
        state.update(update)
        if fn is verify_hypotheses and not state.get("done"):
            # 模拟条件边的循环
            while not state.get("done"):
                state.update(verify_hypotheses(state, None, db, ws))
    print(f"\n===== 事件 {event_id} 推理流（{len(state['stream'])} 条消息）=====")
    for m in state["stream"]:
        d = m["data"]
        if m["type"] == "step":
            print(f"[{d.get('phase')}] {d.get('clue', '')[:60]} -> {d.get('status')}")
        elif m["type"] == "hypothesis":
            print(f"[假设 {d['id']}] {d['target']} 得分 {d['score']} ({d['status']})")
        elif m["type"] == "agent_talk":
            print(f"[{d['agent']}] {d['text'][:60]}...")
        elif m["type"] in ("conclusion", "failed"):
            print(f"[结论/{m['type']}] {json.dumps(d, ensure_ascii=False)[:200]}")
    print("\n===== 报告开头 =====")
    print("\n".join(state["report"].splitlines()[:12]))
    ok = state["conclusion"] and state["conclusion"].get("status") == "resolved"
    print(f"\n=> 结论: {state['conclusion'].get('status')} "
          f"置信度 {state['conclusion'].get('confidence')}")
    return state


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "evt_001")
