"""LangGraph 状态机：侦探式溯源全流程。

parse_event → generate_hypotheses → verify_hypotheses(循环) → conclude
→ compliance → responder → reporter

节点函数均为闭包绑定 (llm, db_path, ws)。langgraph 缺失时本模块导入会失败，
API 层在触发调查时才懒加载（见 runner），保证服务本体可在无 langgraph 环境启动。
"""
from __future__ import annotations

from .compliance import compliance_review
from .investigator import conclude, generate_hypotheses, parse_event, verify_hypotheses
from .reporter import build_report
from .responder import response_plan


def _route_verify(state: dict) -> str:
    return "done" if state.get("done") else "again"


def build_graph(llm, db_path: str, ws: dict):
    from langgraph.graph import END, START, StateGraph

    from .state import InvestigationState

    def n_parse(state):
        return parse_event(state, llm, db_path, ws)

    def n_gen(state):
        return generate_hypotheses(state, llm, db_path, ws)

    def n_verify(state):
        return verify_hypotheses(state, llm, db_path, ws)

    def n_conclude(state):
        return conclude(state, llm, db_path, ws)

    def n_compliance(state):
        return compliance_review(state, llm, db_path, ws)

    def n_responder(state):
        return response_plan(state, llm, db_path, ws)

    def n_reporter(state):
        return build_report(state, llm, db_path, ws)

    g = StateGraph(InvestigationState)
    g.add_node("parse_event", n_parse)
    g.add_node("generate_hypotheses", n_gen)
    g.add_node("verify_hypotheses", n_verify)
    g.add_node("conclude", n_conclude)
    g.add_node("compliance", n_compliance)
    g.add_node("responder", n_responder)
    g.add_node("reporter", n_reporter)

    g.add_edge(START, "parse_event")
    g.add_edge("parse_event", "generate_hypotheses")
    g.add_edge("generate_hypotheses", "verify_hypotheses")
    g.add_conditional_edges("verify_hypotheses", _route_verify,
                            {"again": "verify_hypotheses", "done": "conclude"})
    g.add_edge("conclude", "compliance")
    g.add_edge("compliance", "responder")
    g.add_edge("responder", "reporter")
    g.add_edge("reporter", END)
    return g.compile()
