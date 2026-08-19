import { create } from 'zustand'
import type { Watershed } from '../types'
import { getWatershed } from '../api/watershed'

// 流域拓扑:会话级缓存,进大屏拉一次
interface WatershedState {
  data: Watershed | null
  loading: boolean
  error: string | null
  load: () => Promise<void>
}

export const useWatershedStore = create<WatershedState>((set, get) => ({
  data: null,
  loading: false,
  error: null,
  load: async () => {
    if (get().data || get().loading) return
    set({ loading: true, error: null })
    try {
      const data = await getWatershed()
      set({ data, loading: false })
    } catch (e) {
      set({ loading: false, error: String(e) })
    }
  },
}))
