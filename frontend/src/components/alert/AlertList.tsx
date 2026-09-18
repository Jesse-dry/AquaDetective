import { useEffect } from 'react'
import { useAlertStore } from '../../store/alertStore'
import { useInvestigationStore } from '../../store/investigationStore'
import { usePlaybackStore } from '../../store/playbackStore'
import { useUiStore } from '../../store/uiStore'
import { useWatershedStore } from '../../store/watershedStore'
import { startInvestigation } from '../../api/events'
import { getInvestigation } from '../../api/investigate'
import { deleteInjectedEvent } from '../../api/simulate'
import { IS_MOCK } from '../../api/client'
import { MockStream } from '../../ws/mockStream'
import { InvestigationConnection } from '../../ws/connection'
import { Popconfirm } from '../ui/Popconfirm'
import { MonitorControl } from './MonitorControl'
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
  const setIndicator = useUiStore((s) => s.setIndicator)
  const selectStation = useUiStore((s) => s.selectStation)
  const stationIds = useWatershedStore((s) => s.data?.stations.map((st) => st.id) ?? [])
  const removeInjected = async (id: string) => {
    try {
      await deleteInjectedEvent(id)
      await refresh()
    } catch {
      alert('删除失败，请稍后重试')
    }
  }

  // 排序:预置事件(evt_00N)在前按序号,注入事件(evt_inj_00N)在后按序号
  const sortKey = (id: string) => {
    const inj = id.match(/^evt_inj_0*(\d+)$/i)
    if (inj) return [1, Number(inj[1])] as const // 注入类,第二序
    const m = id.match(/^evt_?0*(\d+)$/i)
    if (m) return [0, Number(m[1])] as const // 预置类,第一序
    return [2, 0] as const // 其余垫底
  }
  const sortedEvents = [...events].sort((a, b) => {
    const [ta, na] = sortKey(a.id)
    const [tb, nb] = sortKey(b.id)
    return ta !== tb ? ta - tb : na - nb
  })

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 30_000)
    return () => clearInterval(timer)
  }, [refresh])

  // 调查结束(收到 report_ready/conclusion/failed)后主动关闭 WS,避免后端关连接触发无效重连
  // 无效重连会反复补齐 stream,导致 talks 重复跳出(已加去重,但切断根源更干净)
  const reportId = useInvestigationStore((s) => s.reportId)
  const conclusion = useInvestigationStore((s) => s.conclusion)
  const failed = useInvestigationStore((s) => s.failed)
  useEffect(() => {
    if (reportId || conclusion || failed) {
      ;(activeConn as { close?: () => void } | null)?.close?.()
      // 调查结束后立刻刷新事件状态(resolved/open),不等 30s 轮询
      refresh()
    }
  }, [reportId, conclusion, failed, refresh])

  const investigate = async (eventId: string) => {
    ;(activeConn as { close?: () => void; stop?: () => void } | null)?.close?.()
    ;(activeConn as { stop?: () => void } | null)?.stop?.()
    // 本地即时置为 investigating,不等 30s 轮询(按钮立刻切换状态)
    useAlertStore.setState((s) => ({
      events: s.events.map((e) => (e.id === eventId ? { ...e, status: 'investigating' } : e)),
    }))

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
      <MonitorControl />
      {sortedEvents.length === 0 && (
        <p className="py-6 text-center text-sm text-slate-500">暂无事件</p>
      )}
      {sortedEvents.map((ev) => (
        <div
          key={ev.id}
          className={`relative rounded-lg border p-3 ${SEVERITY_STYLE[ev.severity]} ${
            ev.status === 'open' ? 'animate-pulse' : ''
          }`}
        >
          {ev.id.startsWith('evt_inj_') && (
            <div className="absolute right-2 top-2">
              <Popconfirm
                message="删除该注入事件？删除后不可恢复。"
                onConfirm={() => removeInjected(ev.id)}
              >
                <button
                  className="rounded px-1 text-xs text-slate-500 hover:bg-danger/20 hover:text-danger"
                  title="删除此注入事件"
                >
                  ✕
                </button>
              </Popconfirm>
            </div>
          )}
          <div className="flex items-center justify-between gap-2 pr-5">
            {/* 标题不换行(否则窄栏里"事件1"会被拆成两行),右侧类型/严重度可折行 */}
            <span className="shrink-0 whitespace-nowrap text-sm font-semibold text-slate-100">
              {ev.etype === 'detected' ? '监测告警' : eventLabel(ev.id)}
            </span>
            <span className="text-right text-xs text-slate-400">
              {etypeLabel(ev.etype)} · {SEVERITY_LABEL[ev.severity] ?? ev.severity}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            {stationLabel(ev.station_id)} · {ev.indicators.map(indicatorLabel).join('/')}
          </p>
          <p className="text-xs text-slate-500">
            {new Date(ev.onset_ts).toLocaleString('zh-CN')}
          </p>
          <button
            onClick={() => investigate(ev.id)}
            disabled={ev.status !== 'open'}
            className={`mt-2 w-full rounded px-2 py-1 text-xs font-semibold disabled:cursor-not-allowed ${
              ev.status === 'open'
                ? 'bg-danger text-white hover:bg-red-400'
                : ev.status === 'investigating'
                  ? 'bg-warn/30 text-warn'
                  : 'bg-edge/40 text-slate-500'
            }`}
          >
            {ev.status === 'open' ? '🔍 开始侦查'
              : ev.status === 'investigating' ? '⏳ 侦查中…'
              : '✓ 已侦查'}
          </button>
          <button
            onClick={() => {
              // 回放开始:选中断面切到事件预警断面、指标切到事件首达指标,
              // 底部曲线才能立刻显示"该断面在该事件窗口内"的时序
              selectStation(ev.station_id)
              setIndicator(ev.indicators[0] ?? 'cod')
              loadPlayback(ev, stationIds)
            }}
            disabled={stationIds.length === 0}
            className="mt-1.5 w-full rounded bg-edge px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-50"
          >
            ▶ 扩散回放
          </button>
        </div>
      ))}
    </div>
  )
}
