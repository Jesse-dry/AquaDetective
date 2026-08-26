import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import { getSeries } from '../../api/series'
import { useUiStore } from '../../store/uiStore'
import { indicatorLabel } from '../../utils/labels'

// 断面时序曲线:异常时段由调用方传 markArea(后续接 events)
export function SeriesChart({ stationId }: { stationId: string | null }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const indicator = useUiStore((s) => s.selectedIndicator)

  useEffect(() => {
    if (!ref.current) return
    chartRef.current = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    const onResize = () => chartRef.current?.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chartRef.current?.dispose()
    }
  }, [])

  useEffect(() => {
    if (!stationId || !chartRef.current) return
    getSeries({ station: stationId, indicator, step: 10 }).then((resp) => {
      chartRef.current?.setOption({
        backgroundColor: 'transparent',
        grid: { left: 48, right: 16, top: 24, bottom: 24 },
        tooltip: { trigger: 'axis' },
        xAxis: {
          type: 'time',
          axisLabel: { color: '#94a3b8' },
          axisLine: { lineStyle: { color: '#1f2c4a' } },
        },
        yAxis: {
          type: 'value',
          scale: true,
          axisLabel: { color: '#94a3b8' },
          splitLine: { lineStyle: { color: '#1f2c4a' } },
        },
        series: [{
          name: indicatorLabel(indicator),
          type: 'line',
          showSymbol: false,
          sampling: 'lttb',
          lineStyle: { color: '#38bdf8', width: 1.5 },
          data: resp.data.map((p) => [p.ts , p.value]),
        }],
      })
    }).catch(() => {})
  }, [stationId, indicator])

  if (!stationId) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        点击地图断面查看时序曲线
      </div>
    )
  }
  return <div ref={ref} className="h-full w-full" />
}
