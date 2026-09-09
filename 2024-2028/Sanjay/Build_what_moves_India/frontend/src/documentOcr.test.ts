import { beforeEach, describe, expect, it, vi } from 'vitest'

const recognize = vi.fn()
const terminate = vi.fn(async () => undefined)
const createWorker = vi.fn(async () => ({ recognize, terminate }))
const getDocument = vi.fn()

vi.mock('tesseract.js', () => ({ createWorker, OEM: { LSTM_ONLY: 1 } }))
vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: {}, getDocument }))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '/assets/pdf.worker.test.mjs' }))

describe('local OCR worker lifecycle', () => {
  beforeEach(() => {
    recognize.mockReset()
    terminate.mockReset()
    terminate.mockResolvedValue(undefined)
    createWorker.mockClear()
    getDocument.mockReset()
  })

  it('runs image OCR with local no-cache paths and terminates the worker', async () => {
    recognize.mockResolvedValue({ data: { text: 'synthetic proof address', confidence: 88 } })
    const { runLocalOcr } = await import('./documentOcr')
    const result = await runLocalOcr(new File([new Uint8Array([1])], 'synthetic.png', { type: 'image/png' }), { kind: 'image', mimeType: 'image/png', width: 1, height: 1 }, 'en', new AbortController().signal, vi.fn())
    expect(result).toMatchObject({ confidence: 88, pages: 1 })
    expect(createWorker).toHaveBeenCalledWith('eng', 1, expect.objectContaining({ workerPath: '/ocr/worker.min.js', corePath: '/ocr/core', langPath: '/ocr/lang', cacheMethod: 'none' }))
    expect(terminate).toHaveBeenCalled()
  })

  it('renders bounded PDF pages to temporary canvases and cleans every resource', async () => {
    const cleanup = vi.fn()
    const page = { getViewport: vi.fn(() => ({ width: 100, height: 100 })), render: vi.fn(() => ({ promise: Promise.resolve() })), cleanup }
    const pdf = { numPages: 1, getPage: vi.fn(async () => page), cleanup: vi.fn(async () => undefined) }
    const destroy = vi.fn(async () => undefined)
    getDocument.mockReturnValue({ promise: Promise.resolve(pdf), destroy, onPassword: null })
    recognize.mockResolvedValue({ data: { text: 'synthetic pension form', confidence: 80 } })
    const { runLocalOcr } = await import('./documentOcr')
    const result = await runLocalOcr(new File([new TextEncoder().encode('%PDF-1.7')], 'synthetic.pdf', { type: 'application/pdf' }), { kind: 'pdf', mimeType: 'application/pdf' }, 'hi', new AbortController().signal, vi.fn())
    expect(result.pages).toBe(1)
    expect(page.render).toHaveBeenCalled()
    expect(cleanup).toHaveBeenCalled()
    expect(pdf.cleanup).toHaveBeenCalled()
    expect(destroy).toHaveBeenCalled()
    expect(terminate).toHaveBeenCalled()
  })

  it('rejects PDFs above three pages and still terminates resources', async () => {
    const pdf = { numPages: 4, cleanup: vi.fn(async () => undefined) }
    const destroy = vi.fn(async () => undefined)
    getDocument.mockReturnValue({ promise: Promise.resolve(pdf), destroy, onPassword: null })
    const { runLocalOcr } = await import('./documentOcr')
    await expect(runLocalOcr(new File([new TextEncoder().encode('%PDF-1.7')], 'synthetic.pdf', { type: 'application/pdf' }), { kind: 'pdf', mimeType: 'application/pdf' }, 'ml', new AbortController().signal, vi.fn())).rejects.toThrow('pdf-page-limit')
    expect(destroy).toHaveBeenCalled()
    expect(terminate).toHaveBeenCalled()
  })

  it('rejects encrypted PDFs without requesting a password and destroys the task', async () => {
    const destroy = vi.fn(async () => undefined)
    const encrypted = Object.assign(new Error('PasswordException'), { name: 'PasswordException' })
    getDocument.mockImplementation(() => ({ promise: Promise.resolve().then(() => { throw encrypted }), destroy, onPassword: null }))
    const { runLocalOcr } = await import('./documentOcr')
    await expect(runLocalOcr(new File([new TextEncoder().encode('%PDF-1.7')], 'synthetic.pdf', { type: 'application/pdf' }), { kind: 'pdf', mimeType: 'application/pdf' }, 'en', new AbortController().signal, vi.fn())).rejects.toMatchObject({ name: 'PasswordException' })
    expect(destroy).toHaveBeenCalled()
    expect(terminate).toHaveBeenCalled()
  })

  it('terminates the active worker on cancellation', async () => {
    let rejectRecognition: (error: Error) => void = () => undefined
    recognize.mockReturnValue(new Promise((_, reject) => { rejectRecognition = reject }))
    terminate.mockImplementation(async () => { rejectRecognition(new DOMException('Cancelled', 'AbortError')) })
    const { runLocalOcr } = await import('./documentOcr')
    const controller = new AbortController()
    const running = runLocalOcr(new File([new Uint8Array([1])], 'synthetic.png', { type: 'image/png' }), { kind: 'image', mimeType: 'image/png', width: 1, height: 1 }, 'en', controller.signal, vi.fn())
    await vi.waitFor(() => expect(recognize).toHaveBeenCalled())
    controller.abort()
    await expect(running).rejects.toMatchObject({ name: 'AbortError' })
    expect(terminate).toHaveBeenCalled()
  })

  it('fails closed when total worker startup exceeds the bounded timeout', async () => {
    vi.useFakeTimers()
    try {
      createWorker.mockImplementationOnce(() => new Promise(() => {}))
      const { runLocalOcr } = await import('./documentOcr')
      const running = runLocalOcr(new File([new Uint8Array([1])], 'synthetic.png', { type: 'image/png' }), { kind: 'image', mimeType: 'image/png', width: 1, height: 1 }, 'en', new AbortController().signal, vi.fn())
      const rejection = expect(running).rejects.toThrow('ocr-total-timeout')
      await vi.advanceTimersByTimeAsync(75_000)
      await rejection
    } finally {
      vi.useRealTimers()
    }
  })
})
