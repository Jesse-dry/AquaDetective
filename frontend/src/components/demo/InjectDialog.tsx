import { useState } from 'react'
import { injectEvent } from '../../api/simulate'
import { useWatershedStore } from '../../store/watershedStore'
import { useAlertStore } from '../../store/alertStore'
import type { EventType, Severity } from '../../types'

// 手动注入事件表单:POST /simulate/inject(现场演示"不是录屏"的保险)
export function InjectDialog({ onClose }: { onClose: () => void }) {
  const enterprises = useWatershedStore((s) => s.data?.enterprises ?? [])
  const refresh = useAlertStore((s) => s.refresh)
  const [etype, setEtype] = useState<EventType>('sudden')
  const [source, setSource] = useState('')
  const [severity, setSeverity] = useState<Severity>('medium')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!source) return
    setBusy(true)
    try {
      await injectEvent({ etype, source_id: source, severity })
      await refresh()
      onClose()
    } catch (e) {
      alert(`注入失败:${e instanceof Error ? e.message : e}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-80 space-y-3 rounded-lg border border-edge bg-panel p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-slate-100">💉 手动注入污染事件</h3>
        <label className="block text-xs text-slate-400">
          事件类型
          <select
            value={etype}
            onChange={(e) => setEtype(e.target.value as EventType)}
            className="mt-1 w-full rounded border border-edge bg-ink px-2 py-1 text-sm text-slate-200"
          >
            <option value="sudden">突发泄漏</option>
            <option value="periodic">夜间偷排</option>
            <option value="gradual">渐变恶化</option>
          </select>
        </label>
        <label className="block text-xs text-slate-400">
          污染源企业
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="mt-1 w-full rounded border border-edge bg-ink px-2 py-1 text-sm text-slate-200"
          >
            <option value="">请选择…</option>
            {enterprises.map((ent) => (
              <option key={ent.id} value={ent.id}>
                {ent.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs text-slate-400">
          严重程度
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value as Severity)}
            className="mt-1 w-full rounded border border-edge bg-ink px-2 py-1 text-sm text-slate-200"
          >
            <option value="low">轻微</option>
            <option value="medium">中等</option>
            <option value="high">严重</option>
          </select>
        </label>
        <div className="flex gap-2 pt-1">
          <button
            onClick={submit}
            disabled={busy || !source}
            className="flex-1 rounded bg-danger px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-400 disabled:opacity-50"
          >
            {busy ? '注入中…' : '注入'}
          </button>
          <button
            onClick={onClose}
            className="rounded bg-edge px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  )
}
