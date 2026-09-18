import { useEffect, useRef, useState } from 'react'
import { injectEvent } from '../../api/simulate'
import { useWatershedStore } from '../../store/watershedStore'
import { useAlertStore } from '../../store/alertStore'
import type { EventType, Severity } from '../../types'

// 手动注入事件表单:POST /simulate/inject(现场演示"不是录屏"的保险)
export function InjectDialog({ onClose }: { onClose: () => void }) {
  const enterprises = useWatershedStore((s) => s.data?.enterprises ?? [])
  const refresh = useAlertStore((s) => s.refresh)
  const [etype, setEtype] = useState<Exclude<EventType, 'detected'>>('sudden')
  const [source, setSource] = useState('')
  const [severity, setSeverity] = useState<Severity>('medium')
  const [silent, setSilent] = useState(false)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!source) return
    setBusy(true)
    try {
      await injectEvent({ etype, source_id: source, severity, notify: !silent })
      await refresh()
      onClose()
    } catch (e) {
      alert(`注入失败：${e instanceof Error ? e.message : e}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      {/* 宽度用 w-full + max-w:窗口窄于 320px 时收窄而不是横向溢出;
          max-h + overflow:窗口再矮也不会把弹窗顶出可视区 */}
      <div
        className="max-h-[90vh] w-full max-w-[20rem] space-y-3 overflow-y-auto rounded-lg border border-edge bg-panel p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-slate-100">💉 手动注入污染事件</h3>
        <label className="block text-xs text-slate-400">
          事件类型
          <select
            value={etype}
            onChange={(e) => setEtype(e.target.value as Exclude<EventType, 'detected'>)}
            className="mt-1 w-full rounded border border-edge bg-ink px-2 py-1 text-sm text-slate-200"
          >
            <option value="sudden">突发泄漏</option>
            <option value="periodic">夜间偷排</option>
            <option value="gradual">渐变恶化</option>
          </select>
        </label>
        <EnterprisePicker value={source} onChange={setSource} enterprises={enterprises} />
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
        <label className="flex cursor-pointer items-start gap-2 rounded border border-edge bg-ink/60 p-2">
          <input
            type="checkbox"
            checked={silent}
            onChange={(e) => setSilent(e.target.checked)}
            className="mt-0.5 accent-sky-400"
          />
          <span className="text-xs text-slate-300">
            静默注入（只排污，不报警）
            <span className="mt-0.5 block text-slate-500">
              污染进入河网但不生成告警，注入后点顶部「📡 立即扫描」，
              由监测 Agent 自己从时序里发现并报警
            </span>
          </span>
        </label>
        <div className="flex gap-2 pt-1">
          <button
            onClick={submit}
            disabled={busy || !source}
            className="flex-1 rounded bg-danger px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-400 disabled:opacity-50"
          >
            {busy ? '注入中…' : silent ? '静默注入' : '注入'}
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

// 企业选择器:18 家企业用原生 <select> 时,下拉浮层由浏览器绘制、不受弹窗约束,
// 会溢到窗口外;改成受控下拉,列表限高可滚动、可搜索、长名截断
function EnterprisePicker({
  value, onChange, enterprises,
}: {
  value: string
  onChange: (id: string) => void
  enterprises: { id: string; name: string }[]
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const boxRef = useRef<HTMLDivElement>(null)
  const selected = enterprises.find((e) => e.id === value)

  // 点击外部 / Esc 关闭
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const kw = query.trim()
  const list = kw ? enterprises.filter((e) => e.name.includes(kw) || e.id.includes(kw)) : enterprises

  return (
    <div className="block text-xs text-slate-400" ref={boxRef}>
      <span>污染源企业</span>
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="mt-1 flex w-full items-center justify-between gap-2 rounded border border-edge bg-ink px-2 py-1 text-left text-sm"
        >
          <span className={`truncate ${selected ? 'text-slate-200' : 'text-slate-500'}`}>
            {selected?.name ?? '请选择…'}
          </span>
          <span className="shrink-0 text-slate-500">▾</span>
        </button>
        {open && (
          <div className="absolute z-10 mt-1 w-full rounded border border-edge bg-panel shadow-lg">
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="输入企业名筛选…"
              className="w-full border-b border-edge bg-ink px-2 py-1 text-sm text-slate-200 outline-none"
            />
            {/* 限高可滚动,且不超过窗口高度的 40% */}
            <ul className="max-h-[min(12rem,40vh)] overflow-y-auto py-1">
              {list.map((ent) => (
                <li key={ent.id}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange(ent.id)
                      setOpen(false)
                      setQuery('')
                    }}
                    className={`block w-full truncate px-2 py-1 text-left text-sm hover:bg-edge ${
                      ent.id === value ? 'text-accent' : 'text-slate-200'
                    }`}
                  >
                    {ent.name}
                  </button>
                </li>
              ))}
              {list.length === 0 && (
                <li className="px-2 py-1 text-xs text-slate-500">无匹配企业</li>
              )}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
