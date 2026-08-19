import { apiPost } from './client'
import type { EventType, Severity } from '../types'

// POST /simulate/reset?seed= 一键重建世界
export const resetWorld = (seed?: number) =>
  apiPost<{ ok: boolean }>(`/simulate/reset${seed !== undefined ? `?seed=${seed}` : ''}`)

export interface InjectBody {
  etype: EventType
  source_enterprise: string
  severity: Severity
  at?: number // 毫秒 epoch,缺省为当前模拟时间
}

// POST /simulate/inject 运行时注入污染事件(现场演示按钮)
export const injectEvent = (body: InjectBody) =>
  apiPost<{ id: string }>('/simulate/inject', body)
