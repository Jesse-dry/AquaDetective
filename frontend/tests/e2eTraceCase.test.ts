import { describe, expect, it } from 'vitest'
import traceCase from '../public/data/e2e_trace_case.json'

describe('real-data trace candidate contract', () => {
  it('presents upstream enterprises as unverified candidates', () => {
    expect(traceCase).not.toHaveProperty('matched_enterprise')
    expect(traceCase).toHaveProperty('primary_candidate')
    expect(traceCase.evidence_status).toBe('candidate_unverified')
    expect(traceCase.causal_confirmed).toBe(false)
    expect(traceCase.primary_candidate.causal_confirmed).toBe(false)
    expect(traceCase.primary_candidate.travel_time.causal_evidence).toBe(false)
    expect(traceCase.primary_candidate_tie_count).toBeGreaterThan(1)
    expect(traceCase.limitations.length).toBeGreaterThan(0)
    expect(traceCase.limitations.join('')).toContain('同分候选')
  })
})
