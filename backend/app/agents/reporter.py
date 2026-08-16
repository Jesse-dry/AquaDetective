"""报告 Agent：汇总全链路生成 Markdown 溯源报告（report_ready）。"""
from __future__ import annotations

from datetime import datetime, timezone

from . import tools


def _fmt(ts: int | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_report(state: dict, llm, db_path: str, ws: dict) -> dict:
    ev = state["event"]
    hyps = state["hypotheses"]
    conclusion = state["conclusion"] or {}
    talks = [m["data"] for m in state["stream"] if m["type"] == "agent_talk"]
    steps = [m["data"] for m in state["stream"] if m["type"] == "step"]

    lines = [
        "# 水质污染溯源调查报告",
        "",
        f"- 调查编号：{state.get('investigation_id', '-')}",
        f"- 事件编号：{ev.get('id')}（{ev.get('etype')} / {ev.get('severity')}）",
        f"- 预警断面：{ev.get('station_id')}",
        f"- 异常指标：{', '.join(tools.parse_indicators(ev))}",
        f"- 首达时间：{_fmt(ev.get('onset_ts'))}",
        "",
        "## 一、调查过程（线索 → 推理 → 证据）",
        "",
    ]
    for i, s in enumerate(steps, 1):
        lines.append(f"### {i}. {s.get('phase', '')}")
        lines.append(f"- 线索：{s.get('clue', '')}")
        lines.append(f"- 推理：{s.get('reasoning', '')}")
        for e in s.get("evidence", []):
            lines.append(f"- 证据：{e.get('kind')} = {e.get('value')}")
        lines.append("")
    lines.append("## 二、嫌疑排序")
    lines.append("")
    for h in sorted(hyps, key=lambda x: x["score"], reverse=True):
        lines.append(f"- {h['target_name']}（{h['industry']}）：得分 {h['score']}，状态 {h['status']}")
    lines.append("")
    lines.append("## 三、结论")
    lines.append("")
    if conclusion.get("status") == "resolved":
        lines.append(f"**锁定污染源：{conclusion.get('source_name')}**")
        lines.append("")
        lines.append(f"- 置信度：{conclusion['confidence']:.0%}")
        lines.append(f"- 依据：{conclusion.get('evidence_summary', '')}")
    else:
        lines.append("**未能锁定单一污染源**")
        lines.append("")
        lines.append(f"- 原因：{conclusion.get('reason', '')}")
        lines.append(f"- 建议：{('；'.join(conclusion.get('suggestions') or []))}")
    lines.append("")
    lines.append("## 四、法规与处置意见")
    lines.append("")
    for t in talks:
        lines.append(f"**{t.get('agent')}**：{t.get('text')}")
        lines.append("")
    report = "\n".join(lines)
    stream = list(state["stream"])
    stream.append({"type": "report_ready", "data": {
        "report_id": state.get("investigation_id")}})
    return {"report": report, "stream": stream}
