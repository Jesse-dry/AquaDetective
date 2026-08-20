// WS 消息守卫:非法/控制消息不进入渲染层
import { describe, it, expect } from 'vitest'
import { parseWsMessage } from '../src/ws/messages'

describe('parseWsMessage', () => {
  it('接受 6 类业务消息', () => {
    for (const t of ['step', 'hypothesis', 'agent_talk', 'conclusion', 'failed', 'report_ready']) {
      expect(parseWsMessage(JSON.stringify({ type: t, data: {} }))?.type).toBe(t)
    }
  })

  it('丢弃控制消息 connected/error', () => {
    expect(parseWsMessage(JSON.stringify({ type: 'connected', data: {} }))).toBeNull()
    expect(parseWsMessage(JSON.stringify({ type: 'error', data: {} }))).toBeNull()
  })

  it('容错:非 JSON 与未知类型返回 null', () => {
    expect(parseWsMessage('not json')).toBeNull()
    expect(parseWsMessage(JSON.stringify({ type: 'unknown', data: {} }))).toBeNull()
  })
})
