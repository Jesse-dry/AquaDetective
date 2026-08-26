import { useEffect } from 'react'
import { useAlertStore } from '../../store/alertStore'
import { useInvestigationStore } from '../../store/investigationStore'
import { usePlaybackStore } from '../../store/playbackStore'
import { useWatershedStore } from '../../store/watershedStore'
import { startInvestigation } from '../../api/events'
import { getInvestigation } from '../../api/investigate'
import { IS_MOCK } from '../../api/client'
import { MockStream } from '../../ws/mockStream'
import { InvestigationConnection } from '../../ws/connection'
import type { Severity } from '../../types'
import { eventLabel, stationLabel, indicatorLabel, etypeLabel, SEVERITY_LABEL } from '../../utils/labels'

// 告警面板:新事件闪烁,点击触发调查(Mock 模式回放 mock 推理流)
const SEVERITY_STYLE: Record<Severity, string> = {
  high: 'border-danger/60 bg-danger/10',
  medium: 'border-warn/60 bg-warn/10',
  low: 'border-edge bg-panel',
}

let activeConn: InvestigationConnection | MockStream | null = null

export function AlertList() {
  const { events, refresh } = useAlertStore()
  const inv = useInvestigationStore()
  const loadPlayback = usePlaybackStore((s) => s.load)
  const stationIds = useWatershedStore((s) => s.data?.stations.map((st) => st.id) ?? [])

  // 按事件序号正序展示(事件1 在前),后端默认按发生时间倒序
  const sortedEvents = [...events].sort((a, b) => {
    const na = Number(a.id.match(/(\d+)/)?.[1] ?? 0)
    const nb = Number(b.id.match(/(\d+)/)?.[1] ?? 0)
    return na - nb
  })

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 30_000)
    return () => clearInterval(timer)
  }, [refresh])

  const investigate = async (eventId: string) => {
    ;(activeConn as { close?: () => void; stop?: () => void } | null)?.close?.()
    ;(activeConn as { stop?: () => void } | null)?.stop?.()

    if (IS_MOCK) {
      inv.start('mock_inv_001')
      inv.setConnStatus('open')
      const stream = new MockStream()
      activeConn = stream
      stream.start({ onMessage: inv.applyMessage })
      return
    }
    const { investigation_id } = await startInvestigation(eventId)
    inv.start(investigation_id)
    const conn = new InvestigationConnection(investigation_id, {
      onMessage: inv.applyMessage,
      onStatus: inv.setConnStatus,
      // 重连成功后用 REST 补齐全量 stream(step_id 去重保证不重复)
      onReconnect: () => {
        getInvestigation(investigation_id)
          .then((full) => full.stream?.forEach(inv.applyMessage))
          .catch(() => {})
      },
    })
    activeConn = conn
    conn.connect()
  }

  return (
    <div className="flex h-full flex-col gap-2 overflow-y-auto p-3">
      <h2 className="text-sm font-semibold text-slate-200">🚨 告警事件</h2>
      {sortedEvents.length === 0 && (
        <p className="py-6 text-center text-sm text-slate-500">暂无事件</p>
      )}
      {sortedEvents.map((ev) => (
        <div
          key={ev.id}
          className={`rounded-lg border p-3 ${SEVERITY_STYLE[ev.severity]} ${
            ev.status === 'open' ? 'animate-pulse' : ''
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-100">{eventLabel(ev.id)}</span>
            <span className="text-xs text-slate-400">
              {etypeLabel(ev.etype)} · {SEVERITY_LABEL[ev.severity] ?? ev.severity}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            {stationLabel(ev.station_id)} · {ev.indicators.map(indicatorLabel).join('/')}
          </p>
          <p className="text-xs text-slate-500">
            {new Date(ev.onset_ts).toLocaleString('zh-CN')}
          </p>
          {ev.status === 'open' && (
            <button
              onClick={() => investigate(ev.id)}
              className="mt-2 w-full rounded bg-danger px-2 py-1 text-xs font-semibold text-white hover:bg-red-400"
            >
              🔍 开始侦查
            </button>
          )}
          <button
            onClick={() => loadPlayback(ev, stationIds)}
            disabled={stationIds.length === 0}
            className="mt-1.5 w-full rounded bg-edge px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          >
            ▶ 扩散回放
          </button>
          {ev.status === 'investigating' && (
            <p className="mt-2 text-center text-xs text-warn">侦查中…</p>
          )}
        </div>
      ))}
    </div>
  )
}
