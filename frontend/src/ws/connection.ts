// WS 连接管理:自动重连(指数退避,最多 5 次)+ 连接状态回调
// 重连成功后由调用方调 GET /investigations/{id} 补齐状态
import { parseWsMessage } from './messages'
import type { WsMessage } from '../types'

export type ConnStatus = 'connecting' | 'open' | 'closed' | 'failed'

export interface ConnectionHandlers {
  onMessage: (msg: WsMessage) => void
  onStatus?: (status: ConnStatus) => void
  onReconnect?: () => void // 重连成功,调用方负责补齐
}

const MAX_RETRY = 5

export class InvestigationConnection {
  private ws: WebSocket | null = null
  private retries = 0
  private closedByUser = false

  constructor(
    private investigationId: string,
    private handlers: ConnectionHandlers,
  ) {}

  connect() {
    this.closedByUser = false
    this.retries = 0
    this.open()
  }

  private open() {
    this.handlers.onStatus?.('connecting')
    const base = import.meta.env.VITE_WS_BASE ?? `${location.origin}/api/v1`
    const url = `${base.replace(/^http/, 'ws')}/ws?investigation_id=${this.investigationId}`
    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      this.handlers.onStatus?.('open')
      if (this.retries > 0) this.handlers.onReconnect?.()
      this.retries = 0
    }
    ws.onmessage = (ev) => {
      const msg = parseWsMessage(String(ev.data))
      if (msg) this.handlers.onMessage(msg)
    }
    ws.onclose = () => {
      if (this.closedByUser) return
      if (this.retries < MAX_RETRY) {
        this.retries += 1
        this.handlers.onStatus?.('connecting')
        setTimeout(() => this.open(), Math.min(2 ** this.retries * 500, 8000))
      } else {
        this.handlers.onStatus?.('failed')
      }
    }
    ws.onerror = () => ws.close()
  }

  close() {
    this.closedByUser = true
    this.ws?.close()
    this.handlers.onStatus?.('closed')
  }
}
