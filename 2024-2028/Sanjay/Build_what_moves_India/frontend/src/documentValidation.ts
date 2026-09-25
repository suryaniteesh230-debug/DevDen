export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
export const MAX_DOCUMENT_PIXELS = 20_000_000
export const MAX_PDF_PAGES = 3

export type SupportedDocumentKind = 'image' | 'pdf'
export type ValidatedDocument = { kind: SupportedDocumentKind; mimeType: string; width?: number; height?: number }
export type DocumentValidationCode = 'empty' | 'too-large' | 'unsupported' | 'signature-mismatch' | 'too-many-pixels' | 'malformed'

export class DocumentValidationError extends Error {
  readonly code: DocumentValidationCode

  constructor(code: DocumentValidationCode) {
    super(code)
    this.name = 'DocumentValidationError'
    this.code = code
  }
}

const signatures = {
  'image/jpeg': (bytes: Uint8Array) => bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff,
  'image/png': (bytes: Uint8Array) => [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a].every((value, index) => bytes[index] === value),
  'image/webp': (bytes: Uint8Array) => text(bytes, 0, 4) === 'RIFF' && text(bytes, 8, 12) === 'WEBP',
  'application/pdf': (bytes: Uint8Array) => text(bytes, 0, 5) === '%PDF-',
} as const

export async function validateDocumentFile(file: File): Promise<ValidatedDocument> {
  if (file.size === 0) throw new DocumentValidationError('empty')
  if (file.size > MAX_DOCUMENT_BYTES) throw new DocumentValidationError('too-large')
  const verifier = signatures[file.type as keyof typeof signatures]
  if (!verifier) throw new DocumentValidationError('unsupported')
  const bytes = new Uint8Array(await readBlob(file.slice(0, 16)))
  if (!verifier(bytes)) throw new DocumentValidationError('signature-mismatch')
  if (file.type === 'application/pdf') return { kind: 'pdf', mimeType: file.type }

  try {
    const bitmap = await createImageBitmap(file)
    const width = bitmap.width
    const height = bitmap.height
    bitmap.close()
    if (width <= 0 || height <= 0) throw new DocumentValidationError('malformed')
    if (width * height > MAX_DOCUMENT_PIXELS) throw new DocumentValidationError('too-many-pixels')
    return { kind: 'image', mimeType: file.type, width, height }
  } catch (error) {
    if (error instanceof DocumentValidationError) throw error
    throw new DocumentValidationError('malformed')
  }
}

export async function readBlob(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === 'function') return blob.arrayBuffer()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new DocumentValidationError('malformed'))
    reader.onload = () => reader.result instanceof ArrayBuffer ? resolve(reader.result) : reject(new DocumentValidationError('malformed'))
    reader.readAsArrayBuffer(blob)
  })
}

function text(bytes: Uint8Array, start: number, end: number): string {
  return String.fromCharCode(...bytes.slice(start, end))
}
