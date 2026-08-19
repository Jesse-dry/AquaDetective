import { apiGet } from './client'
import type { Investigation, Recording, WsMessage } from '../types'

// GET /investigations/{id} 调查状态与推理记录(WS 断线重连后补齐用)
export const getInvestigation = (id: string) =>
  apiGet<Investigation>(`/investigations/${id}`, 'investigation.json')

// GET /recordings / /recordings/{id} 历史调查回放
export const getRecordings = () => apiGet<Recording[]>('/recordings', 'recordings.json')

export const getRecording = (id: string) =>
  apiGet<{ id: string; messages: WsMessage[] }>(`/recordings/${id}`, 'recording.json')
