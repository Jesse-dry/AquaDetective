import { apiGet } from './client'
import type { Watershed, Fingerprint, EemMatrix } from '../types'

// GET /watershed 全流域拓扑(节点/边/断面/企业/指纹),一次拉全
export const getWatershed = () => apiGet<Watershed>('/watershed', 'watershed.json')

// GET /watershed/enterprises/{id}/fingerprint 返回 { enterprise, fingerprint }
export const getEnterpriseFingerprint = (id: string) =>
  apiGet<{ enterprise: unknown; fingerprint: Fingerprint }>(
    `/watershed/enterprises/${id}/fingerprint`,
    'fingerprint.json',
  )

// GET /stations/{id}/eem?event_id= 断面"案发现场"EEM 矩阵(61x71)
export const getStationEem = (stationId: string, eventId?: string) =>
  apiGet<EemMatrix>(
    `/stations/${stationId}/eem${eventId ? `?event_id=${eventId}` : ''}`,
    'eem.json',
  )

// GET /watershed/enterprises/{id}/eem 企业档案 EEM(与现场同网格,并排对比用)
export const getEnterpriseEem = (entId: string) =>
  apiGet<EemMatrix>(`/watershed/enterprises/${entId}/eem`, 'eem_enterprise.json')
