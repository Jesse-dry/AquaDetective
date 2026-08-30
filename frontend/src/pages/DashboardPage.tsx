import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useWatershedStore } from '../store/watershedStore'
import { useUiStore } from '../store/uiStore'
import { usePlaybackStore } from '../store/playbackStore'
import { WatershedMap } from '../components/map/WatershedMap'
import { DispersionLayer } from '../components/map/DispersionLayer'
import { AlertList } from '../components/alert/AlertList'
import { ReasoningPanel } from '../components/reasoning/ReasoningPanel'
import { SeriesChart } from '../components/charts/SeriesChart'
import { ScenarioBar } from '../components/demo/ScenarioBar'
import { stationLabel, indicatorLabel } from '../utils/labels'

// 大屏主页:左告警 / 中地图 / 右推理 / 底部曲线
export function DashboardPage() {
  const loadWatershed = useWatershedStore((s) => s.load)
  const watershed = useWatershedStore((s) => s.data)
  const selectedStationId = useUiStore((s) => s.selectedStationId)
  const selectedIndicator = useUiStore((s) => s.selectedIndicator)
  const setIndicator = useUiStore((s) => s.setIndicator)
  const toggleTypewriter = useUiStore((s) => s.toggleTypewriter)

  useEffect(() => {
    loadWatershed()
  }, [loadWatershed])

  // 选中断面的可监测指标列表
  const indicators =
    watershed?.stations.find((s) => s.id === selectedStationId)?.indicators ?? []

  return (
    <div className="flex h-screen flex-col bg-ink text-slate-200">
      <header className="flex items-center justify-between border-b border-edge px-4 py-2">
        <h1 className="text-lg font-bold">
          <span className="text-accent">AquaDetective</span> · 水质预警溯源智能体
        </h1>
        <div className="flex items-center gap-3">
          <Link to="/replay" className="text-xs text-slate-400 hover:text-accent">📼 回放</Link>
          <Link to="/benchmark" className="text-xs text-slate-400 hover:text-accent">📊 对标</Link>
          <button
            onClick={() => {
              toggleTypewriter()
              // 扩散回放正在播时一并跳到终点,一键结束所有演示动画
              const pb = usePlaybackStore.getState()
              if (pb.active && pb.playing) pb.skipToEnd()
            }}
            className="rounded bg-edge px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
            title="关闭打字机动画;扩散回放播放中则跳到终点"
          >
            ⏩ 跳过动画
          </button>
          <ScenarioBar />
        </div>
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-[280px_1fr_380px] gap-2 p-2">
        <aside className="min-h-0 rounded-lg border border-edge bg-ink">
          <AlertList />
        </aside>
        <section className="relative min-h-0">
          <WatershedMap />
          <DispersionLayer />
        </section>
        <aside className="min-h-0 rounded-lg border border-edge bg-ink">
          <ReasoningPanel />
        </aside>
      </main>

      <footer className="flex h-44 flex-col border-t border-edge p-2">
        {selectedStationId && indicators.length > 0 && (
          <div className="mb-1 flex items-center gap-1.5 px-1">
            <span className="text-xs text-slate-500">{stationLabel(selectedStationId)}</span>
            {indicators.map((ind) => (
              <button
                key={ind}
                onClick={() => setIndicator(ind)}
                className={`rounded px-2 py-0.5 text-xs ${
                  ind === selectedIndicator
                    ? 'bg-accent font-semibold text-ink'
                    : 'bg-edge text-slate-300 hover:bg-slate-600'
                }`}
              >
                {indicatorLabel(ind)}
              </button>
            ))}
          </div>
        )}
        <div className="min-h-0 flex-1">
          <SeriesChart stationId={selectedStationId} />
        </div>
      </footer>
    </div>
  )
}
