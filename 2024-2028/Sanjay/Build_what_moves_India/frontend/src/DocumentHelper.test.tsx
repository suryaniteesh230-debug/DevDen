import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DocumentHelper } from './DocumentHelper'

vi.mock('./documentValidation', () => ({
  DocumentValidationError: class extends Error {},
  validateDocumentFile: vi.fn(async () => ({ kind: 'image', mimeType: 'image/png', width: 100, height: 100 })),
}))
vi.mock('./documentOcr', () => ({ runLocalOcr: vi.fn(async () => ({ text: 'valid proof address accepted guidance', confidence: 95, pages: 1 })) }))

describe('DocumentHelper', () => {
  it('requires explicit selection and sends only confirmed allowlisted evidence', async () => {
    const onConfirm = vi.fn(async () => undefined)
    render(<DocumentHelper locale="en" documents={[{ document_id: 'valid-proof-of-address', name: 'Valid proof of address', guidance: 'Accepted proof address guidance', source_ids: ['source'] }]} onConfirm={onConfirm} />)
    expect(screen.queryByLabelText(/Choose JPEG/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Check a document on this device' }))
    const input = screen.getByLabelText(/Choose JPEG/) as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File([new Uint8Array([1])], 'synthetic.png', { type: 'image/png' })] } })
    await screen.findByText(/appears to contain information relevant/)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm this clue' }))
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith({ document_id: 'valid-proof-of-address', appears_relevant: true, citizen_confirmed: true }, 'Valid proof of address'))
    expect(JSON.stringify(onConfirm.mock.calls)).not.toContain('valid proof address accepted guidance')
  })

  it('supports rejection and manual fallback without backend evidence', async () => {
    const onConfirm = vi.fn(async () => undefined)
    render(<DocumentHelper locale="en" documents={[{ document_id: 'valid-proof-of-address', name: 'Valid proof of address', guidance: 'Accepted proof address guidance', source_ids: ['source'] }]} onConfirm={onConfirm} />)
    fireEvent.click(screen.getByRole('button', { name: 'Check a document on this device' }))
    fireEvent.click(screen.getByRole('button', { name: 'Skip and answer manually' }))
    expect(onConfirm).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Check a document on this device' })).toBeInTheDocument()
  })

  it('aborts active local processing when the helper unmounts', async () => {
    const ocr = await import('./documentOcr')
    const capturedSignal: { current: AbortSignal | null } = { current: null }
    vi.mocked(ocr.runLocalOcr).mockImplementation((_file, _validation, _locale, signal) => {
      capturedSignal.current = signal
      return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError')), { once: true }))
    })
    const view = render(<DocumentHelper locale="en" documents={[{ document_id: 'valid-proof-of-address', name: 'Valid proof of address', guidance: 'Accepted proof address guidance', source_ids: ['source'] }]} onConfirm={vi.fn(async () => undefined)} />)
    fireEvent.click(screen.getByRole('button', { name: 'Check a document on this device' }))
    fireEvent.change(screen.getByLabelText(/Choose JPEG/), { target: { files: [new File([new Uint8Array([1])], 'synthetic.png', { type: 'image/png' })] } })
    await screen.findByText(/Reviewing on this device/)
    view.unmount()
    expect(capturedSignal.current?.aborted).toBe(true)
  })
})
