import type { AgentTalkData } from '../../types'

// Agent 会议气泡:不同 Agent 不同颜色,"会议"即多条交替气泡
const AGENT_STYLE: Record<string, { name: string; color: string }> = {
  monitor: { name: '监测 Agent', color: 'bg-sky-500/20 text-sky-300' },
  investigator: { name: '溯源侦探', color: 'bg-amber-500/20 text-amber-300' },
  compliance: { name: '法规 Agent', color: 'bg-violet-500/20 text-violet-300' },
  responder: { name: '处置 Agent', color: 'bg-emerald-500/20 text-emerald-300' },
  reporter: { name: '报告 Agent', color: 'bg-rose-500/20 text-rose-300' },
}

export function AgentTalk({ talk }: { talk: AgentTalkData }) {
  const style = AGENT_STYLE[talk.agent] ?? { name: talk.agent, color: 'bg-edge/40 text-slate-300' }
  return (
    <div className="flex gap-2">
      <span className={`h-fit shrink-0 rounded px-1.5 py-0.5 text-xs ${style.color}`}>
        {style.name}
      </span>
      <p className="rounded-lg rounded-tl-none bg-edge/30 px-2.5 py-1.5 text-sm text-slate-200">
        {talk.text}
      </p>
    </div>
  )
}
