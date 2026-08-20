import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import type { EemMatrix } from '../types'
import { getStationEem, getEnterpriseEem } from '../api/watershed'
import { useWatershedStore } from '../store/watershedStore'
import { SeriesChart } from '../components/charts/SeriesChart'
import { EemContour } from '../components/charts/EemContour'

// 断面详情页:时序 + EEM"现场 vs 企业档案"并排对比
// 可用 ?event=evt_001 指定事件(现场 EEM 以 Ground Truth 源为主导)
export function StationPage() {
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const eventId = params.get('event') ?? undefined
  const enterprises = useWatershedStore((s) => s.data?.enterprises ?? [])
  const loadWatershed = useWatershedStore((s) => s.load)

  const [fieldEem, setFieldEem] = useState<EemMatrix | null>(null)
  const [entId, setEntId] = useState('')
  const [entEem, setEntEem] = useState<EemMatrix | null>(null)

  useEffect(() => {
    loadWatershed()
  }, [loadWatershed])

  useEffect(() => {
    if (id) getStationEem(id, eventId).then(setFieldEem).catch(() => {})
  }, [id, eventId])

  useEffect(() => {
    if (entId) getEnterpriseEem(entId).then(setEntEem).catch(() => setEntEem(null))
    else setEntEem(null)
  }, [entId])

  const entName = enterprises.find((e) => e.id === entId)?.name

  return (
    <div className="min-h-screen space-y-4 bg-ink p-4 text-slate-200">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">断面 {id}{eventId && <span className="ml-2 text-sm text-slate-400">事件 {eventId}</span>}</h1>
        <label className="text-xs text-slate-400">
          对比企业档案:
          <select
            value={entId}
            onChange={(e) => setEntId(e.target.value)}
            className="ml-2 rounded border border-edge bg-panel px-2 py-1 text-sm text-slate-200"
          >
            <option value="">请选择…</option>
            {enterprises.map((ent) => (
              <option key={ent.id} value={ent.id}>
                {ent.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="h-72 rounded-lg border border-edge p-2">
        <SeriesChart stationId={id} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <EemContour title="现场指纹" eem={fieldEem} />
        {entEem ? (
          <EemContour title={`档案指纹 · ${entName}`} eem={entEem} />
        ) : (
          <div className="flex min-h-[320px] items-center justify-center rounded-lg border border-dashed border-edge text-sm text-slate-500">
            选择企业后展示档案指纹并排对比
          </div>
        )}
      </div>
      <p className="text-xs text-slate-500">
        相似度打分由后端确定性引擎计算(见推理流 eem_score 证据),本页仅做可视化对比。
      </p>
    </div>
  )
}
