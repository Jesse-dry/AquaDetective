// investigationStore:WS 消息分发与 step_id 去重(重连安全)
import { describe, it, expect, beforeEach } from 'vitest'
import { useInvestigationStore } from '../src/store/investigationStore'
import type { WsMessage } from '../src/types'

const step = (id: string): WsMessage => ({
  type: 'step',
  data: { step_id: id, phase: '测试', clue: 'c', reasoning: 'r', evidence: [], status: 'verified' },
})

beforeEach(() => useInvestigationStore.getState().reset())

describe('investigationStore', () => {
  it('step 按 step_id 去重(重连重放不产生重复卡片)', () => {
    const s = useInvestigationStore.getState()
    s.applyMessage(step('stp_01'))
    s.applyMessage(step('stp_01'))
    s.applyMessage(step('stp_02'))
    expect(useInvestigationStore.getState().steps.map((p) => p.step_id))
      .toEqual(['stp_01', 'stp_02'])
  })

  it('hypothesis 按 id 覆盖更新(分数变化)', () => {
    const s = useInvestigationStore.getState()
    s.applyMessage({ type: 'hypothesis', data: { id: 'h1', target: '某厂', score: 0.4, status: 'candidate' } })
    s.applyMessage({ type: 'hypothesis', data: { id: 'h1', target: '某厂', score: 0.9, status: 'candidate' } })
    expect(useInvestigationStore.getState().hypotheses['h1'].score).toBe(0.9)
  })

  it('6 类消息各归其位', () => {
    const s = useInvestigationStore.getState()
    s.applyMessage({ type: 'agent_talk', data: { agent: '法规Agent', text: '按 GB 3838' } })
    s.applyMessage({ type: 'conclusion', data: { source_id: 'ent_01', confidence: 0.93, evidence_summary: 'x' } })
    s.applyMessage({ type: 'failed', data: { reason: 'r', suggestions: ['s'] } })
    s.applyMessage({ type: 'report_ready', data: { report_id: 'inv_1' } })
    const st = useInvestigationStore.getState()
    expect(st.talks).toHaveLength(1)
    expect(st.conclusion?.source_id).toBe('ent_01')
    expect(st.failed?.reason).toBe('r')
    expect(st.reportId).toBe('inv_1')
  })

  it('start 清空上一轮调查状态', () => {
    const s = useInvestigationStore.getState()
    s.applyMessage(step('stp_01'))
    s.start('inv_new')
    const st = useInvestigationStore.getState()
    expect(st.steps).toHaveLength(0)
    expect(st.investigationId).toBe('inv_new')
  })
})
