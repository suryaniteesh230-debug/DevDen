import type { ProcedureSummary } from './api'
import { classifyServiceQuery, normalise, type Candidate, type MatchResult } from './matcher'

export type ConversationReply = 'matched' | 'ambiguous' | 'address-clarification' | 'pension-address-unsupported' | 'unsupported'
export type ConversationRoute = { kind: 'pii' } | { kind: 'result'; result: MatchResult; reply: ConversationReply }

const ADDRESS_TERMS = ['address', 'पता', 'വിലാസ']
const CHANGE_TERMS = ['change', 'update', 'correct', 'बदल', 'अपडेट', 'सुधार', 'മാറ്റ', 'പുതുക്ക', 'തിരുത്ത']
const AADHAAR_TERMS = ['aadhaar', 'aadhar', 'आधार', 'ആധാർ', 'ആധാര്']
const PENSION_TERMS = ['pension', 'sevana', 'पेंशन', 'पेन्शन', 'പെൻഷൻ', 'പെന്‍ഷന്']
const NAME_TERMS = ['name', 'नाम', 'नाव', 'പേര്']

const includesAny = (value: string, terms: string[]) => terms.some(term => value.includes(term))
const candidate = (procedure: ProcedureSummary): Candidate => ({ procedure, score: 1000, reason: 'token_overlap', matched_tokens: [] })

/** Deterministic, catalogue-only routing for the primary citizen conversation. */
export function routeCitizenRequest(query: string, procedures: ProcedureSummary[], activeServiceId: string | null): ConversationRoute {
  const classified = classifyServiceQuery(query, procedures)
  if (classified.kind === 'pii') return classified

  const normalized = normalise(query)
  const addressChange = includesAny(normalized, ADDRESS_TERMS) && includesAny(normalized, CHANGE_TERMS)
  const hasAadhaarScope = includesAny(normalized, AADHAAR_TERMS)
  const hasPensionScope = includesAny(normalized, PENSION_TERMS)
  const aadhaar = procedures.find(item => item.service_id === 'uidai-aadhaar-address-update')
  const pension = procedures.find(item => item.service_id === 'kerala-ign-oap')

  if (hasAadhaarScope && includesAny(normalized, NAME_TERMS) && includesAny(normalized, CHANGE_TERMS) && !addressChange) {
    return { kind: 'result', result: { kind: 'none', source: 'unsupported' }, reply: 'unsupported' }
  }

  if (activeServiceId === 'kerala-ign-oap' && addressChange && !hasAadhaarScope && !hasPensionScope && aadhaar && pension) {
    return { kind: 'result', result: { kind: 'ambiguous', candidates: [candidate(aadhaar), candidate(pension)], source: 'deterministic' }, reply: 'address-clarification' }
  }
  if (activeServiceId === 'kerala-ign-oap' && addressChange && hasPensionScope && !hasAadhaarScope) {
    return { kind: 'result', result: { kind: 'none', source: 'unsupported' }, reply: 'pension-address-unsupported' }
  }
  const reply = classified.result.kind === 'confident' ? 'matched' : classified.result.kind === 'ambiguous' ? 'ambiguous' : 'unsupported'
  return { ...classified, reply }
}
