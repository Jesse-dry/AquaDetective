import { apiPost, apiDelete } from './client'
import type { EventType, Severity } from '../types'

// POST /simulate/reset?seed= 一键重建世界
export const resetWorld = (seed?: number) =>
  apiPost<{ ok: boolean }>(`/simulate/reset${seed !== undefined ? `?seed=${seed}` : ''}`)

export interface InjectBody {
  etype: Exclude<EventType, 'detected'>
  source_id: string
  severity: Severity
  // false = 静默注入:只写时序不建告警,交给监测 Agent 自己扫出来
  notify?: boolean
}

export interface InjectResp {
  ok: boolean
  event_id?: string // 静默注入时没有(事件由监测 Agent 生成)
  silent?: boolean
  alert_station: string
}

// POST /simulate/inject 运行时注入污染事件(现场演示按钮)
export const injectEvent = (body: InjectBody) =>
  apiPost<InjectResp>('/simulate/inject', body)

// DELETE /simulate/events/{id} 删除手动注入事件(仅 evt_inj_)
export const deleteInjectedEvent = (id: string) => apiDelete<{ ok: boolean; deleted: string }>(`/simulate/events/${id}`)
