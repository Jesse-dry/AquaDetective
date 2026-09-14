"""报告 Agent：汇总全链路生成 Markdown 溯源报告（report_ready）。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import tools
from .investigator import ETYPE_CN, INDICATOR_CN, INDUSTRY_CN, SEVERITY_CN

_TZ_CN = timezone(timedelta(hours=8))

# 证据阶段英文后缀 → 中文(与前端 STEP_PHASE_CN 保持一致)
STEP_CN = {"eem": "荧光指纹", "pollutant": "污染物谱",
           "pattern": "排放规律", "strength": "传播强度"}
# 证据类型标识 → 中文
KIND_CN = {"eem_score": "荧光指纹相似度", "pollutant_score": "污染物谱相似度",
           "pattern_score": "排放规律匹配度", "strength_score": "传播时间评分"}


def _fmt(ts: int | None) -> str:
    if not ts:
        return "-"
    # 毫秒 epoch(API 契约)与秒级兼容:大于 1e11 视为毫秒
    sec = ts / 1000 if ts > 1e11 else ts
    return datetime.fromtimestamp(sec, tz=_TZ_CN).strftime("%Y-%m-%d %H:%M")


def _event_cn(event_id: str | None) -> str:
    """evt_003 → 事件3;evt_inj_001 → 现场注入事件;其他原样。"""
    eid = event_id or ""
    if eid.startswith("evt_inj_"):
        return "现场注入事件"
    m = re.match(r"^evt_?0*(\d+)$", eid, re.I)
    return f"事件{int(m[1])}" if m else (eid or "-")


def _station_cn(station_id: str | None) -> str:
    """st_06 → 6号断面。"""
    m = re.match(r"^st_?0*(\d+)$", station_id or "", re.I)
    return f"{int(m[1])}号断面" if m else (station_id or "-")


def _indicators_cn(ev: dict) -> str:
    inds = tools.parse_indicators(ev)
    return "、".join(INDICATOR_CN.get(i, i) for i in inds) or "未知指标"


def _evidence_text(e: dict) -> str:
    """证据行:证据类型标识转中文,分值保留 4 位。"""
    kind, value = e.get("kind"), e.get("value")
    kind_cn = KIND_CN.get(kind, kind)
    if isinstance(value, float):
        return f"{kind_cn} = {value:.4f}"
    return f"{kind_cn} = {value}"


def build_report(state: dict, llm, db_path: str, ws: dict) -> dict:
    ev = state["event"]
    hyps = state["hypotheses"]
    conclusion = state["conclusion"] or {}
    talks = [m["data"] for m in state["stream"] if m["type"] == "agent_talk"]
    steps = [m["data"] for m in state["stream"] if m["type"] == "step"]

    etype_cn = ETYPE_CN.get(ev.get("etype"), ev.get("etype") or "-")
    sev_cn = SEVERITY_CN.get(ev.get("severity"), ev.get("severity") or "-")
    lines = [
        "# 水质污染溯源调查报告",
        "",
        f"- 事件：{_event_cn(ev.get('id'))}（{etype_cn} · {sev_cn}）",
        f"- 预警断面：{_station_cn(ev.get('station_id'))}",
        f"- 异常指标：{_indicators_cn(ev)}",
        f"- 首达时间：{_fmt(ev.get('onset_ts'))}",
        "",
        "## 一、调查过程（线索 → 推理 → 证据）",
        "",
    ]
    for i, s in enumerate(steps, 1):
        # 阶段名里的英文后缀(eem/pollutant/pattern)转中文,与前端展示一致
        phase = re.sub(r"·([a-z]+)$",
                       lambda m: f"·{STEP_CN.get(m.group(1), m.group(1))}",
                       s.get("phase", ""))
        lines.append(f"### {i}. {phase}")
        lines.append(f"- 线索：{s.get('clue', '')}")
        lines.append(f"- 推理：{s.get('reasoning', '')}")
        # 事件解析步的证据就是事件本身(报告头部已列明),不重复展示
        if s.get("step_id") != "parse":
            for e in s.get("evidence", []):
                lines.append(f"- 证据：{_evidence_text(e)}")
        lines.append("")
    lines.append("## 二、嫌疑排序")
    lines.append("")
    status_cn = {"candidate": "候选", "rejected": "已排除"}
    for h in sorted(hyps, key=lambda x: x["score"], reverse=True):
        ind_cn = INDUSTRY_CN.get(h["industry"], h["industry"])
        st_cn = status_cn.get(h["status"], h["status"])
        lines.append(f"- {h['target_name']}（{ind_cn}）：得分 {h['score']}，状态 {st_cn}")
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
    # report_ready 不在此处加入 stream;改由 runner 在报告落盘后 push,
    # 保证前端收到 report_ready 时报告文件已可读(避免收到信号却查不到报告的时序竞态)
    return {"report": report}
