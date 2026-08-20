// 契约 TS 类型:与 docs/API契约.md / README "API 一览" 对齐
// 变更需与后端双方确认

// ---------- /watershed ----------
export interface WatershedNode {
  id: string
  name: string
  kind: 'source' | 'segment' | 'confluence' | 'outlet'
  x: number
  y: number
  flow: number
  velocity: number
  k: number
}

export interface WatershedEdge {
  from_node: string
  to_node: string
  distance_m: number
}

export interface Station {
  id: string
  node_id: string
  interval_min: number
  indicators: string[]
}

export interface Enterprise {
  id: string
  name: string
  industry: string
  node_id: string
  discharge_pattern: Record<string, unknown>
}

export interface SpectrumPeak {
  lex: number
  lem: number
  amp: number
  sigma: number
}

export interface Fingerprint {
  enterprise_id: string
  spectrum: SpectrumPeak[]
  pollutants: Record<string, number>
}

export interface Watershed {
  nodes: WatershedNode[]
  edges: WatershedEdge[]
  stations: Station[]
  enterprises: Enterprise[]
  fingerprints?: Fingerprint[]
}

// ---------- /series ----------
export interface SeriesPoint {
  ts: number // 毫秒级 epoch
  value: number
}

export interface SeriesResponse {
  station: string
  indicator: string
  count: number
  data: SeriesPoint[]
}

// ---------- /events ----------
export type Severity = 'low' | 'medium' | 'high'
export type EventType = 'sudden' | 'periodic' | 'gradual'
export type EventStatus = 'open' | 'investigating' | 'resolved'

export interface PollutionEvent {
  id: string
  station_id: string
  indicators: string[] // 后端可能给 JSON 字符串,api 层已归一化为数组
  onset_ts: number //   毫秒级 epoch
  severity: Severity
  etype: EventType
  truth_source?: string
  status: EventStatus
}

// ---------- /investigations ----------
export interface Investigation {
  id: string
  event_id: string
  started_at: number // 毫秒级 epoch
  status: 'running' | 'resolved' | 'failed'
  conclusion: ConclusionData | null
  stream?: WsMessage[] // 后端附带完整推理记录,WS 断线补齐用
}

// ---------- WS 消息(固定 6 类;另有控制消息 connected/error,渲染层忽略) ----------
export interface Evidence {
  kind: string // eem_score / pollutant_score / topology / dispersion / pattern / event
  target?: string // parse 步的事件证据无 target
  value: number | Record<string, unknown> // 大多数为 0~1 分值;parse 步为事件原始字段
  detail?: string
  rank?: number
}

export interface StepData {
  step_id: string
  phase: string // 后端直接给中文标签:事件解析 / 证据校核·eem / 排除假设 ...
  clue: string
  reasoning: string
  evidence: Evidence[]
  status: string // verified / rejected
}

export interface HypothesisData {
  id: string
  target: string // 注意:后端推的是企业名称,不是 id
  industry?: string
  reasons?: string
  score: number
  status: string // candidate / rejected
}

export interface AgentTalkData {
  agent: string // 后端给中文名:监测Agent / 溯源侦探 / 法规Agent / 处置Agent / 报告Agent
  text: string
}

export interface ConclusionData {
  source_id: string | null
  source_name?: string | null
  industry?: string
  confidence: number
  status?: string
  evidence_summary: string
}

export interface FailedData {
  reason: string
  suggestions: string[]
}

export interface ReportReadyData {
  report_id: string
}

export type WsMessage =
  | { type: 'step'; data: StepData }
  | { type: 'hypothesis'; data: HypothesisData }
  | { type: 'agent_talk'; data: AgentTalkData }
  | { type: 'conclusion'; data: ConclusionData }
  | { type: 'failed'; data: FailedData }
  | { type: 'report_ready'; data: ReportReadyData }

// ---------- EEM ----------
export interface EemMatrix {
  lex: number[] // 激发波长轴(61 点)
  lem: number[] // 发射波长轴(71 点)
  eem: number[][] // eem[i][j],i 对应 lex 行,j 对应 lem 列
  dominant?: string // 权重最大企业 id(仅现场 EEM 返回)
}

// ---------- /recordings ----------
// GET /recordings 返回 { recordings: string[] }(仅调查 id 列表)
export interface RecordingList {
  recordings: string[]
}
