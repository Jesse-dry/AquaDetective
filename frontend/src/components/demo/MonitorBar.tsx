import { useCallback, useEffect, useRef, useState } from 'react'
import { configureMonitor, getMonitorStatus, scanNow } from '../../api/monitor'
import type { MonitorStatus } from '../../api/monitor'
import { useAlertStore } from '../../store/alertStore'
import { eventLabel, indicatorLabel, stationLabel } from '../../utils/labels'

// 监测 Agent 状态条:展示后台定时扫描的存活/节奏/检出,并可手动触发或暂停
const POLL_MS = 5000

function fmtClock(ms: number | null): string {
  if (!ms) return '—'
  return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false })
}

function fmtCountdown(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  if (s < 60) return `${s} 秒`
  return `${Math.floor(s / 60)} 分 ${String(s % 60).padStart(2, '0')} 秒`
}

export function MonitorBar() {
  const [status, setStatus] = useState<MonitorStatus | null>(null)
  const [offline, setOffline] = useState(false)
  const [busy, setBusy] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const refreshAlerts = useAlertStore((s) => s.refresh)
  // 已刷新过的事件总数,用于判断本轮是否检出了新事件
  const seenTotal = useRef<number | null>(null)

  const poll = useCallback(async () => {
    try {
      const s = await getMonitorStatus()
      setStatus(s)
      setOffline(false)
      if (seenTotal.current !== null && s.total_created > seenTotal.current) {
        await refreshAlerts()
      }
      seenTotal.current = s.total_created
    } catch {
      setOffline(true)
    }
  }, [refreshAlerts])

  useEffect(() => {
    poll()
    const id = setInterval(poll, POLL_MS)
    return () => clearInterval(id)
  }, [poll])

  // 本地秒针:只为倒计时走动,不触发请求
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const onScanNow = async () => {
    setBusy(true)
    try {
      await scanNow()
      await poll()
      await refreshAlerts()
    } finally {
      setBusy(false)
    }
  }

  const onToggle = async () => {
    if (!status) return
    setBusy(true)
    try {
      const s = await configureMonitor({ enabled: !status.enabled })
      setStatus(s)
    } finally {
      setBusy(false)
    }
  }

  if (offline && !status) {
    return (
      <div className="flex items-center gap-2 border-b border-edge bg-panel/40 px-4 py-1 text-[11px] text-slate-500">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-slate-600" />
        <span>监测 Agent · 未连接(后端未启动)</span>
      </div>
    )
  }

  const live = status?.enabled && status?.running
  const dot = offline
    ? 'bg-slate-600'
    : live
      ? 'bg-emerald-400 animate-pulse'
      : 'bg-slate-500'

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-edge bg-panel/40 px-4 py-1 text-[11px] text-slate-400">
      <span className="flex items-center gap-1.5">
        <span className={`inline-block h-1.5 w-1.5 rounded-full ${dot}`} />
        <span className="font-semibold text-slate-300">监测 Agent</span>
        <span className={live ? 'text-emerald-400' : 'text-slate-500'}>
          {offline ? '连接中断' : live ? '自动巡检中' : '已暂停'}
        </span>
      </span>

      {status && (
        <>
          <span>
            扫描间隔 <span className="text-slate-300">{Math.round(status.interval_s / 60)} 分钟</span>
            · 窗口 <span className="text-slate-300">{status.window_h}h</span>
          </span>
          <span>
            上次扫描 <span className="text-slate-300">{fmtClock(status.last_scan_ms)}</span>
            {status.last_duration_ms !== null && (
              <span className="text-slate-500"> ({(status.last_duration_ms / 1000).toFixed(1)}s)</span>
            )}
            · 检出 <span className="text-slate-300">{status.last_created}</span> 起
          </span>
          <span>
            {status.enabled && status.next_scan_ms
              ? <>下次扫描 <span className="text-accent">{fmtCountdown(status.next_scan_ms - now)}</span> 后</>
              : <span className="text-slate-500">定时扫描已暂停</span>}
          </span>
          <span>
            累计扫描 <span className="text-slate-300">{status.scan_count}</span> 次
            · 生成事件 <span className="text-slate-300">{status.total_created}</span> 起
          </span>

          {status.recent.length > 0 && (
            <span className="flex items-center gap-1">
              <span>最近检出:</span>
              {status.recent.slice(0, 4).map((h) => (
                <span
                  key={h.id}
                  title={`${eventLabel(h.id)} · ${stationLabel(h.station_id)} ${indicatorLabel(h.indicator)}`}
                  className={`rounded border px-1.5 py-0.5 ${
                    h.severity === 'high'
                      ? 'border-rose-500/40 bg-rose-500/10 text-rose-300'
                      : 'border-warn/40 bg-warn/10 text-warn'
                  }`}
                >
                  {stationLabel(h.station_id)}·{indicatorLabel(h.indicator)}
                </span>
              ))}
            </span>
          )}

          {status.last_error && (
            <span className="text-rose-400" title={status.last_error}>扫描异常</span>
          )}
        </>
      )}

      <span className="ml-auto flex items-center gap-2">
        <button
          onClick={onScanNow}
          disabled={busy}
          className="rounded bg-edge px-2 py-0.5 text-slate-200 hover:bg-slate-600 disabled:opacity-50"
        >
          {busy ? '扫描中…' : '📡 立即扫描'}
        </button>
        <button
          onClick={onToggle}
          disabled={busy || !status}
          className="rounded bg-edge px-2 py-0.5 text-slate-200 hover:bg-slate-600 disabled:opacity-50"
        >
          {status?.enabled ? '⏸ 暂停巡检' : '▶ 启动巡检'}
        </button>
      </span>
    </div>
  )
}
