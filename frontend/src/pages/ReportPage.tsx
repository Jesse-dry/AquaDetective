import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { getReport } from '../api/report'
import { getInvestigation } from '../api/investigate'
import { eventLabel } from '../utils/labels'

// 报告页:Markdown 渲染 + window.print() 导出 PDF(打印样式隐藏导航白底)
// 文档标题设为可辨名(浏览器打印为 PDF 时以 document.title 作默认文件名)
export function ReportPage() {
  const { id = '' } = useParams()
  const [markdown, setMarkdown] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [docTitle, setDocTitle] = useState('溯源报告')

  useEffect(() => {
    getReport(id).then(setMarkdown).catch((e) => setError(String(e)))
  }, [id])

  // 组装可辨标题:溯源报告-事件1-耀光金属表面处理-20250215
  useEffect(() => {
    getInvestigation(id)
      .then((inv) => {
        const ev = inv.event_id ? eventLabel(inv.event_id) : '调查'
        const src = inv.conclusion?.source_name
        const d = new Date(inv.started_at ?? Date.now())
        const date = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
        setDocTitle(`溯源报告-${ev}${src ? `-${src}` : ''}-${date}`)
      })
      .catch(() => {})
  }, [id])

  useEffect(() => {
    const prev = document.title
    document.title = docTitle
    return () => {
      document.title = prev
    }
  }, [docTitle])

  return (
    <div className="min-h-screen bg-ink p-6 text-slate-200 print:bg-white print:text-black">
      <div className="mx-auto max-w-3xl">
        <div className="mb-4 flex items-center justify-between print:hidden">
          <h1 className="text-lg font-bold">{docTitle}</h1>
          <button
            onClick={() => window.print()}
            className="rounded bg-accent px-4 py-1.5 text-sm font-semibold text-ink hover:bg-sky-300"
          >
            🖨️ 导出 PDF
          </button>
        </div>
        {error && <p className="text-danger">报告加载失败：{error}</p>}
        {!markdown && !error && <p className="text-slate-500">加载中…</p>}
        {markdown && (
          <article className="report-markdown rounded-lg border border-edge bg-panel p-6">
            <ReactMarkdown>{markdown}</ReactMarkdown>
          </article>
        )}
      </div>
    </div>
  )
}
