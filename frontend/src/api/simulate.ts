import { apiPost } from './client'
import type { EventType, Severity } from '../types'

// POST /simulate/reset?seed= 一键重建世界
export const resetWorld = (seed?: number) =>
  apiPost<{ ok: boolean }>(`/simulate/reset${seed !== undefined ? `?seed=${seed}` : ''}`)

export interface InjectBody {
  etype: EventType
  source_id: string
  severity: Severity
}

// POST /simulate/inject 运行时注入污染事件(现场演示按钮)
export const injectEvent = (body: InjectBody) =>
  apiPost<{ ok: boolean; event_id: string; alert_station: string }>('/simulate/inject', body)
