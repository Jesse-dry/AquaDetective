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
  closed: ['⚪', '待命'],
  failed: ['🔴', '连接失败'],
} as const

export function ReasoningPanel() {
  const inv = useInvestigationStore()
  const watershed = useWatershedStore((s) => s.data)
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  // 用户是否贴近底部(新消息自动跟随的前提;用户上翻阅读时不打断)
  const stickBottom = useRef(true)

  // 程序触发的滚动会引发 onScroll,用标志抑制它误更新 stickBottom
  const suppressScroll = useRef(false)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => {
      if (suppressScroll.current) return
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight
      stickBottom.current = distance < 60
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  // 新调查开始(investigationId 变化):重置滚动状态,从头展示,不自动跟到底
  useEffect(() => {
    stickBottom.current = false
    const el = scrollRef.current
    if (!el) return
    suppressScroll.current = true
    el.scrollTop = 0
    // 下一帧解除抑制(程序滚动产生的 scroll 事件在此期间被忽略)
    requestAnimationFrame(() => { suppressScroll.current = false })
  }, [inv.investigationId])

  useEffect(() => {
    // 仅在用户贴近底部时跟随滚动;且只在面板容器内滚,不把整个页面带走
    if (!stickBottom.current) return
    const el = scrollRef.current
    if (!el || !bottomRef.current) return
    // 内容未溢出容器时不滚,避免空面板把整页拽到底
    if (el.scrollHeight <= el.clientHeight + 4) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [inv.steps.length, inv.talks.length, inv.conclusion, inv.failed])

  const sourceName = inv.conclusion
    ? watershed?.enterprises.find((e) => e.id === inv.conclusion?.source_id)?.name ??
      inv.conclusion.source_id
    : null

  const [icon, label] = STATUS_LABEL[inv.connStatus]

  return (
    <div ref={scrollRef} className="flex h-full flex-col gap-3 overflow-y-auto p-3">
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
