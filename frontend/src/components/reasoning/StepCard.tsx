import type { StepData } from '../../types'
import { EvidenceChip } from './EvidenceChip'
import { Typewriter } from './Typewriter'
import { humanize, phaseLabel, stepIdLabel } from '../../utils/labels'

// 单步"线索→推理→证据"卡片
const PHASE_LABEL: Record<string, string> = {
  parse_event: '事件解析',
  topology_filter: '上游排查',
  dispersion_check: '扩散反推',
  fingerprint_match: '指纹比对',
  pattern_check: '规律分析',
  conclude: '结论',
}

export function StepCard({ step }: { step: StepData }) {
  const phase = PHASE_LABEL[step.phase] ?? phaseLabel(step.phase)
  return (
    <div className="rounded-lg border border-edge bg-panel p-3">
      <div className="mb-1 flex items-center gap-2">
        <span className="rounded bg-accent/15 px-1.5 py-0.5 text-xs text-accent">
          {phase}
        </span>
        <span className="text-xs text-slate-500">{stepIdLabel(step.step_id)}</span>
        {step.status === 'verified' && <span className="text-xs text-ok">✓ 已验证</span>}
        {step.status === 'rejected' && <span className="text-xs text-slate-500">✗ 已排除</span>}
      </div>
      <p className="mb-1 text-sm text-warn">🔍 {humanize(step.clue)}</p>
      <p className="mb-2 text-sm leading-relaxed text-slate-300">
        <Typewriter text={humanize(step.reasoning)} />
      </p>
      {step.evidence.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {step.evidence.map((ev, i) => (
            <EvidenceChip key={i} evidence={ev} />
          ))}
        </div>
      )}
    </div>
  )
}
