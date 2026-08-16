"""法规 Agent：RAG 检索适用标准与法条，输出合规判定意见（agent_talk）。"""
from __future__ import annotations

from . import tools


def compliance_review(state: dict, llm, db_path: str, ws: dict) -> dict:
    ev = state["event"]
    indicators = tools.parse_indicators(ev)
    lines = []
    for ind in indicators:
        hits = tools.search_regulations(ind)
        for h in hits[:2]:
            if h["indicator"] == ind:
                lines.append(f"- {h['standard']} · {h['clause']}：{h['text']}")
    if not lines:
        hits = tools.search_regulations("general")
        lines = [f"- {h['standard']} · {h['clause']}：{h['text']}" for h in hits[:2]]
    text = ("依据现行标准与法规，本次事件涉及以下条款：\n" + "\n".join(lines)
            + "\n\n若确认人为偷排/事故性排放，可依据《水污染防治法》追究行政责任。")
    stream = list(state["stream"])
    stream.append({"type": "agent_talk", "data": {"agent": "法规Agent", "text": text}})
    return {"stream": stream}
