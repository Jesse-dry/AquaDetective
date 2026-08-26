import { useInvestigationStore } from '../../store/investigationStore'
import { industryLabel } from '../../utils/labels'

// 假设排行榜:分数实时变化,被排除(rejected)假设变灰划线
// 注意:WS hypothesis 消息的 target 是企业名称,直接展示
export function HypothesisBoard() {
  const hypotheses = useInvestigationStore((s) => s.hypotheses)
  const list = Object.values(hypotheses).sort((a, b) => b.score - a.score)
  if (list.length === 0) return null

  return (
    <div className="rounded-lg border border-edge bg-panel p-3">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
        嫌疑假设榜
      </h3>
      <div className="space-y-1.5">
        {list.map((h) => {
          const eliminated = h.status === 'rejected' || h.status === 'eliminated'
          const pct = Math.round(h.score * 100)
          return (
            <div key={h.id} className={eliminated ? 'opacity-40' : ''} title={h.reasons}>
              <div className="flex justify-between text-xs">
                <span className={eliminated ? 'line-through' : ''}>
                  {h.target}
                  {h.industry && <span className="ml-1 text-slate-500">({industryLabel(h.industry)})</span>}
                </span>
                <span className="tabular-nums text-slate-400">{pct}%</span>
              </div>
              <div className="mt-0.5 h-1.5 overflow-hidden rounded bg-edge/60">
                <div
                  className={`h-full rounded transition-all duration-700 ${
                    eliminated ? 'bg-slate-600' : pct >= 85 ? 'bg-danger' : 'bg-accent'
                  }`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
