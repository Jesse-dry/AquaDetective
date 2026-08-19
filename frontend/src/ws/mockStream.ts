// Mock 推理流:按契约逐条回放 public/mock/investigationStream.json
// 用途:1) 契约冻结前后端并行开发 2) 演示现场离线兜底
import type { WsMessage } from '../types'

export interface MockStreamHandlers {
  onMessage: (msg: WsMessage) => void
  onDone?: () => void
}

export class MockStream {
  private timer: ReturnType<typeof setTimeout> | null = null
  private cancelled = false

  async start(handlers: MockStreamHandlers, intervalMs = 900) {
    const res = await fetch('/mock/investigationStream.json')
    const messages = (await res.json()) as WsMessage[]
    let i = 0
    const tick = () => {
      if (this.cancelled) return
      if (i >= messages.length) {
        handlers.onDone?.()
        return
      }
      handlers.onMessage(messages[i])
      i += 1
      this.timer = setTimeout(tick, intervalMs)
    }
    tick()
  }

  stop() {
    this.cancelled = true
    if (this.timer) clearTimeout(this.timer)
  }
}
