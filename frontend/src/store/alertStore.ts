import { create } from 'zustand'
import type { PollutionEvent } from '../types'
import { getEvents } from '../api/events'

// 告警面板:事件列表,30s 轮询 + 调查后刷新
interface AlertState {
  events: PollutionEvent[]
  loading: boolean
  refresh: () => Promise<void>
}

export const useAlertStore = create<AlertState>((set) => ({
  events: [],
  loading: false,
  refresh: async () => {
    set({ loading: true })
    try {
      const events = await getEvents()
      set({ events, loading: false })
    } catch {
      set({ loading: false })
    }
  },
}))
