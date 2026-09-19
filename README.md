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
| 🤖 多智能体协作 | 监测 / 溯源侦探 / 法规 / 处置 / 报告 五个 Agent。监测 Agent 后台定时扫描断面时序自动生成告警(大屏状态条可见可暂停),其余四个由 LangGraph 状态机编排 |
| 🛡️ 防幻觉护城河 | 数值全部来自确定性引擎（NumPy/SciPy/NetworkX），LLM 无编造数据的工具 |
| 📡 流式推理展示 | WebSocket 实时推送 6 类消息（step/hypothesis/agent_talk/conclusion/failed/report_ready） |
| 🎲 可复现演示 | 模拟数据同 seed 逐字节可复现，一键重置世界，现场注入任意事件 |
| 🔌 无 LLM 也能跑 | 未配置 API Key 时自动降级为模板推理，完整调查流程照常工作 |
| 📼 全程可回放 | 每次调查推理过程落盘 JSONL，一键回放（答辩利器） |

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│  展示层  Web 大屏(React + Vite)                       │
│          流域地图 / 推理流 / 扩散回放 / 指纹比对 / 报告  │
├─────────────────────────────────────────────────────┤
│  API 层  FastAPI:REST 端点 + WebSocket 推理流         │
├─────────────────────────────────────────────────────┤
│  Agent 层  监测Agent(后台定时扫描 → 生成告警事件)       │
│    LangGraph 侦探式状态机:溯源Agent(侦探主编排)          │
│    → 法规Agent → 处置Agent → 报告Agent                 │
│    推理状态: parse → 假设生成 → 证据校核循环 → 排除/锁定  │
├─────────────────────────────────────────────────────┤
│  计算引擎  确定性纯函数(LLM 不可触碰)                  │
│    异常检测(3σ/CUSUM/EWMA/季节基线) / 高斯烟团扩散       │
│    / EEM+污染物双指纹 / 拓扑溯源 / 昼夜规律分析          │
├─────────────────────────────────────────────────────┤
│  数据层  清源河模拟流域(27 节点 / 10 断面 / 18 企业)    │
│    90 天时序生成器 / 双指纹库 / 三类事件注入(seed 可复现)│
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
- API 文档: http://localhost:8000/docs
- 事件接口(示例): http://localhost:8000/api/v1/events

现场演示万一环境故障,`--mock` 模式前端全部走本地 mock 数据(含推理流回放),零外部依赖。

<details>
<summary>手动分步启动(不使用脚本时)</summary>

### 环境要求

- Python **3.11+**、Node 18+
- 依赖：fastapi、uvicorn、langgraph、numpy、scipy、networkx、pydantic-settings（见 `backend/pyproject.toml`）

**Node.js 注意**：前端 dev server 需要 **Node.js 18+**（Vite 5 的要求）。脚本会在启动前检查，
缺失时直接给出安装命令而不是走到一半报 `node: command not found`。Windows 上装了 Node 后
**需要重开终端**让 PATH 生效（Git Bash 不会自动继承）。

**Windows 注意**：`./start_demo.sh` 是 bash 脚本，**cmd / PowerShell 下无法直接运行**（Windows 无 bash，
且 `.sh` 不是可执行格式）。两种可用方式：

- **Git Bash**（装 Git for Windows 时自带）：`./start_demo.sh` 可直接用。注意此时 Python 是 Windows 版，
  venv 的解释器在 `.venv/Scripts/python.exe`（不是 `bin/python`）——脚本已按平台两种布局探测
- **WSL**：`./start_demo.sh` 直接用（本项目的开发环境）

Python 需自行安装（python.org 版并勾选 *Add to PATH*，或 `winget install Python.Python.3.12`）；
Windows 不自带满足 3.11+ 的 Python。

**macOS 注意**：系统只自带 `python3`（版本 3.9，**不满足 3.11+**），且没有 `python` / `pip`
命令——它们只存在于虚拟环境里。所以要么 `brew install python@3.12`，要么按下面的步骤建 venv。
`./start_demo.sh` 会自动探测可用的解释器（优先项目内 `.venv`，其次 `python3`），
版本不够时会直接给出提示，不会跑到一半才报错。

```bash
# macOS 首次准备(建 venv 后,venv 里才有 python / pip)
brew install python@3.12          # 或从 python.org 装 3.12
cd backend && python3.12 -m venv .venv && source .venv/bin/activate
```

### 启动后端

```bash
cd backend
# 推荐：按已验证版本安装
pip install -r requirements.lock
pip install -e . --no-deps

# 仅数据导入器(app/ingest/)需要 pandas,演示与测试都不需要:
# pip install -r requirements-ingest.lock

# 开发依赖也可直接解析安装
# pip install -e ".[dev]"

# 1) 生成模拟数据（流域 + 90 天时序 + 3 条预置污染事件，约 3 秒）
python -m app.data.seed

# 2) 启动服务
uvicorn app.main:app --reload --port 8000
# API 文档: http://127.0.0.1:8000/docs

# 3) 跑测试（66 个后端测试：引擎纯函数 / 监测调度 / 真值隔离 / 评测口径）
pytest tests
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

### 快速体验（不启动服务）

```bash
# 直接跑一遍"偷排事件 → 侦探推理 → 锁定 → 报告"全链路
python scripts/smoke_investigate.py evt_001
```

</details>

### 配置 LLM（可选）

复制 `backend/.env.example` 为 `.env`，填入 OpenAI 兼容接口的三项即可，**所有 Agent 共用**：

```bash
cd backend && cp .env.example .env
```

```env
AQ_LLM_BASE_URL=https://api.deepseek.com/v1
AQ_LLM_API_KEY=sk-你的key
AQ_LLM_MODEL=deepseek-chat
AQ_LLM_TIMEOUT_S=30
AQ_LLM_MAX_TOKENS=4096
```

> **推理模型注意**：`deepseek-reasoner` / o 系这类模型会**先输出思维链、正文才在后面**。
> `AQ_LLM_MAX_TOKENS` 给小了会出现「正文为空 + `finish_reason=length`」，表现为**静默降级为
> 模板推理**（配了 key、`/health` 也是 `llm:true`，但推理流看不出差别）。默认 4096；
> 若后端日志出现 `LLM 返回空内容(finish_reason=length ...)`，把它调大即可。
> 调用失败、返回空、返回非 JSON 都会**打 WARNING 日志**（`app/agents/llm.py`），不再静默吞掉。

常见 OpenAI 兼容服务（以各家官方文档为准）：

| 服务 | `AQ_LLM_BASE_URL` | `AQ_LLM_MODEL` 示例 |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 阿里通义 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4` |
| 月之暗面 Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 本地 Ollama | `http://localhost:11434/v1` | `qwen2.5:7b`（key 随便填） |

**不配置也能跑**——自动使用模板推理降级，完整调查流程照常工作。

**LLM 在这套系统里只做一件事**：给每个嫌疑企业追加一段推理理由（`generate_hypotheses`，
全仓库唯一的 LLM 调用点）。推理流里的其余文字——事件解析、证据校核、结论、法规、处置、
报告——**全部由确定性引擎产出**，这正是「数值与事实不经过大模型」这条铁律的体现。

所以：配了 LLM 之后，推理流**看起来不会有翻天覆地的变化**，差别集中在嫌疑企业后面那段
理由上；反过来，`/health` 显示 `llm:true` 也不代表调用成功，要看日志或对比理由文字。

**改完 `.env` 怎么让它生效**：

- `./start_demo.sh` 启动的后端带 `--reload-include .env`，**保存 `.env` 即自动重载**
- 手动启动的加同样参数：`uvicorn app.main:app --reload --reload-include .env`
- 脚本若提示"**复用既有进程**"，说明端口上已有旧服务，它不会应用本次 `.env` 改动 ——
  需先停掉旧服务再启动
- **自检**：`curl -s localhost:8000/health` → `"llm":true` 表示已读到 API Key；
  `false` 说明配置没加载（多为服务比 `.env` 早启动）

#### 按 Agent 覆盖（可选）

默认所有 Agent 共用上面这套配置。若想让不同 Agent 走不同模型／不同服务，
用 `AQ_LLM_<AGENT>_*` 覆盖对应字段（可覆盖 `API_KEY` / `BASE_URL` / `MODEL` / `TIMEOUT_S`）：

| Agent 名 | 覆盖哪些节点 |
|---|---|
| `INVESTIGATOR` | 溯源侦探：事件解析、假设生成、证据校核、结论 |
| `COMPLIANCE` | 法规 Agent |
| `RESPONDER` | 处置 Agent |
| `REPORTER` | 报告 Agent |

```env
# 溯源侦探用推理更强的模型
AQ_LLM_INVESTIGATOR_MODEL=deepseek-reasoner
# 报告 Agent 用便宜的就够
AQ_LLM_REPORTER_MODEL=deepseek-chat
# 法规 Agent 走本地模型（不联网）
AQ_LLM_COMPLIANCE_BASE_URL=http://localhost:11434/v1
AQ_LLM_COMPLIANCE_API_KEY=ollama
AQ_LLM_COMPLIANCE_MODEL=qwen2.5:7b
```

未填写的字段自动回落到全局默认值；**一项都不配时，各 Agent 与全局配置完全一致**（即维持现状）。
实现见 `backend/app/config.py` 的 `llm_profile(agent)` 与 `backend/app/context.py` 的 `get_llm(agent)`。

### 监测 Agent 配置（可选）

监测 Agent 在服务启动时拉起一个后台任务，按固定间隔扫描全部断面的最近时序，
检出异常即生成待溯源事件（`evt_scan_NNN`，真值未知）。大屏顶部状态条可看运行状态、
手动触发扫描、随时暂停巡检。增量扫描会记录每个序列的进度（`monitor_cursors`），
未推进的序列直接跳过。

```env
AQ_MONITOR_ENABLED=true   # 是否启用后台定时扫描(默认 true;false 则只响应手动扫描)
AQ_MONITOR_INTERVAL_S=300 # 扫描间隔秒数(默认 300,允许 10~86400)
AQ_MONITOR_WINDOW_H=24    # 每次扫描回看的窗口小时数(默认 24,允许 1~2160)
AQ_MONITOR_METHOD=seasonal # 检测方法:cusum|ewma|threesigma|seasonal(默认 seasonal)
```

报警判定有两条门槛（`backend/app/engine/anomaly.py` 的 `significant`）：
峰值偏离须超过「3×基线稳健标准差」与「5×量化分辨率」的较大者，且相对基线涨幅 ≥20%。
第二条门槛用于排除量化噪声误报——低浓度指标（如 Cr⁶⁺ 只有 0.002/0.003/0.004 三档）
会让稳健标准差退化为 0，使 CUSUM 的 z 值虚高，从而在毫无意义的 0.001 mg/L 波动上报警。

**为什么默认用季节基线**：干净序列的日内极差达均值的 40%，日内基线（cusum/ewma/
3σ 都取窗口内的基线）无法区分昼夜规律与污染，检出率只有 30% 且要靠"浓度翻倍"
兜住误报；同刻基线把昼夜规律扣掉后检出率 70%、误报 0。季节基线需要 8 天历史
（`period × 8` 个采样点），历史不足的序列会被计为 `insufficient_series` 并跳过。

**同一次污染只报一条事件**：一次排放常同时顶起多个断面、多个指标，若逐个断面报警，
一次污染会刷出好几条告警。`engine/topology.py` 的 `group_detections` 按河网上下游关系
与传播时间把它们并成一组（下游检出时刻须落在 `[上游−2h, 上游+传播时间+3h]` 内），
合并后的事件：

- 锚点断面 = 组内**最上游**断面（离污染源最近，溯源最有价值）
- 指标取并集，严重度取最高，起报时刻取最早
- `affected_stations` 记录全部波及断面，告警卡片显示「波及 N 个断面」
- 去重按「断面 + 指标」在 ±48h 内是否已报过（任何状态，且认得合并事件的波及断面），
  因此同一污染在下游断面不会二次报警

实测：一次注入在 5 个断面、2 个指标上共 9 条检出 → **1 条事件**，锚点为真值首达断面；
连续复扫不再新增。

**监测类事件如何溯源**：监测 Agent 自动检出的事件没有实验室观测——在线监测站只测浓度，
不出三维荧光谱（EEM 需要采样送检）。此时系统**不会拿"背景值"硬凑一条证据**（背景 EEM
与谁都比得像，实测前三名 0.973/0.948/0.946，等于给排名注入噪声），而是：

- **EEM 通道不参与打分**；把它的权重并入指纹通道（污染物 0.25 → 0.65）。证据来源换了，
  权重总量不变；若让权重凭空消失，可用池只剩「污染物 0.25 + 传播强度 0.15」，
  拓扑"谁离断面近"会占掉近四成，前四名会全是最近的污水处理厂
- **污染物向量由实测浓度相对事件前基线的增量构造**（`vector_from_excess`）

实测完整链路：静默注入彩云印染厂 → 点「立即扫描」→ 监测 Agent 生成告警 → 侦查
→ **判定彩云印染厂，置信度 0.73**。

**污染物组成的单一事实来源**：模拟器里曾经并存三套互不一致的"企业污染物组成"——
逐企业合成指纹、真实许可证库（按行业轮转覆盖）、以及生成读数用的排放浓度。覆盖后
从读数推导的证据永远对不上库，实测真凶在污染物通道排 17/18、监测类事件无法溯源。
现在统一到**逐企业合成指纹**，并保证「排放 → 观测 → 比对库」三者同源：

- 现场观测与比对库都取合成指纹（`rank_pollutants` 不再被许可证库覆盖）
- 指纹的定义是 `normalize(sqrt(排放浓度))`（sqrt 压缩主导指标以放大特征污染物差异），
  故由读数推导证据时也要做同样的变换——两者必须在同一空间才可比

真实许可证的污染物年排放量改为**对标页的数据资产展示**（见下文"真实数据资产"）。


## 演示故事线（三条预置事件）

| 事件 | 类型 | 故事 | 溯源看点 |
|---|---|---|---|
| evt_001 | 夜间偷排 | 耀光金属表面处理夜间偷排电镀废水 | Cr⁶⁺ 从 0.003 飙至 0.55 mg/L（超标 11 倍），金属主导、COD 几乎不动——典型电镀指纹；夜间规律分析佐证 |
| evt_002 | 突发泄漏 | 恒泰精细化工储罐泄漏 | 高斯烟团随水流推进，COD 17→61、氨氮 0.66→4.9；传播时间校核锁定最近源 |
| evt_003 | 逐渐恶化 | 城东污水处理厂处理能力下降 | 30 天缓慢爬坡，考验趋势检测（CUSUM/季节基线） |

现场演示时可用 `POST /api/v1/simulate/reset` 一键重置世界，或 `POST /api/v1/simulate/inject`
随时注入新事件(模拟真实事故的即时响应)，`DELETE /api/v1/simulate/events/{id}` 删除注入事件(预置事件受保护)。

## 验证结果

- 后端测试 **66/66 通过**(`cd backend && python -m pytest tests`;含引擎纯函数、
  监测调度与并发去重、真值隔离、评测口径)
- 模拟观测先独立落库，调查引擎不读取 `truth_source`；真值只用于调查结束后的评测
- 三条预置事件全部正确锁定真凶：**耀光金属 78% / 恒泰化工 79% / 城东污水厂 77%**(模板推理模式实测)
- 批量评测(`python scripts/batch_eval.py`，30 轮随机注入，报告见 `data/processed/batch_eval_report.json`)：

  | 指标 | 结果 |
  |---|---|
  | 预警检出率（首达断面） | **70%**(21/30) |
  | 预警检出率（任一受污染断面） | **77%**(23/30) |
  | 干净数据常驻误报 | **0** 个(断面,指标) |
  | 上游候选召回率 | **87%**(26/30) |
  | Top-1 / Top-3 命中率 | **87%** / **87%** |
  | 最终锁定命中率 | **87%**(26/30) |
  | MRR | **0.867** |
  | 传播时间误差(均值/最大) | **0.04h / 0.10h** |
  | 分类型检出 | sudden **100%** · periodic **80%** · gradual **30%** |
  | 分类型 Top-1 | sudden 90% / periodic 80% / gradual 90% |

  > 检出率的**前提是误报为零**。干净序列的日内极差达均值的 40%（昼夜规律），
  > 用日内基线或日内阈值都会把日波动当污染，在干净数据上常驻报出告警，
  > 使检出率虚高（实测可虚高到 67%/97%）。因此本表在报检出率的同时报常驻误报数。
  >
  > 该指标历史上写过 100%，是口径问题层层叠加的结果：把"扫到任何告警"当命中、
  > 注入时点落在扫描窗口外、量化噪声误报、逐轮污染累积、类型与严重度在评测里
  > 被绑死（突发恒 low / 周期恒 medium / 渐变恒 high，分类型数字实为组合数）、
  > 以及拿"检出但严重度=low"当漏检。以上均已修正，评测内置**归因口径**
  > （扣掉干净基线上的常驻告警）与**常驻误报计数**，两者都会打印。
  >
  > 检测方法默认 `seasonal`（同刻基线，唯一能区分昼夜规律与污染的做法），
  > 阈值 k=4.5：实测 k=3.0 会常驻 9 个误报，4.5 归零而检出仅从 73% 降到 70%
  > （真实污染偏离远大于噪声，抬阈值几乎不损检出）。
  > 24h 窗口下周期性、渐变检测仍需改进；以上溯源排名对全部注入事件单独计算，并非自动检出后的端到端成功率。

- **两条溯源路径均端到端实测通过**：①有案卷的事件(预置 + 手动注入)②监测 Agent 自主检出的事件
  (静默注入彩云印染厂 → 扫描 → 侦查 → 判定彩云印染厂,置信度 0.73)
- LangGraph 状态机接线验证通过(7 超步全链路：解析 → 假设 → 校核 → 结论 → 法规 → 处置 → 报告)
- 端到端 API 实测通过：事件注入、世界重置、WS 流式推送、调查回放、报告生成、注入事件删除
- 前端单测 **8/8 通过**(WS 消息守卫、step 去重、状态分发)；前后端联调全链路实测通过

## 真实数据资产(太湖流域)

除模拟流域外,本项目接入**真实数据**验证算法在实战场景的可信度,全部数值仍走确定性纯函数。

| 资产 | 规模 | 来源 | 用途 |
|---|---|---|---|
| 国控站水质时序 | 105 断面 · 35 万条 · 2021-06~2025-10 · 4h 级 | 国家地表水水质自动监测系统 | 真实异常检测验证 |
| 河网拓扑 | 2082 河段 · NEXT_DOWN 有向图 | HydroRIVERS v1.0(太湖 bbox) | 真实上下游溯源 |
| 企业名录 | 37 家(印染/电镀/化工/制药/造纸/污水厂) | 锡山区政府公告 + gsxt 人工核验 | 真实排污源 |
| 排口级许可证 | 28 家有许可数据 · 418 条污染物记录 | 全国排污许可证平台(permit.mee.gov.cn)解析 | 企业排放指纹 |
| 降雨 | CHIRPS 全球月度(太湖裁剪) | UCSB CHIRPS | 水量平衡参考(已入库,代码未引用) |
| CNEMC 实时存档 | 持续累积 | 国家地表水水质自动监测实时发布系统 | GitHub Actions 定时存档(数据积累) |

**端到端溯源演示**(对标页 ③):钓邾大桥断面 2022-12-02 氨氮异常(CUSUM 检出,峰值 0.698 mg/L,约 7 倍基线,水质 Ⅱ→Ⅲ)→ 河网上溯 8.5km/4.6h → 命中无锡中发水务(锡北污水处理厂)。经 4 视角对抗核验:拓扑 confirmed(0.95)、异常 confirmed(0.78),时空一致性指出 4.6h 为距离排序分非因果证据,已诚实降级为"候选命中"并标注。

**指纹接入**:真实许可证主要污染物年排放量限值构成 `fingerprint_vector`(如污水厂 `{COD:575.9, NH3N:23.0}`),用于**对标页展示与数据资产声明**。

> 曾把真实指纹按行业轮转**覆盖**合成流域 18 企业的指纹库,现已停用(`_injected_pollutant_lib`
> 保留实现但不在排序路径上)。原因:模拟器里会出现三套互不一致的污染物组成 —— 逐企业合成指纹、
> 许可证库、以及生成读数用的排放浓度。覆盖后从读数推导的证据永远对不上库,实测真凶在污染物
> 通道排 17/18、监测类事件无法溯源。溯源排序统一用逐企业合成指纹(与排放、观测同源)。

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
│   ├── scripts/              # 验证/演示脚本(smoke_investigate/e2e_api/batch_eval/verify_*)
│   ├── tests/                # 27 个单测(引擎/数据/导入/真值隔离)
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
    │   │   ├── playbackStore.ts # 扩散回放(时间游标/热力/重放/跳终点)
    │   │   └── uiStore.ts        # 大屏模式/选中断面/打字机开关
    │   ├── pages/
    │   │   ├── DashboardPage.tsx # 大屏主页(地图 + 告警 + 推理面板)
    │   │   ├── StationPage.tsx   # 断面详情(时序曲线 + EEM)
    │   │   ├── ReportPage.tsx    # 报告页(Markdown 渲染 + 打印)
    │   │   ├── ReplayPage.tsx    # 历史调查回放(答辩用)
    │   │   └── BenchmarkPage.tsx # 真实数据对标页(6 节)
    │   ├── components/
    │   │   ├── map/
    │   │   │   ├── WatershedMap.tsx   # 流域底图(断面/企业/HTML 标签碰撞布局)
    │   │   │   └── DispersionLayer.tsx# 扩散回放控制条(浓度随时间流动)
    │   │   ├── reasoning/
    │   │   │   ├── ReasoningPanel.tsx # 推理流式面板(核心,贴近底部才自动跟随)
    │   │   │   ├── StepCard.tsx       # 单步"线索→推理→证据"卡片(打字机动画)
    │   │   │   ├── Typewriter.tsx    # 打字机效果(可跳过,StrictMode 安全)
    │   │   │   ├── EvidenceChip.tsx   # 证据条(eem_score 等)
    │   │   │   ├── HypothesisBoard.tsx# 假设排行榜(分数实时变化)
    │   │   │   └── AgentTalk.tsx      # Agent 会议气泡对话
    │   │   ├── charts/
    │   │   │   ├── SeriesChart.tsx    # 断面时序曲线
    │   │   │   ├── EemContour.tsx     # EEM 等高线图(并排对比)
    │   │   │   ├── ConfidenceBar.tsx  # 嫌疑企业置信度条形图
    │   │   │   ├── RealDataValidation.tsx # 真实异常检测验证(太湖)
    │   │   │   ├── E2ETraceCase.tsx   # 真实端到端溯源(太湖)
    │   │   │   └── PermitEnterprises.tsx  # 企业许可+指纹向量
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
| GET | `/series?station=&indicator=&from=&to=` | 断面时序数据(from/to 毫秒 epoch) |
| GET | `/events?status=` | 污染事件列表（告警面板） |
| POST | `/monitor/scan` | 立即扫描观测并生成监测告警 |
| GET | `/monitor/status` | 监测配置、运行状态与最近结果 |
| POST | `/monitor/config` | 暂停/恢复及运行时监测参数 |
| POST | `/events/{id}/investigate` | 触发溯源调查 |
| GET | `/investigations/{id}` | 调查状态与推理记录 |
| GET | `/investigations/{id}/report` | Markdown 溯源报告 |
| POST | `/simulate/reset?seed=` | 一键重建世界 |
| POST | `/simulate/inject` | 运行时注入污染事件 |
| DELETE | `/simulate/events/{id}` | 删除注入事件(仅 evt_inj_ 前缀) |
| GET | `/recordings` | 历史调查列表(附事件摘要) |
| GET | `/recordings/{id}` | 单条录音 stream(回放) |
| DELETE | `/recordings/{id}` | 删除历史录音 |
| GET | `/monitor/status` | 监测 Agent 运行状态(状态条轮询) |
| POST | `/monitor/scan` | 立即执行一次断面异常扫描 |
| POST | `/monitor/config` | 调整监测开关/间隔/窗口 |
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
  前端大屏(地图/推理流/扩散回放/指纹比对/报告/回放/对标页 5 页面)、
  测试与验证脚本、一键启动(`start_demo.sh`)、批量评测(`batch_eval.py`)
- ✅ **真实数据**：太湖 105 国控断面 + 37 家企业 + 排口级许可证 + HydroRIVERS 河网;
  真实断面异常端到端溯源演示(钓邾大桥氨氮→锡北污水厂,指纹+拓扑双证据);
  真实许可证指纹向量接入溯源系统;CNEMC 前向存档 GitHub Actions 定时工作流
- 📋 **后续规划**：法规 RAG 向量检索化、置信度校准曲线、Cuyahoga 基准溯源评测、
  真实数据持续入库与监测阈值校准、Docker 部署与鉴权(详见 `docs/后续开发计划.md` §10 剩余缺口)

## 团队

- 后端：Jesse
- 前端：advent
