"""调查状态定义（LangGraph State）。"""
from typing import TypedDict


class InvestigationState(TypedDict):
    event: dict                 # 事件详情（来自 events 表）
    hypotheses: list[dict]      # [{id, target_id, target_name, reasons, score, evidence, status}]
    evidence_log: list[dict]    # 全链路证据（线索→推理→证据 三元组）
    conclusion: dict | None     # {source_id, confidence, evidence_summary, status}
    report: str | None          # Markdown 报告
    stream: list[dict]          # 待推送消息队列（WS 消费；每次整体返回给 LangGraph）
    round: int                  # 验证轮次（限制循环）
    done: bool                  # 验证循环是否结束（条件边路由用）
    investigation_id: str       # 调查编号（报告/落盘用）
