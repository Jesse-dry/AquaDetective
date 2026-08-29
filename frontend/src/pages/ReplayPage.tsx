import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRecordings, getRecording } from '../api/investigate'
import { useInvestigationStore } from '../store/investigationStore'
import { ReasoningPanel } from '../components/reasoning/ReasoningPanel'
import type { RecordingSummary } from '../types'
import { eventLabel, stationLabel, indicatorLabel } from '../utils/labels'

// 回放页:历史调查按消息序重放到推理面板(答辩兜底/复盘)
// 列表展示事件摘要(事件名/断面/指标/时间),点开后拉完整 stream
export function ReplayPage() {
  const [recordings, setRecordings] = useState<RecordingSummary[]>([])
  const inv = useInvestigationStore()

  useEffect(() => {
    getRecordings().then((r) => setRecordings(r.recordings)).catch(() => {})
  }, [])

  const replay = async (id: string) => {
    const rec = await getRecording(id)
    inv.start(rec.investigation_id)
    inv.setConnStatus('closed')
    rec.stream.forEach(inv.applyMessage)
  }

  return (
    <div className="grid h-screen grid-cols-[320px_1fr] bg-ink text-slate-200">
      <aside className="space-y-2 overflow-y-auto border-r border-edge p-4">
        <Link to="/" className="inline-block rounded bg-edge px-3 py-1 text-xs text-slate-300 hover:bg-slate-600">
          ← 返回大屏
        </Link>
        <h1 className="text-lg font-bold">📼 调查回放</h1>
        {recordings.length === 0 && (
          <p className="text-sm text-slate-500">暂无历史调查记录</p>
        )}
        {recordings.map((rec) => (
          <button
            key={rec.investigation_id}
            onClick={() => replay(rec.investigation_id)}
            className="block w-full rounded-lg border border-edge bg-panel p-3 text-left hover:border-accent"
          >
            <p className="text-sm font-semibold">
              {rec.event_id ? eventLabel(rec.event_id) : rec.investigation_id}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">
              {rec.station_id ? stationLabel(rec.station_id) : ''}
              {rec.indicators?.length ? ` · ${rec.indicators.map(indicatorLabel).join('/')}` : ''}
            </p>
            {rec.started_at && (
              <p className="text-xs text-slate-500">
                {new Date(rec.started_at).toLocaleString('zh-CN')}
              </p>
            )}
          </button>
        ))}
      </aside>
      <main className="min-h-0">
        <ReasoningPanel />
      </main>
    </div>
  )
}
