import { create } from 'zustand'
import type { PollutionEvent, SeriesPoint } from '../types'
import { getSeries } from '../api/series'

// 扩散回放:以事件首达时刻为中心开时间窗,拉取各断面真实时序,
// 时间游标推进时把"当前值/窗内峰值"作为热力值供地图着色。
// 前端零计算:数值原样来自 /series,热力仅做显示归一化。
const PRE_S = 6 * 3600 // 窗口:事件前 6h
const POST_S = 48 * 3600 // 窗口:事件后 48h

interface PlaybackState {
  active: boolean
  eventId: string | null
  indicator: string
  cursorMs: number
  t0Ms: number
  t1Ms: number
  playing: boolean
  speedS: number // 每个 tick(100ms)推进的模拟秒数
  series: Record<string, SeriesPoint[]>
  heat: Record<string, number> // stationId -> 0~1 热力(显示用)
  cursors: Record<string, number> // stationId -> 已消费的数据下标

  load: (ev: PollutionEvent, stationIds: string[]) => Promise<void>
  setPlaying: (playing: boolean) => void
  setSpeed: (speedS: number) => void
  tick: () => void
  close: () => void
}

const initial = {
  active: false,
  eventId: null as string | null,
  indicator: '',
  cursorMs: 0,
  t0Ms: 0,
  t1Ms: 0,
  playing: false,
  speedS: 900,
  series: {} as Record<string, SeriesPoint[]>,
  heat: {} as Record<string, number>,
  cursors: {} as Record<string, number>,
}

export const usePlaybackStore = create<PlaybackState>((set, get) => ({
  ...initial,

  load: async (ev, stationIds) => {
    const onsetS = ev.onset_ts / 1000
    const from = onsetS - PRE_S
    const to = onsetS + POST_S
    const indicator = ev.indicators[0]
    const entries = await Promise.all(
      stationIds.map(async (sid) => {
        try {
          const resp = await getSeries({ station: sid, indicator, from, to })
          return [sid, resp.data] as const
        } catch {
          return [sid, []] as const
        }
      }),
    )
    set({
      ...initial,
      active: true,
      eventId: ev.id,
      indicator,
      t0Ms: from,
      t1Ms: to,
      cursorMs: from,
      playing: true,
      series: Object.fromEntries(entries),
    })
  },

  setPlaying: (playing) => set({ playing }),
  setSpeed: (speedS) => set({ speedS }),

  tick: () => {
    const s = get()
    if (!s.playing || !s.active) return
    const cursorMs = s.cursorMs + s.speedS * 1000
    if (cursorMs >= s.t1Ms) {
      set({ playing: false, cursorMs: s.t1Ms })
      return
    }
    const heat: Record<string, number> = {}
    const cursors = { ...s.cursors }
    for (const [sid, points] of Object.entries(s.series)) {
      let idx = cursors[sid] ?? 0
      while (idx < points.length && points[idx].ts <= cursorMs) idx += 1
      cursors[sid] = idx
      const current = idx > 0 ? points[idx - 1].value : 0
      // 显示归一化:当前值 / 窗内峰值(纯渲染缩放,不改变数据)
      let peak = 0
      for (const p of points) if (p.value > peak) peak = p.value
      heat[sid] = peak > 0 ? Math.min(current / peak, 1) : 0
    }
    set({ cursorMs, heat, cursors })
  },

  close: () => set({ ...initial }),
}))
