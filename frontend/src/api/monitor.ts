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

export interface MonitorStatus {
  enabled: boolean
  interval_s: number
  window_h: number
  method: string
  running: boolean
  last_started_at: number | null
  last_finished_at: number | null
  last_result: ScanResult | null
  last_error: string | null
}

export const getMonitorStatus = () => apiGet<MonitorStatus>('/monitor/status')
export const scanNow = () => apiPost<ScanResult>('/monitor/scan')
