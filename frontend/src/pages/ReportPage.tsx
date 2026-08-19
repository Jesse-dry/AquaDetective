import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { getReport } from '../api/report'

// 报告页:Markdown 渲染 + window.print() 导出 PDF(打印样式隐藏导航白底)
export function ReportPage() {
  const { id = '' } = useParams()
  const [markdown, setMarkdown] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getReport(id).then(setMarkdown).catch((e) => setError(String(e)))
  }, [id])

  return (
    <div className="min-h-screen bg-ink p-6 text-slate-200 print:bg-white print:text-black">
      <div className="mx-auto max-w-3xl">
        <div className="mb-4 flex items-center justify-between print:hidden">
          <h1 className="text-lg font-bold">溯源报告 · {id}</h1>
          <button
            onClick={() => window.print()}
            className="rounded bg-accent px-4 py-1.5 text-sm font-semibold text-ink hover:bg-sky-300"
          >
            🖨️ 导出 PDF
          </button>
        </div>
        {error && <p className="text-danger">报告加载失败:{error}</p>}
        {!markdown && !error && <p className="text-slate-500">加载中…</p>}
        {markdown && (
          <article className="prose prose-invert max-w-none rounded-lg border border-edge bg-panel p-6 print:border-0 print:bg-white print:p-0 prose-headings:text-slate-100 print:prose-headings:text-black">
            <ReactMarkdown>{markdown}</ReactMarkdown>
          </article>
        )}
      </div>
    </div>
  )
}
