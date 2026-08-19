import { useEffect, useState } from 'react'
import type { Recording } from '../types'
import { getRecordings, getRecording } from '../api/investigate'
import { useInvestigationStore } from '../store/investigationStore'
import { ReasoningPanel } from '../components/reasoning/ReasoningPanel'

// 回放页:历史调查按消息序重放到推理面板(答辩兜底/复盘)
export function ReplayPage() {
  const [recordings, setRecordings] = useState<Recording[]>([])
  const inv = useInvestigationStore()

  useEffect(() => {
    getRecordings().then(setRecordings).catch(() => {})
  }, [])

  const replay = async (id: string) => {
    const rec = await getRecording(id)
    inv.start(id)
    inv.setConnStatus('closed')
    rec.messages.forEach(inv.applyMessage)
  }

  return (
    <div className="grid h-screen grid-cols-[320px_1fr] bg-ink text-slate-200">
      <aside className="space-y-2 overflow-y-auto border-r border-edge p-4">
        <h1 className="text-lg font-bold">📼 调查回放</h1>
        {recordings.map((rec) => (
          <button
            key={rec.id}
            onClick={() => replay(rec.id)}
            className="block w-full rounded-lg border border-edge bg-panel p-3 text-left hover:border-accent"
          >
            <p className="text-sm font-semibold">{rec.id}</p>
            <p className="text-xs text-slate-400">
              事件 {rec.event_id} · {rec.status}
            </p>
            <p className="text-xs text-slate-500">
              {new Date(rec.started_at).toLocaleString('zh-CN')}
            </p>
          </button>
        ))}
      </aside>
      <main className="min-h-0">
        <ReasoningPanel />
      </main>
    </div>
  )
}
