import { useEffect } from 'react'
import { usePlaybackStore } from '../../store/playbackStore'
import { eventLabel, indicatorLabel } from '../../utils/labels'

// 扩散回放控制条:悬浮在地图左上角;播放时以 100ms tick 推进时间游标,
// 各断面热力值写入 playbackStore,由 WatershedMap 消费着色。
export function DispersionLayer() {
  const pb = usePlaybackStore()

  useEffect(() => {
    if (!pb.playing) return
    const timer = setInterval(() => pb.tick(), 100)
    return () => clearInterval(timer)
  }, [pb.playing, pb.tick])

  if (!pb.active) return null

  const progress = (pb.cursorMs - pb.t0Ms) / Math.max(pb.t1Ms - pb.t0Ms, 1)

  return (
    <div className="absolute left-3 top-3 z-10 w-80 rounded-lg border border-edge bg-panel/95 p-3 shadow-lg">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-200">
          🌊 扩散回放 · {pb.eventId ? eventLabel(pb.eventId) : ''} · {indicatorLabel(pb.indicator)}
        </span>
        <button onClick={pb.close} className="text-xs text-slate-500 hover:text-slate-300">✕</button>
      </div>
      <p className="mb-2 text-xs tabular-nums text-accent">
        {new Date(pb.cursorMs).toLocaleString('zh-CN')}
      </p>
      <div className="mb-2 h-1.5 overflow-hidden rounded bg-edge/60">
        <div className="h-full bg-accent transition-none" style={{ width: `${progress * 100}%` }} />
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => {
            // 已播到终点时,重新点播放 = 从头重放(否则 cursor 卡在 t1,tick 一步就又结束)
            if (!pb.playing && pb.cursorMs >= pb.t1Ms) pb.replay()
            else pb.setPlaying(!pb.playing)
          }}
          className="rounded bg-accent px-3 py-1 text-xs font-semibold text-ink hover:bg-sky-300 whitespace-nowrap"
        >
          {pb.playing ? '⏸暂停' : (pb.cursorMs >= pb.t1Ms ? '↻重放' : '▶播放')}
        </button>
        <select
          value={pb.speedMs}
          onChange={(e) => pb.setSpeed(Number(e.target.value))}
          className="rounded border border-edge bg-ink px-1.5 py-1 text-xs text-slate-200"
        >
          <option value={300 * 1000}>慢速 5min/步</option>
          <option value={900 * 1000}>中速 15min/步</option>
          <option value={3600 * 1000}>快速 1h/步</option>
        </select>
        <span className="text-xs text-slate-500">断面颜色 = 浓度热力</span>
      </div>
    </div>
  )
}
