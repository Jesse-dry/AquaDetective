import { useState } from 'react'
import { resetWorld } from '../../api/simulate'
import { useAlertStore } from '../../store/alertStore'
import { useInvestigationStore } from '../../store/investigationStore'
import { InjectDialog } from './InjectDialog'

// 场景脚本栏:三条预置脚本提示 + 一键重置 + 手动注入(演示保险)
const SCENARIOS = [
  { id: 'evt_001', name: '场景一 · 夜间偷排', hint: '电镀厂 · 指纹溯源全流程' },
  { id: 'evt_002', name: '场景二 · 突发泄漏', hint: '化工园区 · 扩散动画' },
  { id: 'evt_003', name: '场景三 · 渐变恶化', hint: '污水厂 · CUSUM 长周期检出' },
]

export function ScenarioBar() {
  const [injectOpen, setInjectOpen] = useState(false)
  const [resetting, setResetting] = useState(false)
  const refresh = useAlertStore((s) => s.refresh)
  const resetInv = useInvestigationStore((s) => s.reset)

  const onReset = async () => {
    setResetting(true)
    try {
      await resetWorld()
      resetInv()
      await refresh()
    } finally {
      setResetting(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      {SCENARIOS.map((s) => (
        <span
          key={s.id}
          title={s.hint}
          className="hidden rounded border border-edge bg-panel px-2 py-1 text-xs text-slate-400 lg:inline"
        >
          {s.name}
        </span>
      ))}
      <button
        onClick={() => setInjectOpen(true)}
        className="rounded bg-warn/80 px-3 py-1 text-xs font-semibold text-ink hover:bg-warn"
      >
        💉 注入事件
      </button>
      <button
        onClick={onReset}
        disabled={resetting}
        className="rounded bg-edge px-3 py-1 text-xs font-semibold text-slate-200 hover:bg-slate-600 disabled:opacity-50"
      >
        {resetting ? '重置中…' : '♻️ 重置世界'}
      </button>
      {injectOpen && <InjectDialog onClose={() => setInjectOpen(false)} />}
    </div>
  )
}
