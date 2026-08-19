import type { Evidence } from '../../types'

// 证据条:eem_score / pollutant_score / topology / dispersion / pattern
const KIND_LABEL: Record<string, string> = {
  eem_score: '光谱指纹',
  pollutant_score: '污染物指纹',
  topology: '拓扑可达',
  dispersion: '扩散校核',
  pattern: '排放规律',
}

export function EvidenceChip({ evidence }: { evidence: Evidence }) {
  const pct = Math.round(evidence.value * 100)
  const tone =
    evidence.value >= 0.85 ? 'bg-danger/20 text-danger border-danger/40'
    : evidence.value >= 0.6 ? 'bg-warn/20 text-warn border-warn/40'
    : 'bg-edge/40 text-slate-400 border-edge'
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs ${tone}`}>
      <span>{KIND_LABEL[evidence.kind] ?? evidence.kind}</span>
      <span className="font-semibold">{evidence.target}</span>
      <span className="tabular-nums">{pct}%</span>
    </span>
  )
}
