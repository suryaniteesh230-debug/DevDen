import type { Locale } from './i18n'

export type HealthStatus = { status: 'ok' }
export type PublicConfig = {
  application_name: string
  kiosk_mode: boolean
  agent_available: boolean
  agent_provider: 'groq'
  agent_model: string
  inactivity_timeout_seconds: number
  inactivity_warning_seconds: number
}
export type TrustState = 'current' | 'stale'
export type FeeVerificationStatus = 'confirmed' | 'conflicting' | 'free' | 'not_stated'
export type TranslationInfo = {
  locale: Locale
  canonical_locale: 'en'
  method: 'canonical_source' | 'machine_assisted_prototype'
  review_status: 'canonical_verified' | 'native_review_required'
  disclaimer: string
}
export type ProcedureSummary = {
  service_id: string
  title: string
  short_description: string
  intent_phrases: string[]
  category: string
  category_label: string
  trust_state: TrustState
  attention_required: boolean
}
export type CitedFact = { fact_id: string; text: string; source_ids: string[] }
export type DocumentGuidance = { document_id: string; name: string; guidance: string; source_ids: string[] }
export type FeeClaim = { amount: string; currency: string; qualifier: string; source_ids: string[] }
export type FeeInformation = {
  verification_status: FeeVerificationStatus
  amount: string | null
  currency: string | null
  display_message: string
  claims: FeeClaim[]
  resolution_guidance: string | null
  source_ids: string[]
}
export type ProcedureStep = { step_id: string; order: number; title: string; instruction: string; source_ids: string[] }
export type ProcedureSource = {
  source_id: string
  publisher: string
  title: string
  url: string
  retrieved_at: string
  official_updated_date: string | null
  sha256: string | null
  source_type: 'webpage' | 'pdf'
}
export type ProcedureDetail = {
  locale: Locale
  translation: TranslationInfo
  service_id: string
  title: string
  short_description: string
  category: string
  category_label: string
  jurisdiction: { level: 'national' | 'state' | 'local'; name: string }
  department: string
  official_publisher: string
  interaction_modes: Array<'online' | 'in_person'>
  requirements: CitedFact[]
  required_documents: DocumentGuidance[]
  fee: FeeInformation
  steps: ProcedureStep[]
  submission_channels: Array<{ channel_id: string; mode: 'online' | 'in_person'; name: string; guidance: string; source_ids: string[] }>
  official_handoff_url: string
  tracking_guidance: CitedFact | null
  sources: ProcedureSource[]
  provenance: Record<string, string[]>
  pack_version: string
  pack_digest: string
  last_verified_at: string
  review_due_at: string
  trust_state: TrustState
  attention_required: boolean
  limitations: CitedFact[]
  additional_review_items: CitedFact[]
  monitoring: {
    prototype_available: boolean
    continuously_monitored: false
    human_review_required: true
    baseline_status: 'reviewed' | 'review_required' | 'unavailable'
    monitored_source_count: number
  }
}
export type ReadinessAnswer = boolean | number | string
export type ReadinessQuestion = {
  question_id: string
  prompt: string
  help_text: string | null
  answer_type: 'boolean' | 'single_choice' | 'integer'
  options: Array<{ option_id: string; label: string }> | null
  minimum: number | null
  maximum: number | null
  required: boolean
  sensitivity: 'non_sensitive' | 'sensitive'
}
export type ReadinessResponse = {
  locale: Locale
  translation: TranslationInfo
  pack_version: string
  pack_digest: string
  evaluation_status: 'incomplete' | 'ready' | 'alternative_path' | 'needs_information' | 'cannot_confirm'
  complete: boolean
  progress: { answered: number; total: number }
  next_question: ReadinessQuestion | null
  outcome: { outcome_id: string; status: 'ready' | 'alternative_path' | 'needs_information' | 'cannot_confirm'; title: string; explanation: string } | null
  reason_trace: Array<{ trace_type: 'question' | 'rule' | 'outcome' | 'default'; trace_id: string; source_ids: string[] }>
  sources: ProcedureSource[]
  recommended_next_steps: string[]
  official_handoff_url: string | null
  disclaimer: string
}
export type ChecklistItem = { item_id: string; text: string; source_ids: string[] }
export type PersonalizedChecklist = {
  locale: Locale
  translation: TranslationInfo
  service_id: string
  title: string
  pack_version: string
  pack_digest: string
  result: ChecklistItem
  ready: ChecklistItem[]
  documents: DocumentGuidance[]
  confirm: ChecklistItem[]
  steps: ChecklistItem[]
  warnings: ChecklistItem[]
  where: ChecklistItem[]
  sources: ProcedureSource[]
  not_verified: ChecklistItem[]
  official_handoff_url: string
  disclaimer: string
}
export type SyntheticFormAssistance = {
  locale: Locale
  translation: TranslationInfo
  service_id: string
  title: string
  mode: 'official_form_worksheet' | 'preparation_worksheet'
  persona: { persona_id: string; display_name: string; synthetic: true; readiness_answers: Record<string, ReadinessAnswer> }
  available_personas: Array<{ persona_id: string; display_name: string; synthetic: true; readiness_answers: Record<string, ReadinessAnswer> }>
  fields: Array<{
    field_id: string
    label: string
    explanation: string
    value: string | null
    handling: 'fictional_demo' | 'citizen_private' | 'not_collected'
    status: 'verified_official_form' | 'preparation_only'
    source_ids: string[]
    question_id: string | null
    question: string | null
    why_needed: string | null
    input_type: 'text' | 'textarea' | 'single_choice' | 'readiness_value' | 'document_clue' | 'not_collected' | null
    required: boolean | null
    validation_kind: 'non_empty_text' | 'single_choice' | 'structural' | 'not_collected' | null
    minimum_length: number | null
    maximum_length: number | null
    supported_value_sources: Array<'citizen_confirmed_local_answer' | 'citizen_confirmed_local_ocr_suggestion' | 'deterministic_derived_value' | 'bundled_synthetic_demonstration_profile'>
    may_appear_on_sheet: boolean | null
    confirmation_required: boolean | null
    editable: boolean | null
    choices: Array<{ option_id: string; label: string }>
    readiness_question_id: string | null
    document_ids: string[]
  }>
  sources: ProcedureSource[]
  watermark: string
  privacy_notice: string
  disclaimer: string
  official_handoff_url: string
  pack_version: string
  pack_digest: string
}
export type AssistantTurnResponse = {
  status: 'ok' | 'fallback' | 'blocked' | 'unavailable' | 'rate_limited'
  locale: Locale
  message: string
  selection: { state: 'none' | 'clarification' | 'selected'; service_id: string | null; choices: Array<{ service_id: string; title: string }> }
  fact_cards: Array<{ card_id: string; title: string; text: string; source_ids: string[] }>
  sources: ProcedureSource[]
  actions: Array<{ action_id: string; label: string; service_id: string | null }>
  tool_trace: string[]
  disclaimer: string
  fallback: boolean
}
export type ConfirmedDocumentEvidence = { document_id: string; appears_relevant: boolean; citizen_confirmed: true }
export type PublicJourneyState = {
  service_id: string | null
  candidate_service_ids: string[]
  confirmed: boolean
  answers: Record<string, ReadinessAnswer>
  current_question_id: string | null
  document_evidence: ConfirmedDocumentEvidence[]
  completed_field_ids: string[]
  current_preparation_question_id: string | null
}
export type ConversationUiAction = {
  action_id: 'confirm_service' | 'choose_service' | 'answer' | 'attach_document' | 'open_official_service' | 'browse_services'
  label: string
  service_id: string | null
  question_id: string | null
  value: ReadinessAnswer | null
}
export type ConversationTurnResponse = {
  status: 'ok' | 'blocked' | 'unsupported' | 'unavailable' | 'error'
  locale: Locale
  assistant_message: string
  next_action: 'confirm_service' | 'choose_service' | 'ask_user' | 'prepared' | 'official_handoff' | 'unsupported' | 'blocked' | 'error'
  progress_text: string | null
  actions: ConversationUiAction[]
  active_procedure: ProcedureSummary | null
  current_question: ReadinessQuestion | null
  current_preparation_question: SyntheticFormAssistance['fields'][number] | null
  readiness: ReadinessResponse | null
  checklist: PersonalizedChecklist | null
  preparation: SyntheticFormAssistance | null
  prepared_field_count: number
  preparation_field_count: number
  missing_required_field_ids: string[]
  document_helper_available: boolean
  accepted_document_evidence: ConfirmedDocumentEvidence[]
  contextual_sources: ProcedureSource[]
  official_handoff_url: string | null
  state: PublicJourneyState
  diagnostic_category: 'none' | 'pii_blocked' | 'invalid_state' | 'provider_unavailable' | 'provider_failure' | 'budget_exhausted'
}
export type DemoScenarioId = 'normal-completion' | 'action-required'
export type DemoStatusId = 'preparation-completed' | 'demo-submitted' | 'simulated-review' | 'action-required' | 'demo-completed'
export type DemoStatusItem = {
  status_id: DemoStatusId
  title: string
  explanation: string
  state: 'complete' | 'current' | 'upcoming'
  simulated_time_label: string
  next_action: string
  source_ids: string[]
}
export type DemoJourneyResponse = {
  locale: Locale
  service_id: string
  persona_id: string
  scenario_id: DemoScenarioId
  scenario_title: string
  demo_reference: string
  current_status_id: DemoStatusId
  statuses: DemoStatusItem[]
  can_advance: boolean
  synthetic: true
  disclosure: string
  disclaimer: string
}
const apiBase = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const localizedPath = (path: string, locale: Locale) => `${path}${path.includes('?') ? '&' : '?'}locale=${locale}`
async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> { const response = await fetch(`${apiBase}${path}`, { headers: { Accept: 'application/json' }, signal }); if (!response.ok) throw new Error('Service unavailable'); return response.json() as Promise<T> }
async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw new Error('Service unavailable')
  return response.json() as Promise<T>
}
export const getHealth = (signal?: AbortSignal) => getJson<HealthStatus>('/health', signal)
export const getPublicConfig = (signal?: AbortSignal) => getJson<PublicConfig>('/public-config', signal)
export const getProcedures = (locale: Locale = 'en', signal?: AbortSignal) => getJson<{ locale: Locale; translation: TranslationInfo; procedures: ProcedureSummary[] }>(localizedPath('/procedures', locale), signal)
export const getProcedure = (serviceId: string, locale: Locale = 'en', signal?: AbortSignal) => getJson<ProcedureDetail>(localizedPath(`/procedures/${encodeURIComponent(serviceId)}`, locale), signal)
export const evaluateReadiness = (serviceId: string, answers: Record<string, ReadinessAnswer>, locale: Locale = 'en', signal?: AbortSignal) =>
  postJson<ReadinessResponse>(localizedPath(`/procedures/${encodeURIComponent(serviceId)}/readiness/evaluate`, locale), { answers }, signal)
export const buildChecklist = (serviceId: string, answers: Record<string, ReadinessAnswer>, locale: Locale = 'en', signal?: AbortSignal) =>
  postJson<PersonalizedChecklist>(localizedPath(`/procedures/${encodeURIComponent(serviceId)}/checklist`, locale), { answers }, signal)
export const prepareSyntheticForm = (serviceId: string, locale: Locale = 'en', personaId: string | null = null, signal?: AbortSignal) =>
  postJson<SyntheticFormAssistance>(localizedPath(`/procedures/${encodeURIComponent(serviceId)}/synthetic-form-assistance`, locale), { persona_id: personaId }, signal)
export const startDemoSubmission = (serviceId: string, personaId: string, scenarioId: DemoScenarioId, locale: Locale = 'en', signal?: AbortSignal) =>
  postJson<DemoJourneyResponse>(localizedPath(`/procedures/${encodeURIComponent(serviceId)}/demo-submission`, locale), { persona_id: personaId, scenario_id: scenarioId }, signal)
export const getDemoStatus = (journey: DemoJourneyResponse, statusId: DemoStatusId, locale: Locale = journey.locale, signal?: AbortSignal) =>
  postJson<DemoJourneyResponse>(localizedPath(`/procedures/${encodeURIComponent(journey.service_id)}/demo-status`, locale), {
    persona_id: journey.persona_id,
    scenario_id: journey.scenario_id,
    demo_reference: journey.demo_reference,
    status_id: statusId,
  }, signal)
export const assistantTurn = (body: {
  locale: Locale
  message: string
  history: Array<{ role: 'user' | 'assistant'; content: string }>
  service_id: string | null
  readiness_answers: Record<string, ReadinessAnswer>
  demo_status_id: DemoStatusId | null
  consent: true
}, signal?: AbortSignal) => postJson<AssistantTurnResponse>('/assistant/turn', body, signal)
export const conversationTurn = (body: {
  locale: Locale
  event_type: 'start' | 'confirm_service' | 'answer' | 'field_completed' | 'document_evidence' | 'cloud_clarification'
  local_candidates?: Array<{ service_id: string; confidence: number }>
  confirmed_service_id?: string
  answer?: { question_id: string; value: ReadinessAnswer }
  document_evidence?: ConfirmedDocumentEvidence
  completed_field_id?: string
  message?: string
  consent?: boolean
  state?: PublicJourneyState
}, signal?: AbortSignal) => postJson<ConversationTurnResponse>('/conversation/turn', body, signal)
