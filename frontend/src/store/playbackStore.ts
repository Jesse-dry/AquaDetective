import { create } from 'zustand'
import type { PollutionEvent, SeriesPoint } from '../types'
import { getSeries } from '../api/series'

// 扩散回放:以事件首达时刻为中心开时间窗,拉取各断面真实时序,
// 时间游标推进时把"当前值/窗内峰值"作为热力值供地图着色。
// 前端零计算:数值原样来自 /series,热力仅做显示归一化。
// 单位契约:后端 API 返回毫秒级 epoch(onset_ts、series.ts 均毫秒),
// 本 store 全程毫秒,直接 new Date(ms) 格式化。
const PRE_MS = 6 * 3600 * 1000 // 窗口:事件前 6h
const POST_MS = 48 * 3600 * 1000 // 窗口:事件后 48h

interface PlaybackState {
  active: boolean
  eventId: string | null
  indicator: string
  cursorMs: number
  t0Ms: number
  t1Ms: number
  startMs: number // 播放起点(事件发生时刻,跳过前置基线段)
  playing: boolean
  speedMs: number // 每个 tick(100ms)推进的模拟毫秒数
  series: Record<string, SeriesPoint[]>
  globalPeak: number // 全断面全局峰值(统一归一化,体现扩散浓度差)
  heat: Record<string, number> // stationId -> 0~1 热力(显示用)
  cursors: Record<string, number> // stationId -> 已消费的数据下标

  load: (ev: PollutionEvent, stationIds: string[]) => Promise<void>
  setPlaying: (playing: boolean) => void
  setSpeed: (speedMs: number) => void
  replay: () => void
  skipToEnd: () => void
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
  startMs: 0,
  playing: false,
  speedMs: 900 * 1000,
  series: {} as Record<string, SeriesPoint[]>,
  globalPeak: 0,
  heat: {} as Record<string, number>,
  cursors: {} as Record<string, number>,
}

export const usePlaybackStore = create<PlaybackState>((set, get) => ({
  ...initial,

  load: async (ev, stationIds) => {
    // onset_ts 为毫秒(API 契约),from/to 用毫秒传给 /series
    const from = ev.onset_ts - PRE_MS
    const to = ev.onset_ts + POST_MS
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
    // 全局峰值:所有断面全窗最大值,统一归一化以体现"上游高、下游低"的扩散浓度差
    const seriesMap = Object.fromEntries(entries) as Record<string, SeriesPoint[]>
    let globalPeak = 0
    for (const pts of Object.values(seriesMap)) {
      for (const p of pts) if (p.value > globalPeak) globalPeak = p.value
    }
    // 保留用户调好的播放速度;从窗口起点开始播(完整基线 → 事件 → 扩散),
    // 用户可用进度条/暂停自行跳过基线段
    const { speedMs } = get()
    set({
      ...initial,
      active: true,
      eventId: ev.id,
      indicator,
      t0Ms: from,
      t1Ms: to,
      startMs: from,
      cursorMs: from,
      playing: true,
      speedMs,
      series: seriesMap,
      globalPeak,
    })
  },

  setPlaying: (playing) => set({ playing }),
  setSpeed: (speedMs) => set({ speedMs }),
  // 从头重放:游标回到事件发生时刻(startMs),热力和消费下标复位
  replay: () => set({ playing: true, cursorMs: get().startMs, heat: {}, cursors: {} }),
  // 跳到终点:游标定格末尾,热力取各断面最终值(供"跳过动画"一键结束回放)
  skipToEnd: () => {
    const s = get()
    if (!s.active) return
    const heat: Record<string, number> = {}
    const peak = s.globalPeak || 1
    for (const [sid, points] of Object.entries(s.series)) {
      const current = points.length ? points[points.length - 1].value : 0
      heat[sid] = Math.min(current / peak, 1)
    }
    set({ playing: false, cursorMs: s.t1Ms, heat })
  },

  tick: () => {
    const s = get()
    if (!s.playing || !s.active) return
    // cursorMs 与 points.ts 均为毫秒,单位一致才能正确推进
    const cursorMs = s.cursorMs + s.speedMs
    if (cursorMs >= s.t1Ms) {
      set({ playing: false, cursorMs: s.t1Ms })
      return
    }
    const heat: Record<string, number> = {}
    const cursors = { ...s.cursors }
    // 全局峰值归一化:上游浓度高先变红,下游随扩散到达逐渐变色,体现时空扩散关系
    const peak = s.globalPeak || 1
    for (const [sid, points] of Object.entries(s.series)) {
      let idx = cursors[sid] ?? 0
      while (idx < points.length && points[idx].ts <= cursorMs) idx += 1
      cursors[sid] = idx
      const current = idx > 0 ? points[idx - 1].value : 0
      heat[sid] = Math.min(current / peak, 1)
    }
    set({ cursorMs, heat, cursors })
  },

  close: () => set({ ...initial }),
}))
