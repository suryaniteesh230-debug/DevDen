import { describe, expect, it, vi } from 'vitest'
import model from '../../intent-model/artifacts/intent-model.v1.json'
import type { ProcedureSummary } from './api'
import { classifyLocalIntent, EXPECTED_DATASET_DIGEST, EXPECTED_MODEL_DIGEST, validateLocalIntentModel, type LocalIntentResult } from './localIntent'
import { classifyServiceQuery, matchProceduresHybrid } from './matcher'
import { normalizeIntentText } from './normalization'

const aadhaar: ProcedureSummary = { service_id: 'uidai-aadhaar-address-update', title: 'Aadhaar address', short_description: 'Address help', intent_phrases: ['update Aadhaar address'], category: 'identity', category_label: 'Identity', trust_state: 'current', attention_required: false }
const pension: ProcedureSummary = { service_id: 'kerala-ign-oap', title: 'Kerala pension', short_description: 'Pension help', intent_phrases: ['old age pension Kerala'], category: 'pension', category_label: 'Pension', trust_state: 'current', attention_required: false }
const confident = (label: 'aadhaar_address_update' | 'kerala_old_age_pension' | 'unsupported_other'): LocalIntentResult => ({ kind: 'confident', label, confidence: 0.99, margin: 0.98 })

describe('trained local intent classifier', () => {
  it('validates the versioned artifact contract and normalization parity vectors', () => {
    expect(EXPECTED_MODEL_DIGEST).toMatch(/^[a-f0-9]{64}$/)
    expect(model.dataset_digest).toBe(EXPECTED_DATASET_DIGEST)
    expect(validateLocalIntentModel(model)).not.toBeNull()
    for (const vector of model.normalization_vectors) expect(normalizeIntentText(vector.input)).toBe(vector.output)
  })

  it.each([
    ['en', 'please update the address on Aadhaar', 'aadhaar_address_update'],
    ['hi', 'मुझे आधार का पता बदलना है', 'aadhaar_address_update'],
    ['ml', 'ആധാറിലെ വിലാസം മാറ്റണം', 'aadhaar_address_update'],
    ['en', 'Kerala old age pension application', 'kerala_old_age_pension'],
    ['hi', 'केरल वृद्धावस्था पेंशन चाहिए', 'kerala_old_age_pension'],
    ['ml', 'കേരള വയോജന പെൻഷന് അപേക്ഷിക്കണം', 'kerala_old_age_pension'],
    ['en', 'renew my driving licence', 'unsupported_other'],
    ['hi', 'जन्म प्रमाण पत्र बनवाना है', 'unsupported_other'],
    ['ml', 'റേഷൻ കാർഡ് അപേക്ഷ സഹായം', 'unsupported_other'],
  ])('classifies %s examples across all three labels', (_locale, text, label) => {
    expect(classifyLocalIntent(text)).toMatchObject({ kind: 'confident', label })
  })

  it('abstains on insufficient evidence and bounded oversized input', () => {
    expect(classifyLocalIntent('??')).toMatchObject({ kind: 'abstain' })
    expect(classifyLocalIntent('x'.repeat(501))).toEqual({ kind: 'abstain', confidence: 0, margin: 0 })
  })

  it('fails closed on artifact schema, digest, thresholds, and numeric corruption', () => {
    expect(classifyLocalIntent('update Aadhaar address', { ...model, schema_version: 2 })).toEqual({ kind: 'unavailable' })
    expect(classifyLocalIntent('update Aadhaar address', { ...model, dataset_digest: '0'.repeat(64) })).toEqual({ kind: 'unavailable' })
    expect(classifyLocalIntent('update Aadhaar address', { ...model, thresholds: { ...model.thresholds, minimum_margin: Number.NaN } })).toEqual({ kind: 'unavailable' })
  })

  it('implements agreement, ML-only, deterministic-only, disagreement, unsupported, and fallback policy', () => {
    expect(matchProceduresHybrid('update Aadhaar address', [aadhaar, pension], () => confident('aadhaar_address_update'))).toMatchObject({ kind: 'confident', source: 'both' })
    expect(matchProceduresHybrid('residential data correction', [aadhaar, pension], () => confident('aadhaar_address_update'))).toMatchObject({ kind: 'confident', source: 'ml' })
    expect(matchProceduresHybrid('update Aadhaar address', [aadhaar, pension], () => ({ kind: 'abstain', confidence: 0.4, margin: 0.1 }))).toMatchObject({ kind: 'confident', source: 'deterministic' })
    expect(matchProceduresHybrid('update Aadhaar address', [aadhaar, pension], () => confident('kerala_old_age_pension'))).toMatchObject({ kind: 'ambiguous', source: 'disagreement' })
    expect(matchProceduresHybrid('update Aadhaar address', [aadhaar, pension], () => confident('unsupported_other'))).toEqual({ kind: 'none', source: 'unsupported' })
    expect(matchProceduresHybrid('update Aadhaar address', [aadhaar, pension], () => ({ kind: 'unavailable' }))).toMatchObject({ kind: 'confident', source: 'fallback' })
  })

  it('blocks PII before inference executes', () => {
    const infer = vi.fn<(_text: string) => LocalIntentResult>(() => confident('aadhaar_address_update'))
    expect(classifyServiceQuery('1234 5678 9012', [aadhaar], infer)).toEqual({ kind: 'pii' })
    expect(infer).not.toHaveBeenCalled()
  })

  it('does not use network, logging, or browser persistence during inference', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined)
    const localSpy = vi.spyOn(Storage.prototype, 'setItem')
    classifyLocalIntent('aadhar address बदलना please')
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(logSpy).not.toHaveBeenCalled()
    expect(localSpy).not.toHaveBeenCalled()
    logSpy.mockRestore()
    localSpy.mockRestore()
    fetchSpy.mockRestore()
  })
})
