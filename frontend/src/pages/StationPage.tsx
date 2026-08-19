import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import type { EemMatrix } from '../types'
import { getStationEem } from '../api/watershed'
import { SeriesChart } from '../components/charts/SeriesChart'
import { EemContour } from '../components/charts/EemContour'

// 断面详情页:多指标时序 + EEM 现场/档案并排对比
export function StationPage() {
  const { id = '' } = useParams()
  const [eem, setEem] = useState<EemMatrix | null>(null)

  useEffect(() => {
    if (id) getStationEem(id).then(setEem).catch(() => {})
  }, [id])

  return (
    <div className="min-h-screen space-y-4 bg-ink p-4 text-slate-200">
      <h1 className="text-lg font-bold">断面 {id}</h1>
      <div className="h-72 rounded-lg border border-edge p-2">
        <SeriesChart stationId={id} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <EemContour title="现场指纹" eem={eem} />
        <EemContour title="企业档案指纹(待接入下拉切换)" eem={eem} />
      </div>
    </div>
  )
}
