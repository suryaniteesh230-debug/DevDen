import type { ProcedureSummary } from './api'
import { classifyLocalIntent, serviceIdForLabel, type LocalIntentResult } from './localIntent'
import { normalizeIntentText } from './normalization'

export const MAX_QUERY_LENGTH = 500
const MAX_CATALOGUE_CANDIDATES = 100

// These are intentionally few. Service terms are never stop words.
const STOP_WORDS = new Set([
  'a', 'an', 'and', 'are', 'for', 'i', 'in', 'is', 'it', 'my', 'of', 'or', 'the', 'to', 'want', 'with',
  'का', 'की', 'के', 'को', 'में', 'मुझे', 'है', 'करना', 'चाहिए',
  'ഒരു', 'എന്റെ', 'എനിക്ക്', 'ആണ്', 'വേണം', 'ചെയ്യണം',
])

const DECIMAL_ZERO_CODE_POINTS = [0x30, 0x660, 0x6f0, 0x966, 0x9e6, 0xa66, 0xae6, 0xb66, 0xbe6, 0xc66, 0xce6, 0xd66]

export type MatchReason = 'exact_phrase' | 'phrase_containment' | 'token_overlap'
export type Candidate = { procedure: ProcedureSummary; score: number; reason: MatchReason; matched_tokens: string[] }
export type MatchResult =
  | { kind: 'confident'; candidate: Candidate; source?: 'both' | 'ml' | 'deterministic' | 'fallback' }
  | { kind: 'ambiguous'; candidates: Candidate[]; source?: 'disagreement' | 'deterministic' }
  | { kind: 'none'; source?: 'unsupported' | 'both_abstained' | 'fallback' }

export type ServiceQueryResult = { kind: 'pii' } | { kind: 'result'; result: MatchResult }

export function normalise(text: string): string {
  return normalizeIntentText(text)
}

export function matchProceduresHybrid(query: string, procedures: ProcedureSummary[], infer: (text: string) => LocalIntentResult = classifyLocalIntent): MatchResult {
  const deterministic = matchProcedures(query, procedures)
  const ml = infer(query)
  if (ml.kind === 'unavailable') return withFallback(deterministic)
  if (ml.kind === 'abstain') return withDeterministicSource(deterministic)
  if (ml.label === 'unsupported_other') return { kind: 'none', source: 'unsupported' }
  const serviceId = serviceIdForLabel(ml.label)
  const procedure = procedures.find(item => item.service_id === serviceId)
  if (!procedure) return withFallback(deterministic)
  const mlCandidate: Candidate = { procedure, score: Math.round(ml.confidence * 1000), reason: 'token_overlap', matched_tokens: [] }
  if (deterministic.kind === 'none') return { kind: 'confident', candidate: mlCandidate, source: 'ml' }
  if (deterministic.kind === 'ambiguous') return { ...deterministic, source: 'deterministic' }
  if (deterministic.candidate.procedure.service_id === serviceId) return { ...deterministic, source: 'both' }
  return { kind: 'ambiguous', candidates: uniqueCandidates([deterministic.candidate, mlCandidate]), source: 'disagreement' }
}

export function classifyServiceQuery(query: string, procedures: ProcedureSummary[], infer: (text: string) => LocalIntentResult = classifyLocalIntent): ServiceQueryResult {
  if (detectHighRiskPii(query)) return { kind: 'pii' }
  return { kind: 'result', result: matchProceduresHybrid(query, procedures, infer) }
}

function withFallback(result: MatchResult): MatchResult {
  if (result.kind === 'confident') return { ...result, source: 'fallback' }
  if (result.kind === 'none') return { ...result, source: 'fallback' }
  return { ...result, source: 'deterministic' }
}

function withDeterministicSource(result: MatchResult): MatchResult {
  if (result.kind === 'confident') return { ...result, source: 'deterministic' }
  if (result.kind === 'none') return { ...result, source: 'both_abstained' }
  return { ...result, source: 'deterministic' }
}

function uniqueCandidates(candidates: Candidate[]): Candidate[] {
  return [...new Map(candidates.map(candidate => [candidate.procedure.service_id, candidate])).values()]
}

export function meaningfulTokens(text: string): string[] {
  return normalise(text).split(' ').filter(token => token.length > 1 && !STOP_WORDS.has(token))
}

export function detectHighRiskPii(text: string): boolean {
  const normalisedDigits = normaliseDecimalDigits(text)
  const compactDigits = normalisedDigits.replace(/[\s-]/g, '')
  const hasAadhaarLike = /(?<!\d)\d{12}(?!\d)/.test(compactDigits)
  const hasPhoneLike = /(?<!\d)\d{10}(?!\d)/.test(compactDigits)
  const hasEmail = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(text)
  const hasAddressWithNumber = /(?:\b(?:house|flat|door|street|road|lane|ward|pin(?:code)?)\b|मकान|फ्लैट|गली|सड़क|वार्ड|पिन|വീട്|ഫ്ലാറ്റ്|റോഡ്|വാർഡ്|പിൻ).{0,40}\d/iu.test(normalisedDigits)
  return hasAadhaarLike || hasPhoneLike || hasEmail || hasAddressWithNumber
}

export function normaliseDecimalDigits(text: string): string {
  return text.replace(/\p{Nd}/gu, character => {
    const codePoint = character.codePointAt(0) ?? -1
    const zero = DECIMAL_ZERO_CODE_POINTS.find(base => codePoint >= base && codePoint <= base + 9)
    return zero === undefined ? character : String(codePoint - zero)
  })
}

export function matchProcedures(query: string, procedures: ProcedureSummary[]): MatchResult {
  const boundedProcedures = procedures.slice(0, MAX_CATALOGUE_CANDIDATES)
  if (!query.trim() || query.length > MAX_QUERY_LENGTH || boundedProcedures.length === 0) return { kind: 'none' }
  const queryNormalised = normalise(query)
  const queryTokens = new Set(meaningfulTokens(query))
  if (!queryNormalised || queryTokens.size === 0) return { kind: 'none' }

  const frequency = new Map<string, number>()
  for (const procedure of boundedProcedures) for (const phrase of procedure.intent_phrases) {
    for (const token of new Set(meaningfulTokens(phrase))) frequency.set(token, (frequency.get(token) ?? 0) + 1)
  }
  const candidates = boundedProcedures.map(procedure => scoreProcedure(procedure, queryNormalised, queryTokens, frequency, boundedProcedures.length))
    .filter((candidate): candidate is Candidate => candidate !== null)
    .sort((left, right) => right.score - left.score || left.procedure.service_id.localeCompare(right.procedure.service_id))
  if (candidates.length === 0 || candidates[0].score < 260) return { kind: 'none' }
  const first = candidates[0]
  const second = candidates[1]
  if (second && first.score - second.score < 70) return { kind: 'ambiguous', candidates: candidates.slice(0, 3) }
  return { kind: 'confident', candidate: first }
}

function scoreProcedure(procedure: ProcedureSummary, query: string, queryTokens: Set<string>, frequency: Map<string, number>, total: number): Candidate | null {
  let best: Candidate | null = null
  for (const phrase of procedure.intent_phrases) {
    const normalisedPhrase = normalise(phrase)
    const phraseTokens = [...new Set(meaningfulTokens(phrase))]
    if (!normalisedPhrase || phraseTokens.length === 0) continue
    const matchedTokens = phraseTokens.filter(token => queryTokens.has(token))
    const totalWeight = phraseTokens.reduce((sum, token) => sum + tokenWeight(token, frequency, total), 0)
    const matchedWeight = matchedTokens.reduce((sum, token) => sum + tokenWeight(token, frequency, total), 0)
    let score = totalWeight ? Math.round((matchedWeight / totalWeight) * 400) : 0
    let reason: MatchReason = 'token_overlap'
    if (query === normalisedPhrase) { score += 1000; reason = 'exact_phrase' }
    else if (query.includes(normalisedPhrase)) { score += 700; reason = 'phrase_containment' }
    else if (matchedTokens.length === phraseTokens.length) { score += 300; reason = 'token_overlap' }
    const candidate = { procedure, score, reason, matched_tokens: matchedTokens }
    if (!best || candidate.score > best.score) best = candidate
  }
  return best
}

function tokenWeight(token: string, frequency: Map<string, number>, total: number): number {
  return 1 + Math.log((total + 1) / ((frequency.get(token) ?? 0) + 1))
}
