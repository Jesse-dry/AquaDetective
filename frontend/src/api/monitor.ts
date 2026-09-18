import { apiGet, apiPost } from './client'

export interface ScanResult {
  created_count: number
  scanned_series: number
  unchanged_series: number
  insufficient_series: number
  extended_series: number
  latest_data_ts: number | null
  events: { id: string; station_id: string; indicator: string; ts: number; severity: string }[]
}

export type MonitorHit = ScanResult['events'][number]

export interface MonitorStatus {
  enabled: boolean
  interval_s: number
  window_h: number
  method: string
  running: boolean
  scheduler_running: boolean
  scan_count: number
  total_created: number
  last_scan_ms: number | null
  last_duration_ms: number | null
  last_created: number
  next_scan_ms: number | null
  recent: MonitorHit[]
  server_ms: number
  last_started_at: number | null
  last_finished_at: number | null
  last_result: ScanResult | null
  last_error: string | null
}

export const getMonitorStatus = () => apiGet<MonitorStatus>('/monitor/status')
export const scanNow = () => apiPost<ScanResult>('/monitor/scan')

export const configureMonitor = (body: {
  enabled?: boolean; interval_s?: number; window_h?: number; method?: string
}) => apiPost<MonitorStatus>('/monitor/config', body)
