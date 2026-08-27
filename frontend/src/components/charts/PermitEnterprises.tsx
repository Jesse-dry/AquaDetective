import { useEffect, useState } from 'react'

// 真实排口级数据资产:太湖流域 37 家企业许可证解析结果
// 数据为静态蒸馏 JSON(public/data/permit_enterprises.json),来源许可证平台原始粘贴解析
interface Enterprise {
  name: string
  credit_code: string
  has_data: boolean
  permit_status: string
  primary: string
  fingerprint: Record<string, number | null>
  major_count: number
}

interface PermitData {
  title: string
  dataset: string
  enterprises: Enterprise[]
  summary: { total: number; with_data: number; revoked: number; bankrupt: number }
  pollutant_legend: Record<string, string>
}

export function PermitEnterprises() {
  const [data, setData] = useState<PermitData | null>(null)

  useEffect(() => {
    fetch('/data/permit_enterprises.json')
      .then((r) => r.json())
      .then(setData)
      .catch(() => {})
  }, [])

  if (!data) return null
  const s = data.summary
  const legend: Record<string, string> = data.pollutant_legend

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-slate-300">{data.title}</h2>
      <p className="mb-3 text-xs text-slate-500">
        {data.dataset} · {s.total} 家企业({s.with_data} 家有许可数据,{s.revoked} 家许可注销/届满,{s.bankrupt} 家破产)
      </p>

      <div className="rounded-lg border border-edge bg-panel p-3">
        <div className="mb-2 flex flex-wrap gap-3 text-[11px] text-slate-400">
          <span className="text-slate-500">污染物图例:</span>
          {Object.entries(legend).map(([code, name]) => (
            <span key={code}>
              <span className="text-sky-300">{code}</span>={name}
            </span>
          ))}
        </div>

        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-panel text-slate-400">
              <tr>
                <th className="px-2 py-1 text-left">企业</th>
                <th className="px-2 py-1 text-left">许可状态</th>
                <th className="px-2 py-1 text-left">首要污染物</th>
                <th className="px-2 py-1 text-left">指纹向量(年排放量 t/a)</th>
              </tr>
            </thead>
            <tbody>
              {data.enterprises.map((e) => {
                const revoked = !e.has_data && (e.permit_status.includes('注销') || e.permit_status.includes('届满') || e.permit_status.includes('破产'))
                return (
                  <tr key={e.credit_code + e.name} className="border-t border-edge">
                    <td className="px-2 py-1">
                      <span className={e.has_data ? 'text-slate-200' : 'text-slate-500'}>
                        {e.name.length > 22 ? e.name.slice(0, 22) + '…' : e.name}
                      </span>
                    </td>
                    <td className="px-2 py-1">
                      <span className={revoked ? 'text-rose-400' : e.has_data ? 'text-emerald-400' : 'text-slate-500'}>
                        {revoked ? '许可注销/失效' : e.has_data ? '在业(有许可)' : '无数据'}
                      </span>
                    </td>
                    <td className="px-2 py-1 text-sky-300">{e.primary || '—'}</td>
                    <td className="px-2 py-1 text-slate-400 tabular-nums">
                      {e.has_data && Object.keys(e.fingerprint).length > 0 ? (
                        Object.entries(e.fingerprint).map(([k, v]) => (
                          <span key={k} className="mr-2">
                            <span className="text-sky-300">{k}</span>:
                            {v === null ? <span className="text-slate-600">—</span> : v}
                          </span>
                        ))
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-slate-600">
        数据来源:全国排污许可证管理信息平台(permit.mee.gov.cn)原始粘贴解析。
        主要污染物 = 主要排放口合计表中年排放量限值非"/"的污染物;首要污染物 = 年排放量(t/a)最大者。
        指纹向量已接入溯源系统(backend/app/data/fingerprint_lib.py),供 match_pollutants 做指纹比对。
        许可注销/破产企业无指纹数据,溯源时用同行业真实指纹做代理并如实标注。
      </p>
    </section>
  )
}
