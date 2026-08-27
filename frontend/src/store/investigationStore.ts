import { create } from 'zustand'
import type {
  WsMessage,
  StepData,
  HypothesisData,
  AgentTalkData,
  ConclusionData,
  FailedData,
} from '../types'
import type { ConnStatus } from '../ws/connection'

// 当前调查:WS 消息按 type 分发到各分片;step 以 step_id 去重(重连重放安全)
interface InvestigationState {
  investigationId: string | null
  connStatus: ConnStatus
  steps: StepData[]
  hypotheses: Record<string, HypothesisData>
  talks: AgentTalkData[]
  conclusion: ConclusionData | null
  failed: FailedData | null
  reportId: string | null

  start: (investigationId: string) => void
  reset: () => void
  setConnStatus: (s: ConnStatus) => void
  applyMessage: (msg: WsMessage) => void
}

const initial = {
  investigationId: null,
  connStatus: 'closed' as ConnStatus,
  steps: [] as StepData[],
  hypotheses: {} as Record<string, HypothesisData>,
  talks: [] as AgentTalkData[],
  conclusion: null,
  failed: null,
  reportId: null,
}

export const useInvestigationStore = create<InvestigationState>((set, get) => ({
  ...initial,

  start: (investigationId) => set({ ...initial, investigationId, connStatus: 'connecting' }),

  reset: () => set({ ...initial }),

  setConnStatus: (connStatus) => set({ connStatus }),

  applyMessage: (msg) => {
    const s = get()
    switch (msg.type) {
      case 'step': {
        // step_id 去重:重连补齐时重复消息不产生重复卡片
        if (s.steps.some((p) => p.step_id === msg.data.step_id)) return
        set({ steps: [...s.steps, msg.data] })
        return
      }
      case 'hypothesis':
        set({ hypotheses: { ...s.hypotheses, [msg.data.id]: msg.data } })
        return
      case 'agent_talk': {
        // (agent, text) 去重:重连补齐重放时重复消息不产生重复卡片
        if (s.talks.some((t) => t.agent === msg.data.agent && t.text === msg.data.text)) return
        set({ talks: [...s.talks, msg.data] })
        return
      }
      case 'conclusion':
        set({ conclusion: msg.data })
        return
      case 'failed':
        set({ failed: msg.data })
        return
      case 'report_ready':
        set({ reportId: msg.data.report_id })
        return
    }
  },
}))
