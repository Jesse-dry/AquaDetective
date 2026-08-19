// fetch 封装:基址 / 超时 / 错误统一处理;VITE_MOCK=1 时改读 public/mock
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'
export const IS_MOCK = import.meta.env.VITE_MOCK === '1'

const TIMEOUT_MS = 15_000

export async function apiGet<T>(path: string, mockFile?: string): Promise<T> {
  if (IS_MOCK && mockFile) {
    const res = await fetch(`/mock/${mockFile}`)
    if (!res.ok) throw new Error(`mock ${mockFile}: HTTP ${res.status}`)
    return res.json() as Promise<T>
  }
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: ctrl.signal })
    if (!res.ok) throw new Error(`GET ${path}: HTTP ${res.status}`)
    return (await res.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  if (IS_MOCK) {
    // Mock 模式下写操作直接回显成功,由调用方走 mock 流程
    return { investigation_id: 'mock_inv_001' } as T
  }
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl.signal,
    })
    if (!res.ok) throw new Error(`POST ${path}: HTTP ${res.status}`)
    return (await res.json()) as T
  } finally {
    clearTimeout(timer)
  }
}
