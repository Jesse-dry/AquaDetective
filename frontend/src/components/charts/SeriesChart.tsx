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
    // 容器尺寸变化即重绘:footer 是 flex 布局,初始化时高度可能还没算出来,
    // 只监听 window.resize 会漏掉这种"容器自己变大"的情况,导致图表一直空白
    const ro = new ResizeObserver(() => chartRef.current?.resize())
    ro.observe(ref.current)
    return () => {
      ro.disconnect()
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

  // 图表容器常驻(不再用 early-return 切换节点):
  // 否则初始无断面时 ref 未挂载,初始化 effect 空跑一次后不再重跑,选中断面也画不出来
  return (
    <div className="relative h-full w-full">
      <div ref={ref} className="h-full w-full" />
      {!stationId && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">
          点击地图断面查看时序曲线
        </div>
      )}
    </div>
  )
}
