import { useEffect, useRef, useState } from 'react'
import type { ConfirmedDocumentEvidence, DocumentGuidance } from './api'
import { deriveDocumentConclusion, type LocalDocumentConclusion } from './documentEvidence'
import { DocumentValidationError, validateDocumentFile } from './documentValidation'
import type { Locale } from './i18n'

type Props = {
  locale: Locale
  documents: DocumentGuidance[]
  onConfirm: (evidence: ConfirmedDocumentEvidence, clueValue: string) => Promise<void>
}

const COPY = {
  en: {
    open: 'Check a document on this device', intro: 'Optional. Sahayi processes supported files in this browser. OCR can be wrong. No file or OCR text is uploaded or stored.',
    choose: 'Choose JPEG, PNG, WebP, or PDF', cancel: 'Cancel', working: 'Reviewing on this device…', manual: 'Skip and answer manually',
    unknown: 'Sahayi could not identify a reliable, relevant document clue. Please answer the question yourself.',
    relevant: 'This document appears to contain information relevant to the reviewed procedure. Please confirm it yourself. Sahayi has not validated the document with the government.',
    confirm: 'Confirm this clue', reject: 'Reject this clue', confirmed: 'Confirmed as an unverified preparation clue.',
    error: 'This file could not be reviewed safely. Use the manual answer instead.', limit: 'The file exceeds the supported size, page, or pixel limit.',
  },
  hi: {
    open: 'इस डिवाइस पर दस्तावेज़ जाँचें', intro: 'वैकल्पिक। Sahayi समर्थित फ़ाइलों को इसी ब्राउज़र में संसाधित करता है। OCR गलत हो सकता है। कोई फ़ाइल या OCR पाठ अपलोड या संग्रहित नहीं होता।',
    choose: 'JPEG, PNG, WebP या PDF चुनें', cancel: 'रद्द करें', working: 'इस डिवाइस पर समीक्षा हो रही है…', manual: 'छोड़ें और स्वयं उत्तर दें',
    unknown: 'Sahayi को कोई भरोसेमंद और प्रासंगिक दस्तावेज़ संकेत नहीं मिला। कृपया प्रश्न का उत्तर स्वयं दें।',
    relevant: 'यह दस्तावेज़ समीक्षा की गई प्रक्रिया से संबंधित जानकारी रखता हुआ दिखता है। कृपया स्वयं पुष्टि करें। Sahayi ने सरकार से दस्तावेज़ का सत्यापन नहीं किया है।',
    confirm: 'इस संकेत की पुष्टि करें', reject: 'इस संकेत को अस्वीकार करें', confirmed: 'असत्यापित तैयारी संकेत के रूप में पुष्टि की गई।',
    error: 'इस फ़ाइल की सुरक्षित समीक्षा नहीं हो सकी। इसके बजाय स्वयं उत्तर दें।', limit: 'फ़ाइल समर्थित आकार, पृष्ठ या पिक्सेल सीमा से अधिक है।',
  },
  ml: {
    open: 'ഈ ഉപകരണത്തിൽ രേഖ പരിശോധിക്കുക', intro: 'ഐച്ഛികം. പിന്തുണയുള്ള ഫയലുകൾ Sahayi ഈ ബ്രൗസറിൽ പ്രോസസ്സ് ചെയ്യുന്നു. OCR തെറ്റാകാം. ഫയലോ OCR വാചകമോ അപ്‌ലോഡ് ചെയ്യുകയോ സൂക്ഷിക്കുകയോ ഇല്ല.',
    choose: 'JPEG, PNG, WebP അല്ലെങ്കിൽ PDF തിരഞ്ഞെടുക്കുക', cancel: 'റദ്ദാക്കുക', working: 'ഈ ഉപകരണത്തിൽ പരിശോധിക്കുന്നു…', manual: 'ഒഴിവാക്കി സ്വയം ഉത്തരം നൽകുക',
    unknown: 'വിശ്വസനീയവും പ്രസക്തവുമായ രേഖാ സൂചന Sahayiക്ക് കണ്ടെത്താനായില്ല. ചോദ്യം സ്വയം ഉത്തരം നൽകുക.',
    relevant: 'അവലോകനം ചെയ്ത നടപടിയുമായി ബന്ധപ്പെട്ട വിവരം ഈ രേഖയിൽ ഉള്ളതായി തോന്നുന്നു. ദയവായി സ്വയം സ്ഥിരീകരിക്കുക. Sahayi സർക്കാർ സംവിധാനത്തിൽ രേഖ പരിശോധിച്ചിട്ടില്ല.',
    confirm: 'ഈ സൂചന സ്ഥിരീകരിക്കുക', reject: 'ഈ സൂചന നിരസിക്കുക', confirmed: 'പരിശോധിക്കാത്ത തയ്യാറെടുപ്പ് സൂചനയായി സ്ഥിരീകരിച്ചു.',
    error: 'ഈ ഫയൽ സുരക്ഷിതമായി പരിശോധിക്കാനായില്ല. പകരം നേരിട്ട് ഉത്തരം നൽകുക.', limit: 'പിന്തുണയുള്ള വലുപ്പം, പേജ്, അല്ലെങ്കിൽ പിക്സൽ പരിധി ഫയൽ കവിയുന്നു.',
  },
} as const

export function DocumentHelper({ locale, documents, onConfirm }: Props) {
  const [open, setOpen] = useState(false)
  const [state, setState] = useState<'idle' | 'working' | 'result' | 'error' | 'confirmed'>('idle')
  const [progress, setProgress] = useState(0)
  const [conclusion, setConclusion] = useState<LocalDocumentConclusion | null>(null)
  const [limitError, setLimitError] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const copy = COPY[locale]

  const clear = () => {
    controller.current?.abort()
    controller.current = null
    if (input.current) input.current.value = ''
    setProgress(0)
    setConclusion(null)
  }

  useEffect(() => () => {
    controller.current?.abort()
    controller.current = null
  }, [locale])

  const inspect = async (file: File) => {
    clear()
    const nextController = new AbortController()
    controller.current = nextController
    setState('working')
    setLimitError(false)
    try {
      const validation = await validateDocumentFile(file)
      const { runLocalOcr } = await import('./documentOcr')
      const result = await runLocalOcr(file, validation, locale, nextController.signal, value => setProgress(Math.round(value.progress * 100)))
      if (nextController.signal.aborted) return
      setConclusion(deriveDocumentConclusion(result.text, result.confidence, documents))
      setState('result')
    } catch (error) {
      if (nextController.signal.aborted) { setState('idle'); return }
      setLimitError(error instanceof DocumentValidationError && ['too-large', 'too-many-pixels'].includes(error.code) || error instanceof Error && ['pdf-page-limit', 'pixel-limit'].includes(error.message))
      setState('error')
    } finally {
      controller.current = null
      if (input.current) input.current.value = ''
    }
  }

  const confirm = async () => {
    if (!conclusion?.documentId) return
    const clueValue = documents.find(document => document.document_id === conclusion.documentId)?.name
    if (!clueValue) return
    await onConfirm({ document_id: conclusion.documentId, appears_relevant: conclusion.appearsRelevant, citizen_confirmed: true }, clueValue)
    setState('confirmed')
    setConclusion(null)
  }

  if (!open) return <button type="button" className="document-helper-open secondary compact" onClick={() => setOpen(true)}>{copy.open}</button>
  return <aside className="document-helper" aria-label={copy.open}>
    <h2>{copy.open}</h2><p>{copy.intro}</p>
    {state !== 'working' && state !== 'confirmed' && <label className="document-picker">{copy.choose}<input ref={input} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={event => { const file = event.target.files?.[0]; if (file) void inspect(file) }} /></label>}
    {state === 'working' && <div role="status" aria-live="polite"><p>{copy.working} {progress}%</p><progress max="100" value={progress} /><button type="button" className="secondary compact" onClick={() => { clear(); setState('idle') }}>{copy.cancel}</button></div>}
    {state === 'result' && conclusion && <div className="document-conclusion" role="status"><p>{conclusion.appearsRelevant ? copy.relevant : copy.unknown}</p>{conclusion.appearsRelevant && <div className="suggested-responses"><button type="button" onClick={() => void confirm()}>{copy.confirm}</button><button type="button" className="secondary" onClick={() => { setConclusion(null); setState('idle') }}>{copy.reject}</button></div>}</div>}
    {state === 'error' && <p className="inline-error" role="alert">{limitError ? copy.limit : copy.error}</p>}
    {state === 'confirmed' && <p role="status">{copy.confirmed}</p>}
    <button type="button" className="browse-fallback" onClick={() => { clear(); setOpen(false); setState('idle') }}>{copy.manual}</button>
  </aside>
}
