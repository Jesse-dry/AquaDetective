import type { Evidence } from '../../types'

// 嫌疑企业置信度条形图(从 step 证据聚合,纯展示;只取数值型证据)
export function ConfidenceBar({ items }: { items: Evidence[] }) {
  const sorted = items
    .filter((it): it is Evidence & { value: number } => typeof it.value === 'number')
    .sort((a, b) => b.value - a.value)
  return (
    <div className="space-y-1.5">
      {sorted.map((it, i) => (
        <div key={i}>
          <div className="flex justify-between text-xs text-slate-300">
            <span>{it.target}</span>
            <span className="tabular-nums">{Math.round(it.value * 100)}%</span>
          </div>
          <div className="mt-0.5 h-2 overflow-hidden rounded bg-edge/60">
            <div
              className={`h-full rounded ${it.value >= 0.85 ? 'bg-danger' : 'bg-accent'}`}
              style={{ width: `${Math.round(it.value * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
