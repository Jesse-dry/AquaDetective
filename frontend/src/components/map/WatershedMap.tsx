import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useWatershedStore } from '../../store/watershedStore'
import { useAlertStore } from '../../store/alertStore'
import { useUiStore } from '../../store/uiStore'
import { useInvestigationStore } from '../../store/investigationStore'
import { usePlaybackStore } from '../../store/playbackStore'
import { stationShort } from '../../utils/labels'

interface OverlayItem {
  key: string
  x: number // 屏幕像素
  y: number
  text: string
  color: string
  offset: [number, number] // 相对锚点的像素偏移
}

// 流域底图:空白深色样式 + GeoJSON 绘制节点/边/断面/企业
// 坐标直接使用契约 (x, y) 平面坐标,fitBounds 自适应
const EMPTY_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': '#0b1220' } },
  ],
}

export function WatershedMap() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const watershed = useWatershedStore((s) => s.data)
  const events = useAlertStore((s) => s.events)
  const conclusion = useInvestigationStore((s) => s.conclusion)
  const selectStation = useUiStore((s) => s.selectStation)
  const playbackActive = usePlaybackStore((s) => s.active)
  const playbackHeat = usePlaybackStore((s) => s.heat)
  const [overlays, setOverlays] = useState<OverlayItem[]>([])
  // 企业名上次选中的偏移(滞回):缩放平移时优先沿用旧位置,减少乱跳
  const lastOffsets = useRef<Map<string, [number, number]>>(new Map())

  // 把地图坐标转屏幕像素,生成 overlay 列表(企业名+断面序号)
  // 企业名用碰撞布局:依次尝试候选偏移,与已放置标签/圆点的包围盒不相交才落位
  const updateOverlays = () => {
    const map = mapRef.current
    if (!map || !watershed) return
    const items: OverlayItem[] = []
    interface Box { l: number; r: number; t: number; b: number }
    interface Pt { x: number; y: number }
    const hit = (a: Box, b: Box) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b
    // 标签包围盒:中文按 10px/字估宽,行高 12
    const labelBox = (cx: number, top: number, text: string): Box => {
      const w = text.length * 10 + 4
      return { l: cx - w / 2, r: cx + w / 2, t: top, b: top + 12 }
    }
    const dotBox = (p: Pt, r: number): Box => ({ l: p.x - r, r: p.x + r, t: p.y - r, b: p.y + r })

    const stationPts: Array<{ p: Pt; id: string }> = []
    for (const s of watershed.stations) {
      const n = watershed.nodes.find((nd) => nd.id === s.node_id)
      if (!n) continue
      stationPts.push({ p: map.project([n.x, n.y]), id: s.id })
    }
    const entNodes = watershed.enterprises
      .map((ent) => {
        const n = watershed.nodes.find((nd) => nd.id === ent.node_id)
        return n ? { ent, n } : null
      })
      .filter((x): x is { ent: typeof watershed.enterprises[0]; n: typeof watershed.nodes[0] } => x !== null)
      .map((e) => ({ ent: e.ent, p: map.project([e.n.x, e.n.y]) as Pt }))

    // 障碍:断面大圆(半径 18 留边距)+ 企业小圆,避免文字盖住圆点
    const obstacles: Box[] = [
      ...stationPts.map(({ p }) => dotBox(p, 16)),
      ...entNodes.map(({ p }) => dotBox(p, 10)),
    ]
    // 断面序号固定放圆点上方(现状样式),其包围盒参与后续碰撞
    const placed: Box[] = []
    for (const { p, id } of stationPts) {
      items.push({
        key: `st-${id}`, x: p.x, y: p.y, text: stationShort(id),
        color: '#e2e8f0', offset: [0, -18],
      })
      placed.push(labelBox(p.x, p.y - 18, stationShort(id)))
    }
    // 企业名候选偏移:先近后远、先上下后斜向
    const CANDIDATES: ReadonlyArray<readonly [number, number]> = [
      [0, -22], [0, 22], [12, -16], [12, 16], [-12, -16], [-12, 16],
      [0, -34], [0, 34], [18, -27], [18, 27], [-18, -27], [-18, 27],
      [24, 0], [-24, 0],
    ]
    // 名字长的先放(更难找到空位)
    const sorted = [...entNodes].sort((a, b) => b.ent.name.length - a.ent.name.length)
    for (const e of sorted) {
      // 滞回:上次的位置优先,只要当前无碰撞就沿用,避免缩放时标签来回跳
      const prev = lastOffsets.current.get(e.ent.id)
      const cands: Array<readonly [number, number]> = []
      if (prev) cands.push(prev)
      for (const c of CANDIDATES) {
        if (!prev || c[0] !== prev[0] || c[1] !== prev[1]) cands.push(c)
      }
      let chosen: readonly [number, number] = prev ?? CANDIDATES[0]
      for (const c of cands) {
        const box = labelBox(e.p.x + c[0], e.p.y + c[1], e.ent.name)
        if (![...placed, ...obstacles].some((o) => hit(box, o))) {
          chosen = c
          break
        }
      }
      lastOffsets.current.set(e.ent.id, [chosen[0], chosen[1]])
      placed.push(labelBox(e.p.x + chosen[0], e.p.y + chosen[1], e.ent.name))
      items.push({
        key: `ent-${e.ent.id}`, x: e.p.x, y: e.p.y, text: e.ent.name,
        color: '#fcd34d', offset: [chosen[0], chosen[1]],
      })
    }
    setOverlays(items)
  }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: EMPTY_STYLE,
      center: [0, 0],
      zoom: 8,
      attributionControl: false,
    })
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !watershed) return

    const nodeById = new Map(watershed.nodes.map((n) => [n.id, n]))
    const openStationIds = new Set(events.filter((e) => e.status !== 'resolved').map((e) => e.station_id))

    const edgeFeatures = watershed.edges.flatMap((e) => {
      const a = nodeById.get(e.from_node)
      const b = nodeById.get(e.to_node)
      if (!a || !b) return []
      return [{
        type: 'Feature' as const,
        geometry: { type: 'LineString' as const, coordinates: [[a.x, a.y], [b.x, b.y]] },
        properties: {},
      }]
    })

    const stationNodeIds = new Set(watershed.stations.map((s) => s.node_id))
    const stationFeatures = watershed.stations.flatMap((s) => {
      const n = nodeById.get(s.node_id)
      if (!n) return []
      // 扩散回放中携带热力值(触发 heat 着色),平时不带
      const properties: Record<string, unknown> = {
        id: s.id,
        num: stationShort(s.id), // 图上仅标注数字序号
        alert: openStationIds.has(s.id),
      }
      if (playbackActive) properties.heat = playbackHeat[s.id] ?? 0
      return [{
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [n.x, n.y] },
        properties,
      }]
    })

    const nodeFeatures = watershed.nodes
      .filter((n) => !stationNodeIds.has(n.id))
      .map((n) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [n.x, n.y] },
        properties: { id: n.id, name: n.name, kind: n.kind },
      }))

    const entFeatures = watershed.enterprises.flatMap((ent) => {
      const n = nodeById.get(ent.node_id)
      if (!n) return []
      return [{
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [n.x, n.y] },
        properties: {
          id: ent.id,
          name: ent.name,
          locked: conclusion?.source_id === ent.id,
        },
      }]
    })

    const setData = (id: string, features: unknown[]) => {
      const src = map.getSource(id) as maplibregl.GeoJSONSource | undefined
      const fc = { type: 'FeatureCollection' as const, features: features as never[] }
      if (src) src.setData(fc)
      else map.addSource(id, { type: 'geojson', data: fc })
    }

    const initLayers = () => {
      setData('edges', edgeFeatures)
      setData('nodes', nodeFeatures)
      setData('stations', stationFeatures)
      setData('enterprises', entFeatures)

      if (!map.getLayer('edges')) {
        map.addLayer({
          id: 'edges', type: 'line', source: 'edges',
          paint: { 'line-color': '#1f4e79', 'line-width': 3 },
        })
        map.addLayer({
          id: 'nodes', type: 'circle', source: 'nodes',
          paint: { 'circle-radius': 3, 'circle-color': '#334155' },
        })
        // 断面着色:回放模式按浓度热力(绿→黄→红),平时按告警状态(绿/红)
        map.addLayer({
          id: 'stations', type: 'circle', source: 'stations',
          paint: {
            'circle-radius': 14,
            'circle-color': [
              'case',
              ['has', 'heat'],
              ['interpolate', ['linear'], ['get', 'heat'],
                0, '#14532d', 0.1, '#22c55e', 0.25, '#84cc16', 0.4, '#eab308',
                0.6, '#f97316', 0.8, '#ef4444', 1, '#dc2626'],
              ['case', ['get', 'alert'], '#ef4444', '#22c55e'],
            ],
            'circle-stroke-width': 2,
            'circle-stroke-color': '#e2e8f0',
            'circle-opacity': 1,
          },
        })
        // 断面序号标注(仅数字,需 glyphs 字形源支持)
        // 暂注释:无可靠公共 glyphs 源时,数字标注会报错;用 HTML overlay 替代
        // map.addLayer({
        //   id: 'station-labels', type: 'symbol', source: 'stations',
        //   layout: { 'text-field': ['get', 'num'], 'text-size': 10, 'text-offset': [0, -1.3], 'text-font': ['Open Sans Regular'] },
        //   paint: { 'text-color': '#e2e8f0', 'text-halo-color': '#0b1220', 'text-halo-width': 1.5 },
        // })
        // 企业:锁定后放大高亮;回放时隐藏(避免黄色小圈干扰断面热力)
        map.addLayer({
          id: 'enterprises', type: 'circle', source: 'enterprises',
          paint: {
            'circle-radius': ['case', ['get', 'locked'], 10, 5],
            'circle-color': ['case', ['get', 'locked'], '#ef4444', '#f59e0b'],
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#0b1220',
          },
        })
        // 企业名标注(需 glyphs;暂用 HTML overlay 替代避免无 glyphs 报错)
        // map.addLayer({
        //   id: 'enterprise-labels', type: 'symbol', source: 'enterprises',
        //   layout: { 'text-field': ['get', 'name'], 'text-size': 12, 'text-offset': [0, 1.4] },
        //   paint: { 'text-color': '#fcd34d', 'text-halo-color': '#0b1220', 'text-halo-width': 2 },
        // })

        map.on('click', 'stations', (e) => {
          const id = e.features?.[0]?.properties?.id
          if (id) selectStation(String(id))
        })
        map.on('mouseenter', 'stations', () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', 'stations', () => { map.getCanvas().style.cursor = '' })

        // 自适应视野
        const xs = watershed.nodes.map((n) => n.x)
        const ys = watershed.nodes.map((n) => n.y)
        map.fitBounds(
          [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]],
          { padding: 60, duration: 0 },
        )
        // HTML overlay 标注(企业名+断面序号),随平移/缩放更新
        updateOverlays()
        map.on('move', updateOverlays)
        map.on('zoom', updateOverlays)
      }
    }

    if (map.isStyleLoaded()) initLayers()
    else map.once('load', initLayers)
    // 数据更新(告警/结论变化)时只更新 source
    return () => {}
  }, [watershed, events, conclusion, selectStation, playbackActive, playbackHeat])

  // overlay 依赖 watershed 与 playback(回放时企业 overlay 隐藏),变化时刷新
  useEffect(() => {
    updateOverlays()
    const map = mapRef.current
    if (!map) return
    map.on('move', updateOverlays)
    map.on('zoom', updateOverlays)
    return () => {
      map.off('move', updateOverlays)
      map.off('zoom', updateOverlays)
    }
  }, [watershed, playbackActive])

  return (
    <div className="relative h-full w-full rounded-lg border border-edge">
      <div ref={containerRef} className="h-full w-full" />
      {/* HTML overlay 层:企业名+断面序号,不依赖 MapLibre glyphs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        {overlays
          .filter((o) => playbackActive ? !o.key.startsWith('ent-') : true)
          .map((o) => (
            <span
              key={o.key}
              className={`absolute select-none whitespace-nowrap leading-none ${
                o.key.startsWith('st-')
                  ? 'text-[13px] font-bold tracking-wider'
                  : 'text-[11px] font-medium tracking-wide'
              }`}
              style={{
                left: o.x + o.offset[0],
                top: o.y + o.offset[1],
                color: o.color,
                textShadow: o.key.startsWith('st-')
                  ? '0 0 4px #0b1220, 0 1px 3px #0b1220, 0 0 8px rgba(11,18,32,.9)'
                  : '0 0 2px #0b1220, 0 1px 2px #0b1220, 0 0 6px rgba(11,18,32,.8)',
                transform: 'translateX(-50%)',
              }}
            >
              {o.text}
            </span>
          ))}
      </div>
    </div>
  )
}
