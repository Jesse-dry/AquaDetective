// 通俗化显示标签:面向普通观众,把内部 id/编码转成中文可读名
// 只影响展示,不改变任何数据

/** evt_001 → 事件1;其他原样返回 */
export function eventLabel(id: string): string {
  const m = id.match(/^evt_?0*(\d+)$/i)
  return m ? `事件${Number(m[1])}` : id
}

/** st_02 → 2号断面;其他原样返回 */
export function stationLabel(id: string): string {
  const m = id.match(/^st_?0*(\d+)$/i)
  return m ? `${Number(m[1])}号断面` : id
}

/** st_02 → "2"(地图标注用,仅数字);其他原样返回 */
export function stationShort(id: string): string {
  const m = id.match(/^st_?0*(\d+)$/i)
  return m ? String(Number(m[1])) : id
}

/** 指标编码 → 中文名 */
export const INDICATOR_LABEL: Record<string, string> = {
  cod: '化学需氧量',
  codmn: '高锰酸盐指数',
  ammonia: '氨氮',
  ammonia_n: '氨氮',
  tp: '总磷',
  tn: '总氮',
  cr6: '六价铬',
  ph: 'pH值',
  do: '溶解氧',
  conductivity: '电导率',
  turbidity: '浊度',
  temperature: '水温',
  chla: '叶绿素α',
  toc: '总有机碳',
}

export const indicatorLabel = (code: string): string => INDICATOR_LABEL[code] ?? code

/** 事件类型 → 中文 */
export const ETYPE_LABEL: Record<string, string> = {
  sudden: '突发泄漏',
  periodic: '夜间偷排',
  gradual: '逐渐恶化',
}

export const etypeLabel = (t: string): string => ETYPE_LABEL[t] ?? t

/** 严重度 → 中文(含语义,普通观众可懂) */
export const SEVERITY_LABEL: Record<string, string> = {
  high: '严重(需立即处置)',
  medium: '中等(持续关注)',
  low: '轻微(等结果)',
}

/** 行业编码 → 中文 */
export const INDUSTRY_LABEL: Record<string, string> = {
  electroplating: '电镀',
  dyeing: '印染',
  paper: '造纸',
  chemical: '化工',
  pharma: '制药',
  food: '食品',
  wwtp: '污水处理厂',
}

export const industryLabel = (code: string): string => INDUSTRY_LABEL[code] ?? code

/** 节点编码 → 中文:m04 → 4号节点;t1_03 → t1支流3号节点 */
export function nodeLabel(id: string): string {
  const m = id.match(/^([a-z]+_?)(\d+)$/i)
  if (!m) return id
  const prefix = m[1].replace(/_$/, '').toUpperCase()
  return `${prefix}节点${Number(m[2])}`
}

/** 推理步骤 step_id → 中文:h1_eem → 假设1·荧光指纹;h2_pattern → 假设2·排放规律 */
const STEP_PHASE_CN: Record<string, string> = {
  eem: '荧光指纹', pollutant: '污染物谱', pattern: '排放规律', strength: '传播强度',
}
export function stepIdLabel(stepId: string): string {
  const m = stepId.match(/^(h\d+)_([a-z]+)$/)
  if (!m) return stepId
  const phase = STEP_PHASE_CN[m[2]] ?? m[2]
  return `假设${m[1].slice(1)}·${phase}`
}

/** 推理 phase → 中文(后端发的"证据校核·eem"等) */
export function phaseLabel(phase: string): string {
  // 形如 "证据校核·eem" → "证据校核·荧光指纹"
  return phase.replace(/·([a-z]+)$/, (_, k) => `·${STEP_PHASE_CN[k] ?? k}`)
}

/** 把文本中的内部 id 替换为中文:st_02→2号断面、m04→4号节点、cr6/cod 等→中文 */
export function humanize(text: string): string {
  if (!text) return text
  let out = text
  // 站点 st_xx / stx
  out = out.replace(/\bst_?0*(\d+)\b/gi, (_, n) => `${Number(n)}号断面`)
  // 节点 m04 / t1_03 / t2_04 等(含字母前缀+数字)
  out = out.replace(/\b([mt]\w*)_?0*(\d+)\b/g, (_, p, n) => `${p.toUpperCase()}节点${Number(n)}`)
  // 指标
  for (const [code, cn] of Object.entries(INDICATOR_LABEL)) {
    out = out.replace(new RegExp(`\\b${code}\\b`, 'g'), cn)
  }
  return out
}
