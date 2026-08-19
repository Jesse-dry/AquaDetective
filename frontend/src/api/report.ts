import { IS_MOCK } from './client'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'

// GET /investigations/{id}/report 返回 Markdown 文本(非 JSON,单独封装)
export async function getReport(investigationId: string): Promise<string> {
  const url = IS_MOCK
    ? '/mock/report.md'
    : `${API_BASE}/investigations/${investigationId}/report`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`report: HTTP ${res.status}`)
  return res.text()
}
