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
  gradual: '渐变恶化',
}

export const etypeLabel = (t: string): string => ETYPE_LABEL[t] ?? t

/** 严重度 → 中文(含语义,普通观众可懂) */
export const SEVERITY_LABEL: Record<string, string> = {
  high: '严重(需立即处置)',
  medium: '中等(持续关注)',
  low: '轻微(留观)',
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
