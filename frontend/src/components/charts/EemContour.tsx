import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { EemMatrix } from '../../types'

// EEM 等高线图(heatmap 渲染 61x71 矩阵)
export function EemContour({ title, eem }: { title: string; eem: EemMatrix | null }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || !eem) return
    const chart = echarts.init(ref.current)
    const data: [number, number, number][] = []
    let max = 0
    eem.matrix.forEach((row, i) =>
      row.forEach((v, j) => {
        data.push([eem.lex[j], eem.lem[i], v])
        if (v > max) max = v
      }),
    )
    chart.setOption({
      backgroundColor: 'transparent',
      title: { text: title, left: 'center', textStyle: { color: '#cbd5e1', fontSize: 13 } },
      grid: { left: 64, right: 70, top: 36, bottom: 40 },
      tooltip: {},
      xAxis: { name: 'λex/nm', type: 'value', axisLabel: { color: '#94a3b8' } },
      yAxis: { name: 'λem/nm', type: 'value', axisLabel: { color: '#94a3b8' } },
      visualMap: {
        min: 0, max, calculable: true, orient: 'vertical', right: 4, top: 'center',
        textStyle: { color: '#94a3b8' },
        inRange: { color: ['#0b1220', '#1e3a8a', '#0891b2', '#22c55e', '#eab308', '#ef4444'] },
      },
      series: [{ type: 'heatmap', data, progressive: 4000 }],
    })
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
    }
  }, [eem, title])

  return <div ref={ref} className="h-full min-h-[320px] w-full rounded-lg border border-edge" />
}
