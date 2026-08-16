"""处置 Agent：按事件类型与严重度生成处置与调度建议（agent_talk）。"""
from __future__ import annotations

PLANS = {
    "periodic": ["立即对该企业开展夜间突击执法检查", "核查排污许可证与在线监测数据",
                 "对特征污染物（重金属）开展加密监测", "必要时启用应急调蓄设施"],
    "sudden": ["启动突发水污染事件应急预案", "通知下游水厂停止取水并启用备用水源",
               "在下游断面加密监测（每2小时1次）", "组织泄漏源围堵与吸附处置"],
    "gradual": ["排查污水处理厂运行工况与进水水质", "核查上游管网与面源污染",
                "启动流域联合调度，增加生态补水", "对超标断面实施水质改善工程措施"],
    "detected": ["复核自动监测数据与实验室比对", "扩大监测范围排查潜在污染源"],
}
SEVERITY_TIP = {"low": "密切关注，加密监测", "medium": "启动应急响应，2小时内完成溯源",
                "high": "立即启动应急响应，通报下游并组织溯源"}


def response_plan(state: dict, llm, db_path: str, ws: dict) -> dict:
    ev = state["event"]
    etype = ev.get("etype", "detected")
    sev = ev.get("severity", "medium")
    steps = PLANS.get(etype, PLANS["detected"])
    text = (f"建议处置方案（{etype} · {sev}）：\n"
            + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
            + f"\n\n优先级提示：{SEVERITY_TIP[sev]}")
    stream = list(state["stream"])
    stream.append({"type": "agent_talk", "data": {"agent": "处置Agent", "text": text}})
    return {"stream": stream}
