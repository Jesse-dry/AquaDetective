import { useEffect } from 'react'
import { useWatershedStore } from '../store/watershedStore'
import { useUiStore } from '../store/uiStore'
import { WatershedMap } from '../components/map/WatershedMap'
import { DispersionLayer } from '../components/map/DispersionLayer'
import { AlertList } from '../components/alert/AlertList'
import { ReasoningPanel } from '../components/reasoning/ReasoningPanel'
import { SeriesChart } from '../components/charts/SeriesChart'
import { ScenarioBar } from '../components/demo/ScenarioBar'

// 大屏主页:左告警 / 中地图 / 右推理 / 底部曲线
export function DashboardPage() {
  const loadWatershed = useWatershedStore((s) => s.load)
  const selectedStationId = useUiStore((s) => s.selectedStationId)
  const toggleTypewriter = useUiStore((s) => s.toggleTypewriter)

  useEffect(() => {
    loadWatershed()
  }, [loadWatershed])

  return (
    <div className="flex h-screen flex-col bg-ink text-slate-200">
      <header className="flex items-center justify-between border-b border-edge px-4 py-2">
        <h1 className="text-lg font-bold">
          <span className="text-accent">AquaDetective</span> · 水质预警溯源智能体
        </h1>
        <div className="flex items-center gap-3">
          <button
            onClick={toggleTypewriter}
            className="rounded bg-edge px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
            title="切换打字机动画"
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

      <footer className="h-44 border-t border-edge p-2">
        <SeriesChart stationId={selectedStationId} />
      </footer>
    </div>
  )
}
