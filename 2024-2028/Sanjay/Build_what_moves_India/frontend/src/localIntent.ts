import rawModel from '../../intent-model/artifacts/intent-model.v1.json'
import { NORMALIZATION_VERSION, normalizeIntentText } from './normalization'

export const EXPECTED_MODEL_DIGEST = 'fd8966853576dc1233a82908f93ce80a56d87537d0f0a82ef94d25a97adf54b4'
export const EXPECTED_DATASET_DIGEST = '14e56d1561584e6bfec420957d393740a9f3f6de53cbf6b965ad4a0084c58e62'
export const LOCAL_INTENT_LABELS = ['aadhaar_address_update', 'kerala_old_age_pension', 'unsupported_other'] as const
export type LocalIntentLabel = (typeof LOCAL_INTENT_LABELS)[number]
export type LocalIntentResult =
  | { kind: 'confident'; label: LocalIntentLabel; confidence: number; margin: number }
  | { kind: 'abstain'; confidence: number; margin: number }
  | { kind: 'unavailable' }

type IntentModel = {
  schema_version: number
  model_type: string
  model_version: string
  dataset_digest: string
  normalization_version: string
  labels: LocalIntentLabel[]
  allowed_service_ids: Record<LocalIntentLabel, string | null>
  input: { max_code_points: number }
  features: { minimum_ngram: number; maximum_ngram: number; maximum_feature_count: number; maximum_vocabulary: number; vocabulary: string[] }
  thresholds: { minimum_confidence: number; minimum_margin: number; tuned_on: string }
  class_log_priors: Record<LocalIntentLabel, number>
  feature_log_probabilities: Record<LocalIntentLabel, number[]>
  normalization_vectors: Array<{ input: string; output: string }>
}

const SERVICE_IDS: Record<LocalIntentLabel, string | null> = {
  aadhaar_address_update: 'uidai-aadhaar-address-update',
  kerala_old_age_pension: 'kerala-ign-oap',
  unsupported_other: null,
}

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

export function validateLocalIntentModel(value: unknown): IntentModel | null {
  try {
    if (!value || typeof value !== 'object') return null
    const model = value as IntentModel
    if (model.schema_version !== 1 || model.model_type !== 'character_ngram_multinomial_naive_bayes' || model.model_version !== '1.0.0') return null
    if (model.dataset_digest !== EXPECTED_DATASET_DIGEST || model.normalization_version !== NORMALIZATION_VERSION) return null
    if (JSON.stringify(model.labels) !== JSON.stringify(LOCAL_INTENT_LABELS)) return null
    if (!model.allowed_service_ids || LOCAL_INTENT_LABELS.some(label => model.allowed_service_ids[label] !== SERVICE_IDS[label])) return null
    const features = model.features
    if (!features || features.minimum_ngram !== 2 || features.maximum_ngram !== 5 || features.maximum_feature_count !== 4 || features.maximum_vocabulary !== 6000) return null
    if (!Array.isArray(features.vocabulary) || features.vocabulary.length === 0 || features.vocabulary.length > features.maximum_vocabulary) return null
    if (features.vocabulary.some((feature, index) => typeof feature !== 'string' || (index > 0 && features.vocabulary[index - 1] >= feature))) return null
    if (!model.input || model.input.max_code_points !== 500) return null
    if (!model.thresholds || model.thresholds.tuned_on !== 'validation' || !finite(model.thresholds.minimum_confidence) || !finite(model.thresholds.minimum_margin)) return null
    if (model.thresholds.minimum_confidence < 0.5 || model.thresholds.minimum_confidence > 0.95 || model.thresholds.minimum_margin < 0 || model.thresholds.minimum_margin > 0.9) return null
    for (const label of LOCAL_INTENT_LABELS) {
      if (!finite(model.class_log_priors?.[label])) return null
      const weights = model.feature_log_probabilities?.[label]
      if (!Array.isArray(weights) || weights.length !== features.vocabulary.length || weights.some(weight => !finite(weight))) return null
    }
    if (!Array.isArray(model.normalization_vectors) || model.normalization_vectors.some(vector => normalizeIntentText(vector.input) !== vector.output)) return null
    return model
  } catch {
    return null
  }
}

function createInference(model: IntentModel) {
  const vocabulary = new Map(model.features.vocabulary.map((feature, index) => [feature, index]))
  return (text: string): LocalIntentResult => {
    if (!text || Array.from(text).length > model.input.max_code_points) return { kind: 'abstain', confidence: 0, margin: 0 }
    const normalized = normalizeIntentText(text)
    if (!normalized) return { kind: 'abstain', confidence: 0, margin: 0 }
    const bounded = Array.from(`^${normalized}$`)
    const counts = new Map<number, number>()
    for (let size = model.features.minimum_ngram; size <= model.features.maximum_ngram; size += 1) {
      for (let offset = 0; offset <= bounded.length - size; offset += 1) {
        const index = vocabulary.get(bounded.slice(offset, offset + size).join(''))
        if (index !== undefined) counts.set(index, Math.min((counts.get(index) ?? 0) + 1, model.features.maximum_feature_count))
      }
    }
    if (counts.size === 0) return { kind: 'abstain', confidence: 0, margin: 0 }
    const scores = LOCAL_INTENT_LABELS.map(label => {
      let score = model.class_log_priors[label]
      for (const [index, count] of counts) score += model.feature_log_probabilities[label][index] * count
      return { label, score }
    }).sort((left, right) => right.score - left.score || left.label.localeCompare(right.label))
    const maximum = scores[0].score
    const exponentials = scores.map(item => Math.exp(item.score - maximum))
    const total = exponentials.reduce((sum, value) => sum + value, 0)
    const confidence = exponentials[0] / total
    const margin = confidence - exponentials[1] / total
    if (confidence < model.thresholds.minimum_confidence || margin < model.thresholds.minimum_margin) return { kind: 'abstain', confidence, margin }
    return { kind: 'confident', label: scores[0].label, confidence, margin }
  }
}

const validatedModel = validateLocalIntentModel(rawModel)
const bundledInference = validatedModel ? createInference(validatedModel) : null

export function classifyLocalIntent(text: string, artifact: unknown = rawModel): LocalIntentResult {
  if (artifact === rawModel) return bundledInference?.(text) ?? { kind: 'unavailable' }
  const model = validateLocalIntentModel(artifact)
  return model ? createInference(model)(text) : { kind: 'unavailable' }
}

export function serviceIdForLabel(label: LocalIntentLabel): string | null {
  return SERVICE_IDS[label]
}
