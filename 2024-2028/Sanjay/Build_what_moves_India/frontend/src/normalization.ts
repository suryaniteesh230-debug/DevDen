export const NORMALIZATION_VERSION = 'nfkc-lower-ln-space-v1'

export function normalizeIntentText(text: string): string {
  return text.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, ' ').replace(/\s+/g, ' ').trim()
}
