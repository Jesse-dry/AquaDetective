// WS 消息类型守卫:消息体结构见 types/index.ts
import type { WsMessage } from '../types'

export const WS_MESSAGE_TYPES = [
  'step',
  'hypothesis',
  'agent_talk',
  'conclusion',
  'failed',
  'report_ready',
] as const

export function parseWsMessage(raw: string): WsMessage | null {
  try {
    const msg = JSON.parse(raw) as WsMessage
    if (!WS_MESSAGE_TYPES.includes(msg.type)) return null
    return msg
  } catch {
    return null
  }
}
