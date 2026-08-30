# AquaDetective · 水质预警溯源智能体

> 智理杯 vibe-coding 赛道项目 —— 一个"水域侦探"：从水质异常预警到污染源锁定再到处置报告，
> 全程由多智能体自动推理完成，每一步推理过程可视化、可解释、可回放。
>
> 技术路线：Python + FastAPI + LangGraph 多智能体编排 + 确定性计算引擎 + 模拟数据引擎

---

## 项目简介

AquaDetective 是一个面向流域水环境管理的智能体系统，模拟真实的水污染事件（工业偷排、突发泄漏、
处理设施渐变失效），并自动完成：**异常检测 → 预警 → 侦探式溯源推理 → 指纹比对锁定污染源 →
法规检索 → 处置建议 → 溯源报告** 的完整闭环。

系统对标真实落地的行业技术——清华大学苏州环境创新研究院的"水质指纹"预警溯源技术
（已在台州椒江、长治、黄河乌海段等地应用，最快 21 分钟溯源）——以三维荧光光谱（EEM）
指纹识别为核心手段，结合多智能体推理，把"溯源"从人工分析变成自动化的侦探式推理。

**核心设计铁律**：所有数值计算（超标判断、扩散浓度、指纹相似度、上下游关系）全部走确定性代码，
大模型只负责推理编排与自然语言表达——从机制上杜绝"AI 编数据"的幻觉问题。

## 核心特性

| 特性 | 说明 |
|---|---|
| 🕵️ 侦探式溯源推理 | 假设生成 → 工具验证 → 排除/锁定，每步产出"线索→推理→证据"三元组，流式推送到前端 |
| 🧬 水质双指纹 | EEM 荧光光谱指纹 + 特征污染物比例指纹（一厂一谱），双通道比对打分 |
| 🤖 多智能体协作 | 监测 / 溯源侦探 / 法规 / 处置 / 报告 五个 Agent，LangGraph 状态机编排 |
| 🛡️ 防幻觉护城河 | 数值全部来自确定性引擎（NumPy/SciPy/NetworkX），LLM 无编造数据的工具 |
| 📡 流式推理展示 | WebSocket 实时推送 6 类消息（step/hypothesis/agent_talk/conclusion/failed/report_ready） |
| 🎲 可复现演示 | 模拟数据同 seed 逐字节可复现，一键重置世界，现场注入任意事件 |
| 🔌 无 LLM 也能跑 | 未配置 API Key 时自动降级为模板推理，完整调查流程照常工作 |
| 📼 全程可回放 | 每次调查推理过程落盘 JSONL，一键回放（答辩利器） |

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│  展示层  Web 大屏（开发中）                            │
│          流域地图 / 推理流 / 浓度动画 / 指纹比对 / 报告   │
├─────────────────────────────────────────────────────┤
│  API 层  FastAPI：12 个 REST 端点 + WebSocket 推理流   │
├─────────────────────────────────────────────────────┤
│  Agent 层  LangGraph 侦探式状态机                     │
│    监测Agent → 溯源Agent(侦探主编排) → 法规Agent        │
│    → 处置Agent → 报告Agent                            │
│    推理状态: parse → 假设生成 → 证据校核循环 → 排除/锁定  │
├─────────────────────────────────────────────────────┤
│  计算引擎  确定性纯函数（LLM 不可触碰）                 │
│    异常检测 / 高斯烟团扩散 / EEM+污染物指纹 / 拓扑溯源    │
│    / 昼夜规律分析                                     │
├─────────────────────────────────────────────────────┤
│  数据层  清源河模拟流域（27 节点 / 10 断面 / 18 企业）    │
│    90 天时序生成器 / 双指纹库 / 三类事件注入（seed 可复现）│
└─────────────────────────────────────────────────────┘
```

## 快速开始

### 一键启动(推荐)

```bash
./start_demo.sh          # 完整启动:后端 :8000 + 前端 :5173
./start_demo.sh --mock   # 兜底模式:只起前端(离线 mock,无需后端)
```

脚本自动完成:依赖自检(Python/Node 缺失自动安装)、数据库构建(`aqua.db` 不存在时自动 seed)、
健康等待(轮询接口直到真正可访问)、端口复用(服务已在运行则直接复用)。Ctrl+C 优雅停止本脚本启动的服务。

- 前端: http://localhost:5173
- 后端 API: http://localhost:8000/api/v1
- API 文档: http://localhost:8000/docs

现场演示万一环境故障,`--mock` 模式前端全部走本地 mock 数据(含推理流回放),零外部依赖。

<details>
<summary>手动分步启动(不使用脚本时)</summary>

### 环境要求

- Python 3.11+
- 依赖：fastapi、uvicorn、langgraph、numpy、scipy、networkx、pydantic-settings（见 `backend/pyproject.toml`）

### 启动后端

```bash
cd backend
# 推荐：按已验证版本安装
pip install -r requirements.lock
pip install -e . --no-deps

# 开发依赖也可直接解析安装
# pip install -e ".[dev]"

# 1) 生成模拟数据（流域 + 90 天时序 + 3 条预置污染事件，约 3 秒）
python -m app.data.seed

# 2) 启动服务
uvicorn app.main:app --reload --port 8000
# API 文档: http://127.0.0.1:8000/docs

# 3) 跑测试（22 个引擎/数据单测）
pytest tests                 # 或 python scripts/run_tests.py（无 pytest 依赖的轻量 runner）
```

### 启动前端

```bash
cd frontend
npm install

# 开发(Mock 模式 VITE_MOCK=1 时无需后端,推理流走 public/mock 回放)
npm run dev          # http://localhost:5173
# /api 与 /api/v1/ws 由 Vite proxy 转发到 localhost:8000(需先启动后端)

npm run build        # tsc 类型检查 + 生产构建
npm run test         # vitest(store 与 WS 消息守卫单测)
```

### 配置 LLM（可选）

复制 `backend/.env.example` 为 `.env`，填入 OpenAI 兼容接口的 `AQ_LLM_API_KEY` /
`AQ_LLM_BASE_URL`（支持本地模型如 Ollama）。**不配置也能跑**——自动使用模板推理降级。

### 快速体验（不启动服务）

```bash
# 直接跑一遍"偷排事件 → 侦探推理 → 锁定 → 报告"全链路
python scripts/smoke_investigate.py evt_001
```

</details>

## 演示故事线（三条预置事件）

| 事件 | 类型 | 故事 | 溯源看点 |
|---|---|---|---|
| evt_001 | 夜间偷排 | 耀光金属表面处理夜间偷排电镀废水 | Cr⁶⁺ 从 0.003 飙至 0.55 mg/L（超标 11 倍），金属主导、COD 几乎不动——典型电镀指纹；夜间规律分析佐证 |
| evt_002 | 突发泄漏 | 恒泰精细化工储罐泄漏 | 高斯烟团随水流推进，COD 17→61、氨氮 0.66→4.9；传播时间校核锁定最近源 |
| evt_003 | 渐变恶化 | 城东污水处理厂处理能力下降 | 30 天缓慢爬坡，考验趋势检测（CUSUM/季节基线） |

现场演示时可用 `POST /api/v1/simulate/reset` 一键重置世界，或 `POST /api/v1/simulate/inject`
随时注入新事件（模拟真实事故的即时响应）。

## 验证结果

- 引擎单测 **22/22 通过**（异常检测/扩散/指纹/拓扑/规律/数据生成，含真值隔离与边界用例）
- 模拟观测先独立落库，调查引擎不读取 `truth_source`；真值只用于调查结束后的评测
- 三条预置事件全部正确锁定真凶：**耀光金属 96% / 恒泰化工 95% / 城东污水厂 97%**，
  与第二名嫌疑拉开清晰分差
- LangGraph 状态机接线验证通过（7 超步全链路：解析 → 假设 → 校核 → 结论 → 法规 → 处置 → 报告）
- 端到端 API 实测通过：事件注入、世界重置、WS 流式推送、调查回放、报告生成
- 前端单测 **7/7 通过**（WS 消息守卫、step 去重、状态分发）；前后端联调全链路实测通过

## 真实数据资产(太湖流域)

除模拟流域外,本项目接入**真实数据**验证算法在实战场景的可信度,全部数值仍走确定性纯函数。

| 资产 | 规模 | 来源 | 用途 |
|---|---|---|---|
| 国控站水质时序 | 105 断面 · 35 万条 · 2021-06~2025-10 · 4h 级 | 国家地表水水质自动监测系统 | 真实异常检测验证 |
| 河网拓扑 | 2082 河段 · NEXT_DOWN 有向图 | HydroRIVERS v1.0(太湖 bbox) | 真实上下游溯源 |
| 企业名录 | 37 家(印染/电镀/化工/制药/造纸/污水厂) | 锡山区政府公告 + gsxt 人工核验 | 真实排污源 |
| 排口级许可证 | 28 家有许可数据 · 418 条污染物记录 | 全国排污许可证平台(permit.mee.gov.cn)解析 | 企业排放指纹 |
| 降雨 | CHIRPS 全球月度(太湖裁剪) | UCSB CHIRPS | 水量平衡参考 |

**端到端溯源演示**(对标页 ③):钓邾大桥断面 2022-12-02 氨氮异常(CUSUM 检出,峰值 0.698 mg/L,约 7 倍基线,水质 Ⅱ→Ⅲ)→ 河网上溯 8.5km/4.6h → 命中无锡中发水务(锡北污水处理厂)。经 4 视角对抗核验:拓扑 confirmed(0.95)、异常 confirmed(0.78),时空一致性指出 4.6h 为距离排序分非因果证据,已诚实降级为"候选命中"并标注。

**指纹接入**:真实许可证主要污染物年排放量限值构成 `fingerprint_vector`(如污水厂 `{COD:575.9, NH3N:23.0}`),按行业轮转注入合成流域 18 企业的指纹库,`match_pollutants` 比对时用真实排放结构替换合成值。命中的锡北污水厂许可已注销,用同行业真实指纹做代理并如实标注。

**诚实声明**:演示流域为模拟数据,真实数据仅用于算法验证;真实断面异常的归因属候选命中,非真实污染事件认定。

## 目录结构

```
AquaDetective/
├── backend/                  # 后端（FastAPI + LangGraph）
│   ├── app/
│   │   ├── data/             # 数据引擎：流域构建/时序生成/指纹库/seed
│   │   ├── engine/           # 计算引擎：纯函数、无 LLM、可单测
│   │   ├── agents/           # 多智能体：状态机/5个Agent/工具/落盘
│   │   ├── api/              # REST + WebSocket
│   │   └── main.py           # 入口
│   ├── scripts/              # 验证/演示脚本（smoke、e2e、verify_*）
│   ├── tests/                # 22 个单测
│   └── README.md             # 后端详细说明
├── docs/
│   ├── 设计方案.md           # 产品与系统总方案
│   ├── 前端开发方案.md        # 前端分工方案
│   └── 后端开发方案.md        # 后端分工方案与 API 契约
├── data/                    # 真实数据资产(raw 不可变 → interim 清洗 → processed 标准化)
│   ├── raw/                 # 原始下载(国控站/许可证/HydroRIVERS/CHIRPS)
│   ├── interim/             # 清洗/裁剪(太湖子集、企业名录、排口原始粘贴)
│   └── processed/           # 标准化(guokong_taihu/、taihu_enterprises/、cnemc_archive/)
├── tools/                   # 真实数据流水线(import_taihu_subset/snap_enterprises/
│                            #   cnemc_archive/import_outlets/realdata_e2e_trace/validate_anomaly_real)
├── .github/workflows/       # CNEMC 前向存档定时工作流(cron */4h)
├── README.md                 # 本文件
└── frontend/                 # 前端（React + Vite）
    ├── package.json / pnpm-lock.yaml
    ├── vite.config.ts            # proxy /api 与 /ws 到 localhost:8000
    ├── index.html
    ├── .env.example              # VITE_API_BASE / VITE_WS_BASE / VITE_MOCK
    ├── public/
    │   └── mock/                 # Mock 数据(契约冻结前并行开发用,VITE_MOCK=1 时生
    │       ├── watershed.json      效,演示离线兜底)
    │       ├── series.json
    │       ├── eem.json
    │       ├── report.md
    │       └── recordings.json
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx               # 路由
    │   ├── api/                  # API 层,REST 封装,与 13 个端点一一对应
    │   │   ├── client.ts         # fetch 封装(基址/超时/错误统一处理)
    │   │   ├── watershed.ts
    │   │   ├── series.ts
    │   │   ├── events.ts
    │   │   ├── investigate.ts
    │   │   ├── report.ts
    │   │   └── simulate.ts
    │   ├── ws/
    │   │   ├── connection.ts     # WS 连接管理(自动重连、心跳)
    │   │   ├── messages.ts       # 消息类型定义(TypeScript 镜像契约)
    │   │   └── mockStream.ts     # 按契约回放 mock 推理流(演示兜底)
    │   ├── types/                # 契约 TS 类型:单一事实来源(nodes/edges/steps/...)
    │   ├── store/                # Zustand(流域/告警/调查/UI/扩散回放)
    │   │   ├── watershedStore.ts # 流域拓扑缓存
    │   │   ├── alertStore.ts     # 事件告警列表
    │   │   ├── investigationStore.ts # 当前调查:步骤流/假设/结论
    │   │   └── uiStore.ts        # 大屏模式/选中断面/时间窗
    │   ├── pages/
    │   │   ├── DashboardPage.tsx # 大屏主页(地图 + 告警 + 推理面板)
    │   │   ├── StationPage.tsx   # 断面详情(时序曲线 + EEM)
    │   │   ├── ReportPage.tsx    # 报告页(Markdown 渲染 + 打印)
    │   │   ├── ReplayPage.tsx    # 历史调查回放(答辩用)
    │   │   └── BenchmarkPage.tsx # 真实数据对标页(W5)
    │   ├── components/
    │   │   ├── map/
    │   │   │   ├── WatershedMap.tsx   # 流域底图
    │   │   │   ├── StationLayer.tsx   # 断面状态着色(绿/黄/红)
    │   │   │   ├── EnterpriseLayer.tsx# 企业/排污口标注
    │   │   │   └── DispersionLayer.tsx# 扩散动画(浓度随时间流动)
    │   │   ├── reasoning/
    │   │   │   ├── ReasoningPanel.tsx # 推理流式面板(核心)
    │   │   │   ├── StepCard.tsx       # 单步"线索→推理→证据"卡片
    │   │   │   ├── EvidenceChip.tsx   # 证据条(eem_score 等)
    │   │   │   ├── HypothesisBoard.tsx# 假设排行榜(分数实时变化)
    │   │   │   └── AgentTalk.tsx      # Agent 会议气泡对话
    │   │   ├── charts/
    │   │   │   ├── SeriesChart.tsx    # 断面时序曲线
    │   │   │   ├── EemContour.tsx     # EEM 等高线图(并排对比)
    │   │   │   └── ConfidenceBar.tsx  # 嫌疑企业置信度条形图
    │   │   ├── alert/
    │   │   │   └── AlertList.tsx      # 告警面板(可触发调查)
    │   │   └── demo/
    │   │       ├── ScenarioBar.tsx    # 三条演示脚本一键启动/重置
    │   │       └── InjectDialog.tsx   # 手动注入事件表单
    │   └── styles/               # Tailwind 配置与全局样式
    └── tests/                    # vitest 单测
```

## API 一览（前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/watershed` | 全流域拓扑（节点/边/断面/企业/指纹） |
| GET | `/watershed/enterprises/{id}/fingerprint` | 企业双指纹 |
| GET | `/watershed/enterprises/{id}/eem` | 企业档案 EEM（与现场同网格，并排对比） |
| GET | `/stations/{id}/eem?event_id=` | 断面"现场"EEM 荧光矩阵（61×71） |
| GET | `/series?station=&indicator=&from=&to=` | 断面时序数据 |
| GET | `/events?status=` | 污染事件列表（告警面板） |
| POST | `/events/{id}/investigate` | 触发溯源调查 |
| GET | `/investigations/{id}` | 调查状态与推理记录 |
| GET | `/investigations/{id}/report` | Markdown 溯源报告 |
| POST | `/simulate/reset?seed=` | 一键重建世界 |
| POST | `/simulate/inject` | 运行时注入污染事件 |
| GET | `/recordings` · `/recordings/{id}` | 历史调查回放 |
| WS | `/ws?investigation_id=` | 推理过程流式推送 |

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.11 · FastAPI · uvicorn |
| Agent 编排 | LangGraph（状态机 + 条件路由） |
| 计算 | NumPy · SciPy · NetworkX |
| 数据 | SQLite（运行时）· JSON（流域配置） |
| LLM | OpenAI 兼容接口（可切换本地模型，失败自动降级） |
| 前端 | React 18 · TypeScript · Vite · MapLibre · ECharts · Tailwind · Zustand |

## 当前状态与路线图

- ✅ **已完成**：数据引擎、计算引擎、多智能体推理、REST + WebSocket API、
  前端大屏（地图/推理流/扩散回放/指纹比对/报告/回放/对标页）、测试与验证脚本
- ✅ **真实数据**：太湖 105 国控断面 + 37 家企业 + 排口级许可证 + HydroRIVERS 河网;
  真实断面异常端到端溯源演示(钓邾大桥氨氮→锡北污水厂,指纹+拓扑双证据);
  真实许可证指纹向量接入溯源系统;CNEMC 前向存档 GitHub Actions 定时工作流
- 🔄 **进行中**：与 LLM 真实链路联调
- 📋 **后续规划**：法规 RAG 向量检索化、评分权重调优、答辩演示打磨

## 团队

- 后端：Jesse
- 前端：advent
