import { createWorker, OEM, type Worker } from 'tesseract.js'
import { GlobalWorkerOptions, getDocument, type PDFDocumentLoadingTask, type PDFDocumentProxy, type PDFPageProxy } from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { MAX_DOCUMENT_PIXELS, MAX_PDF_PAGES, readBlob, type ValidatedDocument } from './documentValidation'

GlobalWorkerOptions.workerSrc = pdfWorkerUrl

const PAGE_TIMEOUT_MS = 30_000
const TOTAL_TIMEOUT_MS = 75_000
const OCR_LANGUAGES = { en: 'eng', hi: 'hin', ml: 'mal' } as const

export type OcrProgress = { status: string; progress: number; page: number; pages: number }
export type OcrOutput = { text: string; confidence: number; pages: number }

export async function runLocalOcr(
  file: File,
  validation: ValidatedDocument,
  locale: keyof typeof OCR_LANGUAGES,
  signal: AbortSignal,
  onProgress: (progress: OcrProgress) => void,
): Promise<OcrOutput> {
  const resources: { worker: Worker | null; pdf: PDFDocumentProxy | null; loadingTask: PDFDocumentLoadingTask | null } = {
    worker: null,
    pdf: null,
    loadingTask: null,
  }
  let expired = false
  const cancel = () => { void resources.worker?.terminate(); void resources.loadingTask?.destroy() }
  signal.addEventListener('abort', cancel, { once: true })
  let totalTimer = 0
  const totalTimeout = new Promise<never>((_, reject) => {
    totalTimer = window.setTimeout(() => {
      expired = true
      cancel()
      reject(new Error('ocr-total-timeout'))
    }, TOTAL_TIMEOUT_MS)
  })
  const processDocument = async (): Promise<OcrOutput> => {
    assertActive(signal)
    const language = OCR_LANGUAGES[locale]
    resources.worker = await createWorker(language, OEM.LSTM_ONLY, {
      workerPath: '/ocr/worker.min.js',
      corePath: '/ocr/core',
      langPath: '/ocr/lang',
      cacheMethod: 'none',
      logger: message => {
        if (typeof message.progress === 'number') onProgress({ status: message.status, progress: message.progress, page: 1, pages: 1 })
      },
      errorHandler: cancel,
    })
    if (expired) {
      await resources.worker.terminate()
      throw new Error('ocr-total-timeout')
    }
    assertActive(signal)
    if (validation.kind === 'image') {
      const result = await withTimeout(resources.worker.recognize(file), PAGE_TIMEOUT_MS, cancel)
      return { text: result.data.text, confidence: result.data.confidence, pages: 1 }
    }

    const data = new Uint8Array(await readBlob(file))
    resources.loadingTask = getDocument({ data, useWorkerFetch: false, stopAtErrors: true, maxImageSize: MAX_DOCUMENT_PIXELS, disableFontFace: true, enableXfa: false })
    resources.loadingTask.onPassword = () => { void resources.loadingTask?.destroy() }
    resources.pdf = await resources.loadingTask.promise
    if (resources.pdf.numPages > MAX_PDF_PAGES) throw new Error('pdf-page-limit')
    const texts: string[] = []
    let confidenceTotal = 0
    for (let pageNumber = 1; pageNumber <= resources.pdf.numPages; pageNumber += 1) {
      assertActive(signal)
      const page = await resources.pdf.getPage(pageNumber)
      const canvas = renderCanvas(page)
      try {
        onProgress({ status: 'rendering', progress: (pageNumber - 1) / resources.pdf.numPages, page: pageNumber, pages: resources.pdf.numPages })
        await page.render({ canvas, canvasContext: canvas.getContext('2d')!, viewport: page.getViewport({ scale: 1.5 }) }).promise
        const result = await withTimeout(resources.worker.recognize(canvas), PAGE_TIMEOUT_MS, cancel)
        texts.push(result.data.text)
        confidenceTotal += result.data.confidence
        onProgress({ status: 'recognizing', progress: pageNumber / resources.pdf.numPages, page: pageNumber, pages: resources.pdf.numPages })
      } finally {
        canvas.width = 1
        canvas.height = 1
        page.cleanup()
      }
    }
    return { text: texts.join('\n'), confidence: confidenceTotal / resources.pdf.numPages, pages: resources.pdf.numPages }
  }
  try {
    return await Promise.race([processDocument(), totalTimeout])
  } finally {
    window.clearTimeout(totalTimer)
    signal.removeEventListener('abort', cancel)
    await resources.worker?.terminate()
    await resources.pdf?.cleanup()
    await resources.loadingTask?.destroy()
  }
}

function renderCanvas(page: PDFPageProxy): HTMLCanvasElement {
  const viewport = page.getViewport({ scale: 1.5 })
  if (viewport.width * viewport.height > MAX_DOCUMENT_PIXELS) throw new Error('pixel-limit')
  const canvas = document.createElement('canvas')
  canvas.width = Math.ceil(viewport.width)
  canvas.height = Math.ceil(viewport.height)
  return canvas
}

function assertActive(signal: AbortSignal): void {
  if (signal.aborted) throw new DOMException('Cancelled', 'AbortError')
}

async function withTimeout<T>(operation: Promise<T>, timeout: number, cancel: () => void): Promise<T> {
  let timer = 0
  try {
    return await Promise.race([
      operation,
      new Promise<T>((_, reject) => { timer = window.setTimeout(() => { cancel(); reject(new Error('ocr-timeout')) }, timeout) }),
    ])
  } finally {
    window.clearTimeout(timer)
  }
}
