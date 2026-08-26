import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'

// 真实数据端到端溯源演示:真实断面异常 → 河网上溯 → 命中吸附企业
// 数据为静态蒸馏 JSON(public/data/e2e_trace_case.json),数值来自后端确定性引擎,前端零计算
interface SeriesPoint { dt: string; v: number | null; cls: string }
interface E2EData {
  title: string
  dataset: string
  station: { id: string; name: string; lon: number; lat: number }
  matched_enterprise: {
    name: string; industry: string; city: string; lon: number; lat: number
    dist_km: number; travel_h: number
  }
  anomaly: {
    indicator: string; event_dt: string; peak: number; baseline: number
    multiple: string; class_shift: string; method: string
    severity: string; shape: string
  }
  upstream_path: { hid: number; dist_km: number; travel_h: number }[]
  series: SeriesPoint[]
}

export function E2ETraceCase() {
  const [data, setData] = useState<E2EData | null>(null)
  const chartRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch('/data/e2e_trace_case.json')
      .then((r) => r.json())
      .then(setData)
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!chartRef.current || !data) return
    const chart = echarts.init(chartRef.current)
    const xs = data.series.map((s) => s.dt)
    // 事件点索引(峰值 0.698 附近)
    const peakIdx = data.series.reduce(
      (mi, s, i) => (s.v != null && (data.series[mi]?.v ?? -1) < s.v ? i : mi),
      0,
    )
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 48, right: 24, top: 30, bottom: 40 },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: xs,
        axisLabel: { color: '#94a3b8', fontSize: 10, rotate: 30 },
        axisLine: { lineStyle: { color: '#1f2c4a' } },
      },
      yAxis: {
        type: 'value', name: '氨氮 mg/L', nameTextStyle: { color: '#94a3b8' },
        axisLabel: { color: '#94a3b8' },
        splitLine: { lineStyle: { color: '#1f2c4a' } },
      },
      series: [
        {
          name: '氨氮',
          type: 'line',
          smooth: true,
          symbol: 'none',
          data: data.series.map((s) => s.v),
          lineStyle: { color: '#38bdf8', width: 2 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(56,189,248,0.35)' },
              { offset: 1, color: 'rgba(56,189,248,0.02)' },
            ]),
          },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [
              {
                yAxis: data.anomaly.baseline,
                lineStyle: { color: '#64748b', type: 'dashed' },
                label: { formatter: '基线', color: '#94a3b8', fontSize: 10 },
              },
            ],
          },
          markPoint: {
            symbol: 'pin',
            symbolSize: 44,
            data: [
              {
                coord: [xs[peakIdx], data.anomaly.peak],
                itemStyle: { color: '#f59e0b' },
                label: { formatter: '异常峰', color: '#fff', fontSize: 10 },
              },
            ],
          },
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
  const a = data.anomaly
  const e = data.matched_enterprise

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-slate-300">{data.title}</h2>
      <p className="mb-3 text-xs text-slate-500">
        {data.dataset} · 异常检测 → 河网拓扑上溯 → 命中上游企业,全链路走确定性引擎,真实断面数据
      </p>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {/* 左:异常时序曲线 */}
        <div className="rounded-lg border border-edge bg-panel p-3 lg:col-span-2">
          <div className="mb-1 flex items-baseline justify-between">
            <span className="text-xs text-slate-400">
              {a.indicator}时序 · 峰值 {a.peak} mg/L · {a.multiple}
            </span>
            <span className="text-xs text-amber-400">水质 {a.class_shift}</span>
          </div>
          <div ref={chartRef} className="h-56 w-full" />
          <p className="mt-1 text-xs text-slate-500">
            检测方法:{a.method} · 形态:{a.shape}
          </p>
        </div>

        {/* 右:命中企业卡片 + 上溯路径 */}
        <div className="rounded-lg border border-edge bg-panel p-3">
          <div className="mb-2 text-xs font-semibold text-emerald-400">溯源命中</div>
          <div className="space-y-1 text-xs text-slate-300">
            <div className="font-medium text-slate-200">{e.name}</div>
            <div>行业:{e.industry}</div>
            <div>所在地:{e.city}</div>
            <div>
              河网距离:<span className="tabular-nums text-sky-300">{e.dist_km} km</span>
            </div>
            <div>
              传播时间:<span className="tabular-nums text-sky-300">{e.travel_h} h</span>
            </div>
            <div>
              严重度:<span className="text-amber-400">{a.severity}</span>
            </div>
          </div>
          <div className="mt-3 border-t border-edge pt-2">
            <div className="mb-1 text-[11px] text-slate-500">上溯河段(72h 窗)</div>
            <ol className="space-y-0.5 text-[11px] text-slate-400">
              {data.upstream_path.map((u, i) => (
                <li key={u.hid} className="flex justify-between">
                  <span>河段 #{u.hid}</span>
                  <span className="tabular-nums">
                    {u.dist_km} km / {u.travel_h} h
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-slate-600">
        说明:断面坐标来自百度地图模糊查询(GCJ-02→WGS84 转换,误差米级),吸附到 HydroRIVERS
        太湖河网;异常检测与拓扑上溯均为确定性纯函数。本演示为真实断面数据上的算法验证,
        非真实污染事件认定。
      </p>
    </section>
  )
}
