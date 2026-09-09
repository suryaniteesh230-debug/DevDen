import { describe, expect, it } from 'vitest'
import type { ProcedureSummary } from './api'
import { routeCitizenRequest } from './conversation'

const aadhaar: ProcedureSummary = { service_id: 'uidai-aadhaar-address-update', title: 'Aadhaar address', short_description: 'Verified Aadhaar guidance', intent_phrases: ['change Aadhaar address'], category: 'identity', category_label: 'Identity', trust_state: 'current', attention_required: false }
const pension: ProcedureSummary = { service_id: 'kerala-ign-oap', title: 'Kerala pension', short_description: 'Verified pension guidance', intent_phrases: ['Kerala old age pension'], category: 'pension', category_label: 'Pension', trust_state: 'current', attention_required: false }

describe('conversation routing', () => {
  it('clarifies an unqualified address change inside pension using only verified catalogue entries', () => {
    const route = routeCitizenRequest('I need to change the address', [aadhaar, pension], pension.service_id)
    expect(route).toMatchObject({ kind: 'result', reply: 'address-clarification', result: { kind: 'ambiguous' } })
    if (route.kind === 'result' && route.result.kind === 'ambiguous') expect(route.result.candidates.map(item => item.procedure.service_id)).toEqual([aadhaar.service_id, pension.service_id])
  })

  it('does not invent a pension-record address procedure', () => {
    expect(routeCitizenRequest('change my pension address', [aadhaar, pension], pension.service_id)).toMatchObject({ kind: 'result', reply: 'pension-address-unsupported', result: { kind: 'none' } })
  })

  it('retains PII blocking and verified Aadhaar routing', () => {
    expect(routeCitizenRequest('1234 5678 9012', [aadhaar, pension], null)).toEqual({ kind: 'pii' })
    expect(routeCitizenRequest('change Aadhaar address', [aadhaar, pension], pension.service_id)).toMatchObject({ kind: 'result', reply: 'matched', result: { kind: 'confident', candidate: { procedure: { service_id: aadhaar.service_id } } } })
  })

  it('fails closed for an unsupported Aadhaar name change', () => {
    expect(routeCitizenRequest('I need to change my name in Aadhaar', [aadhaar, pension], null)).toMatchObject({ kind: 'result', reply: 'unsupported', result: { kind: 'none' } })
  })
})
