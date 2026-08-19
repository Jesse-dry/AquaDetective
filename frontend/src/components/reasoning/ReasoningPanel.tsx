import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useInvestigationStore } from '../../store/investigationStore'
import { useWatershedStore } from '../../store/watershedStore'
import { StepCard } from './StepCard'
import { HypothesisBoard } from './HypothesisBoard'
import { AgentTalk } from './AgentTalk'

// 推理流式面板:demo 的灵魂,按 WS 6 类消息渲染
const STATUS_LABEL = {
  connecting: ['🟡', '连接中'],
  open: ['🟢', '实时'],
  closed: ['⚪', '未连接'],
  failed: ['🔴', '连接失败'],
} as const

export function ReasoningPanel() {
  const inv = useInvestigationStore()
  const watershed = useWatershedStore((s) => s.data)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [inv.steps.length, inv.talks.length, inv.conclusion, inv.failed])

  const sourceName = inv.conclusion
    ? watershed?.enterprises.find((e) => e.id === inv.conclusion?.source_id)?.name ??
      inv.conclusion.source_id
    : null

  const [icon, label] = STATUS_LABEL[inv.connStatus]

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-200">🕵️ 侦探推理流</h2>
        <span className="text-xs text-slate-400">
          {icon} {label}
        </span>
      </div>

      {inv.steps.length === 0 && !inv.conclusion && (
        <p className="py-8 text-center text-sm text-slate-500">
          等待调查任务——点击左侧告警的「开始侦查」
        </p>
      )}

      <HypothesisBoard />

      {inv.steps.map((step) => (
        <StepCard key={step.step_id} step={step} />
      ))}

      {inv.talks.length > 0 && (
        <div className="space-y-2 rounded-lg border border-edge bg-panel p-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Agent 会议
          </h3>
          {inv.talks.map((talk, i) => (
            <AgentTalk key={i} talk={talk} />
          ))}
        </div>
      )}

      {inv.conclusion && (
        <div className="rounded-lg border-2 border-danger/60 bg-danger/10 p-4">
          <h3 className="mb-1 font-bold text-danger">🎯 锁定污染源:{sourceName}</h3>
          <p className="mb-1 text-sm text-slate-200">
            置信度 <span className="font-bold tabular-nums">{Math.round(inv.conclusion.confidence * 100)}%</span>
          </p>
          <p className="text-sm text-slate-400">{inv.conclusion.evidence_summary}</p>
        </div>
      )}

      {inv.failed && (
        <div className="rounded-lg border-2 border-warn/60 bg-warn/10 p-4">
          <h3 className="mb-1 font-bold text-warn">⚠️ 无法锁定:{inv.failed.reason}</h3>
          <ul className="list-inside list-disc text-sm text-slate-300">
            {inv.failed.suggestions.map((sug, i) => (
              <li key={i}>{sug}</li>
            ))}
          </ul>
        </div>
      )}

      {inv.reportId && (
        <Link
          to={`/report/${inv.reportId}`}
          className="block rounded-lg bg-accent px-4 py-2 text-center text-sm font-semibold text-ink hover:bg-sky-300"
        >
          📄 查看溯源报告
        </Link>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
