import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRecordings, getRecording, deleteRecording } from '../api/investigate'
import { useInvestigationStore } from '../store/investigationStore'
import { ReasoningPanel } from '../components/reasoning/ReasoningPanel'
import type { RecordingSummary } from '../types'
import { eventLabel, stationLabel, indicatorLabel } from '../utils/labels'

// 回放页:历史调查按消息序重放到推理面板(答辩兜底/复盘)
// 列表展示事件摘要(事件名/断面/指标/时间),点卡片回放,右上角 ✕ 删除
export function ReplayPage() {
  const [recordings, setRecordings] = useState<RecordingSummary[]>([])
  const inv = useInvestigationStore()

  const refresh = () => {
    getRecordings().then((r) => setRecordings(r.recordings)).catch(() => {})
  }

  useEffect(refresh, [])

  const replay = async (id: string) => {
    const rec = await getRecording(id)
    inv.start(rec.investigation_id)
    inv.setConnStatus('closed')
    rec.stream.forEach(inv.applyMessage)
  }

  // 删除录音:确认后调接口,成功则从列表移除;若删的是当前正显示的调查,同时清空面板
  const remove = async (id: string) => {
    const label = recordings.find((r) => r.investigation_id === id)
    const name = label?.event_id ? eventLabel(label.event_id) : id
    if (!window.confirm(`确定删除「${name}」的回放记录吗?`)) return
    try {
      await deleteRecording(id)
      setRecordings((rs) => rs.filter((r) => r.investigation_id !== id))
      if (inv.investigationId === id) inv.reset()
    } catch {
      alert('删除失败,请稍后重试')
    }
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
          <div
            key={rec.investigation_id}
            className="relative rounded-lg border border-edge bg-panel p-3 hover:border-accent"
          >
            <button
              onClick={() => replay(rec.investigation_id)}
              className="block w-full text-left"
            >
              <p className="pr-6 text-sm font-semibold">
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
            <button
              onClick={() => remove(rec.investigation_id)}
              className="absolute right-2 top-2 rounded px-1 text-xs text-slate-500 hover:bg-danger/20 hover:text-danger"
              title="删除此回放"
            >
              ✕
            </button>
          </div>
        ))}
      </aside>
      <main className="min-h-0">
        <ReasoningPanel />
      </main>
    </div>
  )
}
