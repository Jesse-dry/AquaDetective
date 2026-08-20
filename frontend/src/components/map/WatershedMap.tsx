import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useWatershedStore } from '../../store/watershedStore'
import { useAlertStore } from '../../store/alertStore'
import { useUiStore } from '../../store/uiStore'
import { useInvestigationStore } from '../../store/investigationStore'
import { usePlaybackStore } from '../../store/playbackStore'

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
      const properties: Record<string, unknown> = { id: s.id, alert: openStationIds.has(s.id) }
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
            'circle-radius': 7,
            'circle-color': [
              'case',
              ['has', 'heat'],
              ['interpolate', ['linear'], ['get', 'heat'],
                0, '#22c55e', 0.4, '#eab308', 0.75, '#f97316', 1, '#ef4444'],
              ['case', ['get', 'alert'], '#ef4444', '#22c55e'],
            ],
            'circle-stroke-width': 2,
            'circle-stroke-color': '#e2e8f0',
          },
        })
        // 企业:锁定后放大高亮
        map.addLayer({
          id: 'enterprises', type: 'circle', source: 'enterprises',
          paint: {
            'circle-radius': ['case', ['get', 'locked'], 10, 5],
            'circle-color': ['case', ['get', 'locked'], '#ef4444', '#f59e0b'],
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#0b1220',
          },
        })
        map.addLayer({
          id: 'enterprise-labels', type: 'symbol', source: 'enterprises',
          layout: { 'text-field': ['get', 'name'], 'text-size': 11, 'text-offset': [0, 1.2] },
          paint: { 'text-color': '#cbd5e1' },
        })

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
      }
    }

    if (map.isStyleLoaded()) initLayers()
    else map.once('load', initLayers)
    // 数据更新(告警/结论变化)时只更新 source
    return () => {}
  }, [watershed, events, conclusion, selectStation, playbackActive, playbackHeat])

  return <div ref={containerRef} className="h-full w-full rounded-lg border border-edge" />
}
