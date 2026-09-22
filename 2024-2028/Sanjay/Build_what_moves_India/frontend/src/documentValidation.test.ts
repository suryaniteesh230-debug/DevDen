import { afterEach, describe, expect, it, vi } from 'vitest'
import { deriveDocumentConclusion, redactIdentifierShapes } from './documentEvidence'
import { DocumentValidationError, MAX_DOCUMENT_BYTES, validateDocumentFile } from './documentValidation'

const file = (bytes: number[], type: string) => new File([new Uint8Array(bytes)], 'synthetic.bin', { type })

describe('document safety boundary', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('validates MIME and signature together for supported image and PDF types', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 100, height: 80, close: vi.fn() })))
    await expect(validateDocumentFile(file([0xff, 0xd8, 0xff, 0x00], 'image/jpeg'))).resolves.toMatchObject({ kind: 'image', width: 100, height: 80 })
    await expect(validateDocumentFile(file([0x25, 0x50, 0x44, 0x46, 0x2d], 'application/pdf'))).resolves.toEqual({ kind: 'pdf', mimeType: 'application/pdf' })
    await expect(validateDocumentFile(file([0x25, 0x50, 0x44, 0x46, 0x2d], 'image/jpeg'))).rejects.toMatchObject({ code: 'signature-mismatch' })
  })

  it('rejects unsupported, over-size, malformed, and over-pixel inputs', async () => {
    for (const type of ['image/svg+xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/zip']) {
      await expect(validateDocumentFile(file([0x3c, 0x73, 0x76, 0x67], type))).rejects.toBeInstanceOf(DocumentValidationError)
    }
    await expect(validateDocumentFile(new File([new Uint8Array(MAX_DOCUMENT_BYTES + 1)], 'large.png', { type: 'image/png' }))).rejects.toMatchObject({ code: 'too-large' })
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 5000, height: 5000, close: vi.fn() })))
    await expect(validateDocumentFile(file([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 'image/png'))).rejects.toMatchObject({ code: 'too-many-pixels' })
  })

  it('redacts identifier shapes and never promotes low-confidence OCR', () => {
    const redacted = redactIdentifierShapes('Aadhaar 1234 5678 9012 citizen@example.com proof address')
    expect(redacted).not.toContain('1234 5678 9012')
    expect(redacted).not.toContain('citizen@example.com')
    const documents = [{ document_id: 'valid-proof-of-address', name: 'Valid proof of address', guidance: 'Use accepted proof address guidance' }]
    expect(deriveDocumentConclusion('valid proof address', 42, documents).appearsRelevant).toBe(false)
    expect(deriveDocumentConclusion('valid proof address', 91, documents)).toMatchObject({ documentId: 'valid-proof-of-address', appearsRelevant: true })
  })
})
