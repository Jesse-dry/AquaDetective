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
  ts: number // 毫秒 epoch,前端只做格式化
  value: number
}

// ---------- /events ----------
export type Severity = 'low' | 'medium' | 'high'
export type EventType = 'sudden' | 'periodic' | 'gradual'
export type EventStatus = 'open' | 'investigating' | 'resolved'

export interface PollutionEvent {
  id: string
  station_id: string
  indicators: string[]
  onset_ts: number
  severity: Severity
  etype: EventType
  truth_source?: string
  status: EventStatus
}

// ---------- /investigations ----------
export interface Investigation {
  id: string
  event_id: string
  started_at: number
  status: 'running' | 'resolved' | 'failed'
  conclusion: ConclusionData | null
}

// ---------- WS 消息(固定 6 类) ----------
export interface Evidence {
  kind: string // eem_score / pollutant_score / topology / dispersion / pattern ...
  target: string
  value: number
}

export interface StepData {
  step_id: string
  phase: string // topology_filter / dispersion_check / fingerprint_match / pattern_check ...
  clue: string
  reasoning: string
  evidence: Evidence[]
  status: string // verified / rejected / ...
}

export interface HypothesisData {
  id: string
  target: string // 企业 id
  score: number
  status: string // candidate / eliminated / confirmed
}

export interface AgentTalkData {
  agent: string // monitor / investigator / compliance / responder / reporter
  text: string
}

export interface ConclusionData {
  source_id: string
  confidence: number
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
  lex: number[] // 激发波长轴
  lem: number[] // 发射波长轴
  matrix: number[][] // matrix[i][j],i 对应 lem 行,j 对应 lex 列
}

// ---------- /recordings ----------
export interface Recording {
  id: string
  event_id: string
  started_at: number
  status: string
}
