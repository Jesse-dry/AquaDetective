import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import { getSeries } from '../../api/series'
import { useUiStore } from '../../store/uiStore'
import { usePlaybackStore } from '../../store/playbackStore'
import { indicatorLabel, indicatorUnit } from '../../utils/labels'

// 断面时序曲线。
// 平时:按选中断面 + 选定指标请求全量时序。
// 扩散回放中:切换为"当前事件窗口内该断面的时序"(数据取自回放 store,
// 不再请求),并在时间游标处画竖线随播放移动——否则切换事件时曲线毫无变化。
export function SeriesChart({ stationId }: { stationId: string | null }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const indicator = useUiStore((s) => s.selectedIndicator)
  // 按字段精确订阅:回放每 100ms 更新 heat/cursors,整体订阅会带来无谓重渲染
  const pbActive = usePlaybackStore((s) => s.active)
  const pbEventId = usePlaybackStore((s) => s.eventId)
  const pbSeries = usePlaybackStore((s) => s.series)
  const pbCursorMs = usePlaybackStore((s) => s.cursorMs)
  const pbT0Ms = usePlaybackStore((s) => s.t0Ms)
  const pbT1Ms = usePlaybackStore((s) => s.t1Ms)
  const pbIndicator = usePlaybackStore((s) => s.indicator)

  const pbPoints = stationId ? pbSeries[stationId] : undefined
  const inPlayback = pbActive && !!pbPoints?.length

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
    const chart = chartRef.current
    if (!stationId || !chart) return
    // 纵轴带单位(如 mg/L);轴顶留出名字的空间,故 top 由 24 加到 32
    const yAxisOf = (unit: string) => ({
      type: 'value' as const,
      scale: true,
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#1f2c4a' } },
      name: unit,
      nameLocation: 'end' as const,
      nameGap: 10,
      nameTextStyle: { color: '#94a3b8', fontSize: 10 },
    })
    const base = {
      backgroundColor: 'transparent',
      grid: { left: 48, right: 16, top: 32, bottom: 24 },
      tooltip: { trigger: 'axis' },
    }
    // 回放态画图:横轴锁事件时间窗 + 游标竖线;animation:false 避免
    // "竖线从矮长到高""重放时从右滑到左""末尾突然加速"这类动画错觉
    const drawPlayback = (points: { ts: number; value: number }[], ind: string) => {
      // 取 store 的最新游标:切指标走异步请求,用闭包里的旧值会让橙线先画在偏左
      // 位置、下一 tick 才追上(表现为"切换时橙线突然往左跳")
      const cursorMs = usePlaybackStore.getState().cursorMs
      chart.setOption({
        ...base,
        yAxis: yAxisOf(indicatorUnit(ind)),
        xAxis: {
          type: 'time',
          min: pbT0Ms,
          max: pbT1Ms,
          axisLabel: { color: '#94a3b8' },
          axisLine: { lineStyle: { color: '#1f2c4a' } },
        },
        animation: false,
        series: [{
          name: indicatorLabel(ind),
          type: 'line',
          showSymbol: false,
          animation: false,
          lineStyle: { color: '#38bdf8', width: 1.5 },
          data: points.map((p) => [p.ts, p.value]),
          markLine: {
            silent: true,
            symbol: 'none',
            animation: false,
            label: { show: false },
            lineStyle: { color: '#f59e0b', width: 1.5, type: 'solid' },
            data: [{ xAxis: cursorMs }],
          },
        }],
      }, { notMerge: true })
    }
    if (inPlayback) {
      // 回放中允许切换同一断面的其他指标:
      // 事件自身指标用已加载的回放数据,其他指标按事件时间窗临时请求
      if (indicator === pbIndicator && pbPoints) {
        drawPlayback(pbPoints, pbIndicator)
        return
      }
      getSeries({ station: stationId, indicator, from: pbT0Ms, to: pbT1Ms })
        .then((resp) => drawPlayback(resp.data, indicator))
        .catch(() => {})
      return
    }
    getSeries({ station: stationId, indicator, step: 10 }).then((resp) => {
      chart.setOption({
        ...base,
        yAxis: yAxisOf(indicatorUnit(indicator)),
        xAxis: {
          type: 'time',
          axisLabel: { color: '#94a3b8' },
          axisLine: { lineStyle: { color: '#1f2c4a' } },
        },
        series: [{
          name: indicatorLabel(indicator),
          type: 'line',
          showSymbol: false,
          sampling: 'lttb',
          lineStyle: { color: '#38bdf8', width: 1.5 },
          data: resp.data.map((p) => [p.ts, p.value]),
        }],
      }, { notMerge: true })
    }).catch(() => {})
  }, [stationId, indicator, inPlayback, pbEventId, pbPoints, pbT0Ms, pbT1Ms, pbIndicator])

  // 回放游标移动:只更新竖线位置,不重画曲线
  useEffect(() => {
    if (!inPlayback || !chartRef.current) return
    chartRef.current.setOption({
      series: [{
        markLine: {
          silent: true,
          symbol: 'none',
          animation: false,
          label: { show: false },
          lineStyle: { color: '#f59e0b', width: 1.5, type: 'solid' },
          data: [{ xAxis: pbCursorMs }],
        },
      }],
    })
  }, [pbCursorMs, inPlayback])

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
