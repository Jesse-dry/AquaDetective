import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { PollutionEvent } from '../types'
import { getEvents } from '../api/events'
import { getRecordings, getInvestigation } from '../api/investigate'
import { useWatershedStore } from '../store/watershedStore'
import { RealDataValidation } from '../components/charts/RealDataValidation'
import { E2ETraceCase } from '../components/charts/E2ETraceCase'
import { PermitEnterprises } from '../components/charts/PermitEnterprises'
import { eventLabel, etypeLabel } from '../utils/labels'

// 真实数据对标页(W5):本系统验证结果 + 行业真实落地案例
// 声明:演示流域为模拟数据,真实数据仅用于算法验证
const REAL_CASES = [
  {
    place: '台州椒江',
    title: '浙江首个企业端"水质指纹"溯源数据库',
    detail: '清华苏州环境创新研究院技术落地,建立企业端指纹库,实现污染来源快速比对。',
  },
  {
    place: '山西长治',
    title: '清华技术让"隐形污染显形"',
    detail: '引入三维荧光光谱指纹技术,识别常规指标难以区分的隐性工业排放。',
  },
  {
    place: '黄河乌海段',
    title: '24 小时预警溯源系统上线',
    detail: '全天候自动监测 + 指纹比对,异常发生后自动锁定疑似排放源。',
  },
  {
    place: '浙江宁波',
    title: '"水质指纹"最快 21 分钟溯源',
    detail: '从异常检出到锁定污染源企业最快 21 分钟,验证指纹溯源的工程时效性。',
  },
]

interface VerifiedRow {
  event: PollutionEvent
  sourceName: string | null
  confidence: number | null
  hit: boolean | null // 结论是否命中 Ground Truth
}

export function BenchmarkPage() {
  const [rows, setRows] = useState<VerifiedRow[]>([])
  const watershed = useWatershedStore((s) => s.data)
  const loadWatershed = useWatershedStore((s) => s.load)

  useEffect(() => {
    loadWatershed()
  }, [loadWatershed])

  useEffect(() => {
    if (!watershed) return
    ;(async () => {
      const events = await getEvents()
      const nameOf = (id?: string) =>
        watershed.enterprises.find((e) => e.id === id)?.name ?? null
      const rows: VerifiedRow[] = []
      try {
        const { recordings } = await getRecordings()
        const invs = await Promise.all(recordings.map(getInvestigation))
        for (const ev of events) {
          const inv = invs.find((i) => i.event_id === ev.id && i.status === 'resolved')
          const src = inv?.conclusion?.source_id
          rows.push({
            event: ev,
            sourceName: nameOf(src ?? undefined),
            confidence: inv?.conclusion?.confidence ?? null,
            hit: inv ? src === ev.truth_source : null,
          })
        }
      } catch {
        for (const ev of events) {
          rows.push({ event: ev, sourceName: null, confidence: null, hit: null })
        }
      }
      setRows(rows)
    })().catch(() => {})
  }, [watershed])

  return (
    <div className="min-h-screen bg-ink p-6 text-slate-200">
      <div className="mx-auto max-w-4xl space-y-6">
        <Link to="/" className="inline-block rounded bg-edge px-3 py-1 text-xs text-slate-300 hover:bg-slate-600">
          ← 返回大屏
        </Link>
        <h1 className="text-lg font-bold">📊 真实数据对标</h1>
        <p className="rounded-lg border border-warn/50 bg-warn/10 p-3 text-sm text-warn">
          声明:演示流域(清源河)为模拟数据;②节验证使用真实太湖国控断面公开数据(2021–2025),③节真实案例仅用于说明算法与行业落地技术同源。
        </p>

        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-300">① 本系统算法验证(三条预置事件)</h2>
          <div className="overflow-hidden rounded-lg border border-edge">
            <table className="w-full text-xs">
              <thead className="bg-edge/40 text-slate-300">
                <tr>
                  <th className="px-3 py-2 text-left">事件</th>
                  <th className="px-3 py-2 text-left">类型</th>
                  <th className="px-3 py-2 text-left">Ground Truth</th>
                  <th className="px-3 py-2 text-left">锁定结果</th>
                  <th className="px-3 py-2 text-left">置信度</th>
                  <th className="px-3 py-2 text-left">判定</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ event: ev, sourceName, confidence, hit }) => (
                  <tr key={ev.id} className="border-t border-edge">
                    <td className="px-3 py-2">{eventLabel(ev.id)}</td>
                    <td className="px-3 py-2">{etypeLabel(ev.etype)}</td>
                    <td className="px-3 py-2 text-slate-400">
                      {watershed?.enterprises.find((e) => e.id === ev.truth_source)?.name ?? ev.truth_source}
                    </td>
                    <td className="px-3 py-2">{sourceName ?? '—'}</td>
                    <td className="px-3 py-2 tabular-nums">
                      {confidence !== null ? `${Math.round(confidence * 100)}%` : '—'}
                    </td>
                    <td className="px-3 py-2">
                      {hit === true && <span className="text-ok">✓ 命中</span>}
                      {hit === false && <span className="text-danger">✗ 未命中</span>}
                      {hit === null && <span className="text-slate-500">未运行</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            「未运行」表示该事件尚未在本机完成调查;在大屏触发侦查后本表自动更新。
          </p>
        </section>

        <RealDataValidation />

        <E2ETraceCase />

        <PermitEnterprises />

        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-300">⑤ 行业真实落地案例(技术同源背书)</h2>
          <div className="grid grid-cols-2 gap-3">
            {REAL_CASES.map((c) => (
              <div key={c.place} className="rounded-lg border border-edge bg-panel p-4">
                <p className="mb-1 text-xs text-accent">{c.place}</p>
                <p className="mb-1 text-sm font-semibold text-slate-100">{c.title}</p>
                <p className="text-xs leading-relaxed text-slate-400">{c.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-300">④ 核心原理</h2>
          <p className="rounded-lg border border-edge bg-panel p-4 text-xs leading-relaxed text-slate-400">
            不同行业废水具有特征性三维荧光光谱(EEM)——如同"水质指纹"。本系统与清华苏州环境
            创新研究院落地技术同源:为每个污染源企业建立"光谱指纹 + 特征污染物比例"双指纹档案,
            异常发生后将断面现场 EEM 与指纹库做确定性相似度比对(余弦相似度 + 比例向量),
            结合流域拓扑可达性、对流扩散反推与排放规律分析,多路证据闭环锁定污染源。
            全部数值计算由确定性引擎完成,大模型仅负责推理编排与表达,从机制上杜绝"AI 编数据"。
          </p>
        </section>
      </div>
    </div>
  )
}
