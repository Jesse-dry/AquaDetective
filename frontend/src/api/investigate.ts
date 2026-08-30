import { apiGet, apiDelete } from './client'
import type { Investigation, RecordingList, WsMessage } from '../types'

// GET /investigations/{id} 调查状态 + conclusion + 完整 stream(WS 断线重连后补齐用)
export const getInvestigation = (id: string) =>
  apiGet<Investigation>(`/investigations/${id}`, 'investigation.json')

// GET /recordings 返回 { recordings: [调查摘要...] }
export const getRecordings = () => apiGet<RecordingList>('/recordings', 'recordings.json')

// GET /recordings/{id} 返回 { investigation_id, stream: [消息...] }
export const getRecording = (id: string) =>
  apiGet<{ investigation_id: string; stream: WsMessage[] }>(
    `/recordings/${id}`,
    'recording.json',
  )

// DELETE /recordings/{id} 删除一条历史录音(404 = 已不存在)
export const deleteRecording = (id: string) => apiDelete(`/recordings/${id}`)
