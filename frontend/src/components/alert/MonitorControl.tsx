import { useCallback, useEffect, useRef, useState } from 'react'
import { IS_MOCK } from '../../api/client'
import { getMonitorStatus, scanNow, type MonitorStatus } from '../../api/monitor'
import { useAlertStore } from '../../store/alertStore'

export function MonitorControl() {
  const [status, setStatus] = useState<MonitorStatus | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const mounted = useRef(false)
  const refresh = useAlertStore((s) => s.refresh)
  const sync = useCallback(async () => {
    try {
      const next = await getMonitorStatus()
      if (mounted.current) {
        setStatus(next)
        setError(null)
      }
    } catch {
      if (mounted.current) setError('监测服务暂不可用')
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    if (!IS_MOCK) void sync()
    const timer = IS_MOCK ? undefined : setInterval(sync, 5000)
    return () => {
      mounted.current = false
      clearInterval(timer)
    }
  }, [sync])

  const run = async () => {
    setPending(true)
    setError(null)
    try {
      await scanNow()
      await refresh()
      await sync()
    } catch {
      if (mounted.current) setError('扫描请求未完成，请查看最新扫描状态')
      // A timed-out HTTP request may still finish on the server.
    } finally {
      if (mounted.current) setPending(false)
    }
  }

  const busy = pending || status?.running
  const result = status?.last_result
  return (
    <section className="shrink-0 border-b border-edge pb-3" aria-label="水质监测">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-slate-400">
          {IS_MOCK ? '演示数据' : status?.enabled ? `自动监测 · ${status.interval_s} 秒` : '手动监测'}
        </span>
        <button
          type="button"
          onClick={run}
          disabled={IS_MOCK || busy || !status}
          className="rounded bg-accent px-3 py-1 text-xs font-semibold text-ink disabled:opacity-50"
        >
          {busy ? '扫描中…' : '立即扫描'}
        </button>
      </div>
      <div className="mt-2 space-y-1 break-words text-xs text-slate-400" aria-live="polite">
        {!IS_MOCK && !status && !error && <p>连接监测服务中…</p>}
        {status && <p>{status.method.toUpperCase()} · 最近 {status.window_h} 小时</p>}
        {status?.last_finished_at && (
          <p>最近扫描：{new Date(status.last_finished_at).toLocaleString('zh-CN')}</p>
        )}
        {!status?.last_error && result && <>
          <p className="text-slate-200">新增 {result.created_count} 条告警 · 已检测 {result.scanned_series} 条序列</p>
          {result.unchanged_series > 0 && <p>{result.unchanged_series} 条序列无新增观测</p>}
          {result.insufficient_series > 0 && <p className="text-warn">{result.insufficient_series} 条序列样本不足</p>}
          {result.extended_series > 0 && <p>{result.extended_series} 条序列已扩展历史窗口</p>}
          {result.latest_data_ts && <p>最新观测：{new Date(result.latest_data_ts).toLocaleString('zh-CN')}</p>}
        </>}
        {(error || status?.last_error) && <p role="alert" className="text-danger">{error || '最近扫描失败，请重试'}</p>}
      </div>
    </section>
  )
}
