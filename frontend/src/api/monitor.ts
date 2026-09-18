import { apiGet, apiPost } from './client'

// 监测 Agent 检出的事件摘要(状态条"最近检出"用)
export interface MonitorHit {
  id: string
  station_id: string
  indicator: string
  ts: number
  severity: string
  zscore: number
}

// GET /monitor/status 监测 Agent 运行状态(时间戳为毫秒 epoch)
export interface MonitorStatus {
  enabled: boolean
  interval_s: number
  window_h: number
  running: boolean
  scan_count: number
  total_created: number
  last_scan_ms: number | null
  last_duration_ms: number | null
  last_created: number
  last_error: string | null
  next_scan_ms: number | null
  recent: MonitorHit[]
  server_ms: number
}

export const getMonitorStatus = () => apiGet<MonitorStatus>('/monitor/status')

// POST /monitor/scan 立即扫描一次
export const scanNow = () =>
  apiPost<{ created: MonitorHit[]; count: number; duration_ms: number }>('/monitor/scan')

// POST /monitor/config 调整开关/间隔
export const configureMonitor = (body: { enabled?: boolean; interval_s?: number }) =>
  apiPost<MonitorStatus>('/monitor/config', body)
