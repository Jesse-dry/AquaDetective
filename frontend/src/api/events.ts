import { apiGet, apiPost } from './client'
import type { PollutionEvent } from '../types'

// GET /events?status=
export const getEvents = (status?: string) =>
  apiGet<PollutionEvent[]>(`/events${status ? `?status=${status}` : ''}`, 'events.json')

// POST /events/{id}/investigate 触发溯源,返回 { id: investigation_id }
export const startInvestigation = (eventId: string) =>
  apiPost<{ id: string }>(`/events/${eventId}/investigate`)
