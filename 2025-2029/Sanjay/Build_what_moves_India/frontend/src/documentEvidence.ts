import { normalizeIntentText } from './normalization'

export type PackDocument = { document_id: string; name: string; guidance: string }
export type LocalDocumentConclusion = {
  documentId: string | null
  appearsRelevant: boolean
  confidence: number
  matchedTerms: string[]
}

const IDENTIFIER = /(?:\b\d[\d\s-]{7,}\d\b|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})/giu
const STOP = new Set(['the', 'and', 'for', 'with', 'from', 'this', 'that', 'your', 'document', 'documents', 'guidance', 'accepted', 'official', 'का', 'की', 'के', 'और', 'लिए', 'यह', 'दस्तावेज', 'ഒരു', 'ഈ', 'രേഖ', 'ആണ്'])

export function redactIdentifierShapes(text: string): string {
  return text.replace(IDENTIFIER, ' [redacted] ')
}

export function deriveDocumentConclusion(text: string, confidence: number, documents: PackDocument[]): LocalDocumentConclusion {
  if (!Number.isFinite(confidence) || confidence < 60) return { documentId: null, appearsRelevant: false, confidence: Math.max(0, confidence || 0), matchedTerms: [] }
  const safeText = normalizeIntentText(redactIdentifierShapes(text))
  const inputTokens = new Set(safeText.split(' ').filter(Boolean))
  const candidates = documents.map(document => {
    const source = normalizeIntentText(`${document.name} ${document.guidance}`)
    const terms = [...new Set(source.split(' ').filter(term => term.length >= 3 && !STOP.has(term) && !/^\d+$/.test(term)))].slice(0, 30)
    const matchedTerms = terms.filter(term => inputTokens.has(term))
    return { documentId: document.document_id, matchedTerms }
  }).sort((left, right) => right.matchedTerms.length - left.matchedTerms.length || left.documentId.localeCompare(right.documentId))
  const best = candidates[0]
  if (!best || best.matchedTerms.length < 2) return { documentId: null, appearsRelevant: false, confidence, matchedTerms: [] }
  return { documentId: best.documentId, appearsRelevant: true, confidence, matchedTerms: best.matchedTerms.slice(0, 5) }
}
