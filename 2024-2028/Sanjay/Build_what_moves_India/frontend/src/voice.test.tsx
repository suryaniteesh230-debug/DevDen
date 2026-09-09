import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { useVoiceAssistance, type BrowserSpeechRecognition } from './voice'
import type { Locale } from './i18n'

class MockRecognition implements BrowserSpeechRecognition {
  static instances: MockRecognition[] = []
  lang = ''
  continuous = true
  interimResults = true
  onstart: (() => void) | null = null
  onresult: ((event: { results: ArrayLike<{ 0?: { transcript?: string } }> }) => void) | null = null
  onerror: ((event: { error?: string }) => void) | null = null
  onend: (() => void) | null = null
  start = vi.fn(() => this.onstart?.())
  stop = vi.fn()
  abort = vi.fn()
  constructor() { MockRecognition.instances.push(this) }
}

function Harness({ locale = 'en', navigationKey = 'intake' }: { locale?: Locale; navigationKey?: string }) {
  const [transcript, setTranscript] = useState('')
  const voice = useVoiceAssistance(locale, navigationKey)
  return <><button onClick={() => voice.startInput(setTranscript)}>start voice</button><button onClick={() => voice.readAloud('Current question')}>read</button><span>{voice.inputState}</span><output>{transcript}</output></>
}

afterEach(() => {
  cleanup()
  MockRecognition.instances = []
  vi.restoreAllMocks()
  delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition
  delete (window as unknown as { speechSynthesis?: unknown }).speechSynthesis
  delete (globalThis as unknown as { SpeechSynthesisUtterance?: unknown }).SpeechSynthesisUtterance
})

describe('browser voice assistance', () => {
  it('detects support, uses the Indian locale, and keeps the transcript in component memory', () => {
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: MockRecognition })
    render(<Harness locale="hi" />)
    fireEvent.click(screen.getByRole('button', { name: 'start voice' }))
    const recognition = MockRecognition.instances.at(-1)!
    expect(recognition.lang).toBe('hi-IN')
    expect(screen.getByText('listening')).toBeInTheDocument()
    act(() => recognition.onresult?.({ results: [{ 0: { transcript: 'आधार पता अपडेट' } }] }))
    expect(screen.getByText('आधार पता अपडेट')).toBeInTheDocument()
    act(() => recognition.onend?.())
    expect(screen.getByText('stopped')).toBeInTheDocument()
  })

  it('reports permission denial and aborts recognition on locale change and unmount', () => {
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: MockRecognition })
    const view = render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'start voice' }))
    const denied = MockRecognition.instances.at(-1)!
    act(() => denied.onerror?.({ error: 'not-allowed' }))
    expect(screen.getByText('permission-denied')).toBeInTheDocument()
    view.rerender(<Harness locale="ml" />)
    fireEvent.click(screen.getByRole('button', { name: 'start voice' }))
    const active = MockRecognition.instances.at(-1)!
    expect(active.lang).toBe('ml-IN')
    view.unmount()
    expect(active.abort).toHaveBeenCalled()
  })

  it('reads with a matching voice and cancels previous speech', () => {
    const cancel = vi.fn()
    const speak = vi.fn()
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: { cancel, speak, getVoices: () => [{ lang: 'ml-IN', name: 'Malayalam' }] } })
    class MockUtterance { lang = ''; voice: unknown = null; text: string; constructor(text: string) { this.text = text } }
    Object.defineProperty(globalThis, 'SpeechSynthesisUtterance', { configurable: true, value: MockUtterance })
    render(<Harness locale="ml" />)
    fireEvent.click(screen.getByRole('button', { name: 'read' }))
    expect(cancel).toHaveBeenCalled()
    expect(speak).toHaveBeenCalledWith(expect.objectContaining({ text: 'Current question', lang: 'ml-IN', voice: expect.objectContaining({ lang: 'ml-IN' }) }))
  })
})
