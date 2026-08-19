import { apiGet } from './client'
import type { SeriesPoint } from '../types'

export interface SeriesQuery {
  station: string
  indicator: string
  from?: number
  to?: number
  step?: number // 降采样,大图默认带上
}

// GET /series?station=&indicator=&from=&to=
export function getSeries(q: SeriesQuery) {
  const params = new URLSearchParams()
  params.set('station', q.station)
  params.set('indicator', q.indicator)
  if (q.from !== undefined) params.set('from', String(q.from))
  if (q.to !== undefined) params.set('to', String(q.to))
  if (q.step !== undefined) params.set('step', String(q.step))
  return apiGet<SeriesPoint[]>(`/series?${params.toString()}`, 'series.json')
}
