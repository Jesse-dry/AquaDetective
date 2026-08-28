import { apiGet } from './client'
import type { SeriesResponse } from '../types'

export interface SeriesQuery {
  station: string
  indicator: string
  from?: number // API 毫秒级 epoch
  to?: number // API 毫秒级 epoch
  step?: number // 降采样,大图默认带上
}

// GET /series?station=&indicator=&from=&to=
// 后端返回 { station, indicator, count, data:[{ts(毫秒 epoch), value}] }(API 契约:毫秒级)
export function getSeries(q: SeriesQuery) {
  const params = new URLSearchParams()
  params.set('station', q.station)
  params.set('indicator', q.indicator)
  if (q.from !== undefined) params.set('from', String(q.from))
  if (q.to !== undefined) params.set('to', String(q.to))
  if (q.step !== undefined) params.set('step', String(q.step))
  return apiGet<SeriesResponse>(`/series?${params.toString()}`, 'series.json')
}
