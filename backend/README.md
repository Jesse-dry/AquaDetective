# AquaDetective Backend

水质预警溯源智能体后端：数据引擎（模拟流域 + 时序生成 + 水质指纹库）、
确定性计算引擎（异常检测 / 扩散模拟 / 指纹匹配 / 拓扑溯源）、
LangGraph 多智能体编排（监测 / 溯源侦探 / 法规 / 处置 / 报告）、FastAPI + WebSocket 流式接口。

## 快速开始

```bash
cd backend
# 推荐：按已验证版本安装
pip install -r requirements.lock
pip install -e . --no-deps

# 开发依赖也可直接解析安装
# pip install -e ".[dev]"

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

## 公开数据统一导入

太湖导入需要地理数据可选依赖；Cuyahoga 导入只需要基础依赖。

```bash
cd backend
pip install -e ".[data]"

# 可选 cuyahoga、taihu 或 all
python -m app.ingest.run --dataset all
```

标准化结果写入 `data/processed/cuyahoga/` 和 `data/processed/taihu_unified/`，
质量报告同步写入 `docs/data-quality/`。太湖发布水质类别只写入
`evaluation_labels.csv.gz`，不会混入调查引擎读取的 `observations.csv.gz`。

时间约定：SQLite 与计算引擎内部保留秒级 epoch；所有 API/WS 的 `ts`、`onset_ts`
和 `started_at` 均为毫秒级 epoch，前端直接格式化展示。

## 常用脚本

- `python -m app.data.seed` — 重建数据库（同 seed 结果可复现；`--force` 强制重建）
- `python -m app.ingest.run --dataset all` — 生成中美公开数据统一包和质量报告
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
| POST | /monitor/scan | 立即扫描水质时序并生成告警 |
| GET | /monitor/status | 定时监测配置、运行状态和最近结果 |
| POST | /monitor/config | 暂停/恢复巡检，调整间隔、窗口和检测方法 |
| POST | /events/{id}/investigate | 触发溯源调查 |
| GET | /investigations/{id} | 调查状态 |
| GET | /investigations/{id}/report | Markdown 报告 |
| POST | /simulate/reset?seed= | 一键重建世界 |
| POST | /simulate/inject | 运行时注入事件 |
| GET | /recordings | 历史调查记录（可回放） |
| WS | /ws?investigation_id= | 推理过程流式推送 |

坐标说明：流域节点坐标为示意图坐标（公里），后续可替换为真实经纬度。

## 监测运行

大屏监测状态条的“立即扫描”调用 `POST /api/v1/monitor/scan`，无需请求体。扫描生成
`etype=detected`、`truth_source=NULL` 的事件，刷新后可点击“开始侦查”。监测不调用
LLM，也不会自动发起调查。Mock 模式禁用扫描按钮。

默认启用定时扫描，可在状态条暂停/恢复。持久配置在 `backend/.env` 配置后重启服务：

```dotenv
AQ_MONITOR_ENABLED=true
AQ_MONITOR_INTERVAL_S=300
AQ_MONITOR_WINDOW_H=24
AQ_MONITOR_METHOD=cusum
```

启用后首次等待指定间隔，此后每次完成后等待指定间隔；关闭服务时停止任务。
`POST /api/v1/monitor/config` 可调整 enabled、interval_s、window_h 和 method；
运行时配置仅在当前进程生效，重启后恢复环境配置。状态条显示倒计时、累计检出、
最近告警及数据时间。running 表示正在扫描，scheduler_running 表示调度线程存活。
方法支持 `cusum`、`ewma`、`threesigma`、`seasonal`。建议单个 Uvicorn worker 运行
定时任务；多个 worker 各自维护调度和状态，但 SQLite 事务可避免重复写入告警。

窗口以每条断面/指标序列的最新观测时间为终点，不以系统当前时间为终点。
默认窗口 24 小时；低频序列自动补足至少 48 个样本（3σ 至少 144 个，季节检测
还需按实测采样间隔补足 8 个日周期）。历史总量不足则跳过并计入
`insufficient_series`，不会把“无法检测”当作正常水质。界面显示最新观测时间，
历史数据扫描不代表实时数据已经接入。

`monitor_cursors` 持久化每条序列的扫描进度；同一断面、同一指标在 48 小时内的
告警按所有处置状态去重。已有数据不变时不会重扫，新增观测才推进扫描。
修改历史值或检测参数后，如需重新评估历史，请在隔离评测库中调用
`scan_for_events()`（不使用在线进度）。重置世界会同时清空监测进度。
离线评测函数保留原有列表返回类型。

接口结果包含 `created_count`、`events`、`scanned_series`、`unchanged_series`、
`insufficient_series`、`extended_series`、`latest_data_ts`；公开时间戳均为毫秒。
同一服务已有扫描进行时返回 HTTP 409，扫描失败返回 HTTP 500 并记录服务日志；
定时任务失败后会在下一周期重试。告警与扫描进度在同一事务中提交。

CNEMC 抓取任务仍负责文件存档。要监测真实数据，需要先将观测写入运行数据库的
`readings`，并在流域配置中注册对应断面和指标。监测模块只写告警，不生成事件级
EEM 或污染源真值。目前调查流程在缺少事件级指纹时仍会回退到背景观测，这种
调查结果只能辅助排查，不能当作真实污染源已被证实。检测阈值也需用目标断面的
真实数据校准。
