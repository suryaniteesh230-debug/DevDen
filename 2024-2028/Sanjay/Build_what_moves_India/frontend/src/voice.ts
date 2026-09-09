import { useCallback, useEffect, useRef, useState } from 'react'
import type { Locale } from './i18n'

export type VoiceInputState = 'stopped' | 'listening' | 'processing' | 'unavailable' | 'permission-denied'

type RecognitionResultLike = { 0?: { transcript?: string } }
type RecognitionEventLike = { results: ArrayLike<RecognitionResultLike> }
type RecognitionErrorLike = { error?: string }

export interface BrowserSpeechRecognition {
  lang: string
  continuous: boolean
  interimResults: boolean
  onstart: (() => void) | null
  onresult: ((event: RecognitionEventLike) => void) | null
  onerror: ((event: RecognitionErrorLike) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

type RecognitionConstructor = new () => BrowserSpeechRecognition
type VoiceWindow = Window & typeof globalThis & {
  SpeechRecognition?: RecognitionConstructor
  webkitSpeechRecognition?: RecognitionConstructor
}

const recognitionLocale: Record<Locale, string> = { en: 'en-IN', hi: 'hi-IN', ml: 'ml-IN' }

function recognitionConstructor(): RecognitionConstructor | null {
  if (typeof window === 'undefined') return null
  const voiceWindow = window as VoiceWindow
  return voiceWindow.SpeechRecognition ?? voiceWindow.webkitSpeechRecognition ?? null
}

export function useVoiceAssistance(locale: Locale, navigationKey: string) {
  const recognition = useRef<BrowserSpeechRecognition | null>(null)
  const [inputState, setInputState] = useState<VoiceInputState>(() => recognitionConstructor() ? 'stopped' : 'unavailable')
  const speechSupported = typeof window !== 'undefined' && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined'

  const stopInput = useCallback((nextState: VoiceInputState = 'stopped') => {
    const active = recognition.current
    recognition.current = null
    if (active) {
      active.onstart = null; active.onresult = null; active.onerror = null; active.onend = null
      try { active.abort() } catch { /* Browser recognition may already be stopped. */ }
    }
    setInputState(recognitionConstructor() ? nextState : 'unavailable')
  }, [])

  const stopSpeech = useCallback(() => {
    if (speechSupported) window.speechSynthesis.cancel()
  }, [speechSupported])

  const stopAll = useCallback(() => { stopInput(); stopSpeech() }, [stopInput, stopSpeech])

  const startInput = useCallback((onTranscript: (transcript: string) => void) => {
    const Constructor = recognitionConstructor()
    if (!Constructor) { setInputState('unavailable'); return }
    stopInput()
    const instance = new Constructor()
    recognition.current = instance
    instance.lang = recognitionLocale[locale]
    instance.continuous = false
    instance.interimResults = false
    instance.onstart = () => setInputState('listening')
    instance.onresult = event => {
      setInputState('processing')
      const transcript = Array.from(event.results).map(result => result[0]?.transcript ?? '').join(' ').trim()
      if (transcript) onTranscript(transcript)
    }
    instance.onerror = event => {
      const denied = event.error === 'not-allowed' || event.error === 'service-not-allowed'
      recognition.current = null
      setInputState(denied ? 'permission-denied' : 'stopped')
    }
    instance.onend = () => {
      if (recognition.current === instance) recognition.current = null
      setInputState(current => current === 'permission-denied' || current === 'unavailable' ? current : 'stopped')
    }
    try { instance.start() } catch { recognition.current = null; setInputState('stopped') }
  }, [locale, stopInput])

  const readAloud = useCallback((text: string) => {
    if (!speechSupported || !text.trim()) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = recognitionLocale[locale]
    const preferred = window.speechSynthesis.getVoices().find(voice => voice.lang.toLowerCase().startsWith(locale === 'en' ? 'en-in' : locale))
    if (preferred) utterance.voice = preferred
    window.speechSynthesis.speak(utterance)
  }, [locale, speechSupported])

  useEffect(() => {
    return () => stopAll()
  }, [locale, navigationKey, stopAll])

  return { inputSupported: inputState !== 'unavailable', inputState, speechSupported, startInput, stopInput, readAloud, stopSpeech, stopAll }
}
