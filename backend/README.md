# AquaDetective Backend

水质预警溯源智能体后端：数据引擎（模拟流域 + 时序生成 + 水质指纹库）、
确定性计算引擎（异常检测 / 扩散模拟 / 指纹匹配 / 拓扑溯源）、
LangGraph 多智能体编排（监测 / 溯源侦探 / 法规 / 处置 / 报告）、FastAPI + WebSocket 流式接口。

## 快速开始

```bash
cd backend
pip install -e ".[dev]"        # 或 uv sync

# 1) 生成模拟数据（流域 + 90 天时序 + 3 条预置污染事件）
python -m app.data.seed

# 2) 启动服务
uvicorn app.main:app --reload --port 8000
# 文档: http://127.0.0.1:8000/docs

# 3) 跑测试（无 pytest 时可用内置轻量 runner）
pytest tests
# 或
python scripts/run_tests.py
```

## 无 LLM 也能跑

`.env` 不配置 `AQ_LLM_API_KEY` 时，Agent 自动使用模板推理（确定性规则），
完整调查流程（假设生成 → 工具验证 → 结论 → 报告）照常工作，保证演示不依赖网络。

## 常用脚本

- `python -m app.data.seed` — 重建数据库（同 seed 结果可复现；`--force` 强制重建）
- `python scripts/run_tests.py` — 轻量测试 runner（无 pytest 依赖；pytest 亦可）
- `python scripts/smoke_investigate.py [event_id]` — 不启动服务，直接跑"事件 → 侦探推理 → 报告"全链路（无 langgraph 也能跑）
- `python scripts/verify_graph.py [event_id]` — 用最小 stub 模拟 langgraph，验证状态机接线（节点/边/条件路由）
- `python scripts/e2e_api.py [event_id]` — 起服务后跑端到端：触发调查 → WS 流式收推理 → 状态 → 报告
- `python scripts/test_simulate.py` — 测试事件注入 / 世界重置 / EEM / 指纹接口
- `python scripts/verify_data.py` — 检查事件信号与基线合理性

## 目录

```
app/
├── config.py        # pydantic-settings 配置（.env）
├── db.py            # SQLite 连接与建表
├── data/            # 数据引擎：流域构建 / 时序生成 / 指纹库 / seed
├── engine/          # 计算引擎：纯函数、无 LLM、可单测
├── agents/          # LangGraph 状态机 + 5 个 Agent + 工具 + 落盘
├── api/             # REST + WebSocket
└── main.py          # 入口
```

## API 一览（前缀 /api/v1）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /watershed | 全流域拓扑（节点/边/断面/企业） |
| GET | /watershed/enterprises/{id}/fingerprint | 企业双指纹 |
| GET | /stations/{id}/eem | 断面"现场"EEM 荧光矩阵 |
| GET | /series?station=&indicator=&from=&to= | 时序数据 |
| GET | /events?status= | 污染事件列表 |
| POST | /events/{id}/investigate | 触发溯源调查 |
| GET | /investigations/{id} | 调查状态 |
| GET | /investigations/{id}/report | Markdown 报告 |
| POST | /simulate/reset?seed= | 一键重建世界 |
| POST | /simulate/inject | 运行时注入事件 |
| GET | /recordings | 历史调查记录（可回放） |
| WS | /ws?investigation_id= | 推理过程流式推送 |

坐标说明：流域节点坐标为示意图坐标（公里），后续可替换为真实经纬度。
