"""LangGraph 接线验证：用最小 stub 模拟 langgraph（注入 sys.modules），
驱动 app/agents/graph.py 的真实构建与流式执行，验证节点/边/条件路由正确性。

用法: python scripts/verify_graph.py [event_id]
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# ---- 最小 langgraph stub（仅实现 graph.py 用到的 API 面）----
class _Sentinel:
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"<{self.name}>"


START, END = _Sentinel("START"), _Sentinel("END")


class StateGraph:
    def __init__(self, schema):
        self.schema = schema
        self.nodes: dict[str, callable] = {}
        self.edges: dict[str, object] = {}
        self.conditionals: dict[str, tuple[callable, dict]] = {}

    def add_node(self, name, fn):
        self.nodes[name] = fn

    def add_edge(self, src, dst):
        self.edges[src] = dst

    def add_conditional_edges(self, src, router, mapping):
        self.conditionals[src] = (router, mapping)

    def compile(self):
        return _Compiled(self)


class _Compiled:
    def __init__(self, graph: StateGraph):
        self.graph = graph

    def stream(self, state, stream_mode="values"):
        assert stream_mode == "values"
        state = dict(state)
        nxt = [d for s, d in self.graph.edges.items() if s is START]
        if not nxt:
            nxt = ["parse_event"]
        while nxt:
            name = nxt.pop(0)
            fn = self.graph.nodes[name]
            state.update(fn(state))
            yield state
            if name in self.graph.conditionals:
                router, mapping = self.graph.conditionals[name]
                nxt.append(mapping[router(state)])
            elif name in self.graph.edges:
                dst = self.graph.edges[name]
                if dst is not END:
                    nxt.append(dst)


import types  # noqa: E402

_stub = types.ModuleType("langgraph")
_stub.graph = types.ModuleType("langgraph.graph")
_stub.graph.START, _stub.graph.END = START, END
_stub.graph.StateGraph = StateGraph
sys.modules["langgraph"] = _stub
sys.modules["langgraph.graph"] = _stub.graph

# ---- 用真实代码构建图并执行 ----
from app.agents.graph import build_graph  # noqa: E402
from app.config import settings  # noqa: E402
from app.context import get_db_path, get_watershed  # noqa: E402
from app.data.seed import ensure_db  # noqa: E402
from app.db import get_conn  # noqa: E402

ensure_db(settings)
db, ws = get_db_path(), get_watershed()
conn = get_conn(db)
row = conn.execute("SELECT * FROM events WHERE id=?", (sys.argv[1] if len(sys.argv) > 1 else "evt_001",)).fetchone()
conn.close()
assert row, "事件不存在"

state = {
    "event": dict(row), "hypotheses": [], "evidence_log": [], "conclusion": None,
    "report": None, "stream": [], "round": 0, "done": False, "investigation_id": "stub_test",
}
graph = build_graph(None, db, ws)
steps = 0
for chunk in graph.stream(state, stream_mode="values"):
    steps += 1
conclusion = chunk["conclusion"]
assert conclusion and conclusion["status"] == "resolved", f"未锁定: {conclusion}"
assert conclusion["source_id"] == row["truth_source"], \
    f"锁定错误: {conclusion['source_id']} != truth {row['truth_source']}"
assert chunk["report"] and chunk["report"].startswith("# 水质污染溯源调查报告")
assert any(m["type"] == "report_ready" for m in chunk["stream"])
print(f"OK: {steps} 个超步，锁定 {conclusion['source_name']} "
      f"(置信度 {conclusion['confidence']})，报告 {len(chunk['report'])} 字符")
