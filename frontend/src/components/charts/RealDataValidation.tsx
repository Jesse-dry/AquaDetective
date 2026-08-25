import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'

// 真实数据算法验证:太湖 105 断面标准化数据上的异常检测交叉验证
// 数据为静态蒸馏 JSON(public/data),与后端引擎验证报告同源
interface MethodStat {
  runs: number
  total_detections: number
  avg_detection_rate: number
  consistency_checks: number
  consistency_pass: number
  consistency_pass_rate: number | null
}

interface Summary {
  dataset: string
  method_note: Record<string, string>
  conclusion: Record<string, string>
  per_method: Record<string, MethodStat>
}

const METHOD_ORDER = ['threesigma', 'cusum', 'ewma', 'seasonal']
const RECOMMENDED = new Set(['threesigma', 'cusum'])

export function RealDataValidation() {
  const [data, setData] = useState<Summary | null>(null)
  const chartRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch('/data/anomaly_validation_summary.json')
      .then((r) => r.json())
      .then(setData)
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!chartRef.current || !data) return
    const chart = echarts.init(chartRef.current)
    const methods = METHOD_ORDER.filter((m) => data.per_method[m])
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 52, right: 52, top: 40, bottom: 28 },
      legend: { textStyle: { color: '#94a3b8' }, top: 0 },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v: number) => `${v}%`,
      },
      xAxis: {
        type: 'category',
        data: methods.map((m) => data.method_note[m] ?? m),
        axisLabel: { color: '#94a3b8' },
        axisLine: { lineStyle: { color: '#1f2c4a' } },
      },
      yAxis: [
        {
          type: 'value', name: '检出率', max: 25,
          axisLabel: { color: '#94a3b8', formatter: '{value}%' },
          splitLine: { lineStyle: { color: '#1f2c4a' } },
        },
        {
          type: 'value', name: '一致性通过率', max: 100,
          axisLabel: { color: '#94a3b8', formatter: '{value}%' },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: '平均检出率(越低越克制)',
          type: 'bar',
          data: methods.map((m) => +(data.per_method[m].avg_detection_rate * 100).toFixed(2)),
          itemStyle: { color: '#38bdf8' },
        },
        {
          name: '类别一致性通过率(越高越好)',
          type: 'bar',
          yAxisIndex: 1,
          data: methods.map((m) =>
            data.per_method[m].consistency_pass_rate !== null
              ? +(data.per_method[m].consistency_pass_rate! * 100).toFixed(1)
              : null,
          ),
          itemStyle: { color: '#22c55e' },
        },
      ],
    })
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
    }
  }, [data])

  if (!data) return null

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-slate-300">
        ② 真实数据算法验证(太湖国控断面)
      </h2>
      <p className="mb-2 text-xs text-slate-500">{data.dataset} · 验证方法:检出点的官方水质类别(Ⅳ/Ⅴ/劣Ⅴ)富集度 vs 断面基线</p>
      <div className="rounded-lg border border-edge bg-panel p-3">
        <div ref={chartRef} className="h-64 w-full" />
        <table className="mt-2 w-full text-xs">
          <thead className="text-slate-400">
            <tr>
              <th className="px-2 py-1 text-left">方法</th>
              <th className="px-2 py-1 text-left">平均检出率</th>
              <th className="px-2 py-1 text-left">一致性通过</th>
              <th className="px-2 py-1 text-left">结论</th>
            </tr>
          </thead>
          <tbody>
            {METHOD_ORDER.filter((m) => data.per_method[m]).map((m) => {
              const s = data.per_method[m]
              const ok = RECOMMENDED.has(m)
              return (
                <tr key={m} className="border-t border-edge">
                  <td className="px-2 py-1">
                    {ok ? '✅' : '⚠️'} {data.method_note[m] ?? m}
                  </td>
                  <td className="px-2 py-1 tabular-nums">
                    {(s.avg_detection_rate * 100).toFixed(2)}%
                  </td>
                  <td className="px-2 py-1 tabular-nums">
                    {s.consistency_pass}/{s.consistency_checks}
                    {s.consistency_pass_rate !== null &&
                      ` (${Math.round(s.consistency_pass_rate * 100)}%)`}
                  </td>
                  <td className="px-2 py-1 text-slate-400">{data.conclusion[m]}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
