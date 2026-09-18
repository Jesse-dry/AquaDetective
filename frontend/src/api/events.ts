import { apiGet, apiPost } from './client'
import type { AffectedStation, PollutionEvent } from '../types'

// 后端原始事件行:indicators / affected_stations 可能是 JSON 字符串,
// onset_ts 为毫秒级 epoch
interface RawEvent extends Omit<PollutionEvent, 'indicators' | 'affected_stations'> {
  indicators: string | string[]
  affected_stations?: string | AffectedStation[] | null
}

function parseJsonArray<T>(raw: string | T[] | null | undefined): T[] | undefined {
  if (!raw) return undefined
  if (Array.isArray(raw)) return raw
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : undefined
  } catch {
    return undefined
  }
}

function normalize(ev: RawEvent): PollutionEvent {
  let indicators: string[] = []
  if (Array.isArray(ev.indicators)) {
    indicators = ev.indicators
  } else {
    try {
      indicators = JSON.parse(ev.indicators)
    } catch {
      indicators = [ev.indicators]
    }
  }
  return {
    ...ev,
    indicators,
    affected_stations: parseJsonArray<AffectedStation>(ev.affected_stations),
    onset_ts: ev.onset_ts,
  }
}

// GET /events?status=
export async function getEvents(status?: string): Promise<PollutionEvent[]> {
  const rows = await apiGet<RawEvent[]>(
    `/events${status ? `?status=${status}` : ''}`,
    'events.json',
  )
  return rows.map(normalize)
}

export interface InvestigateResp {
  investigation_id: string
  event_id: string
  status: string
}

// POST /events/{id}/investigate 触发溯源,返回 { investigation_id, ... }
export const startInvestigation = (eventId: string) =>
  apiPost<InvestigateResp>(`/events/${eventId}/investigate`)
