import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { UI_MESSAGES } from './i18n'
import type { AssistantTurnResponse, ConversationTurnResponse, DemoJourneyResponse, DemoScenarioId, DemoStatusId, PersonalizedChecklist, ProcedureDetail, ProcedureSummary, PublicJourneyState, ReadinessResponse, SyntheticFormAssistance } from './api'

const englishTranslation = {
  locale: 'en' as const,
  canonical_locale: 'en' as const,
  method: 'canonical_source' as const,
  review_status: 'canonical_verified' as const,
  disclaimer: 'English is the canonical source language.',
}

const summary: ProcedureSummary = {
  service_id: 'uidai-aadhaar-address-update',
  title: 'Update your Aadhaar address online',
  short_description: 'Official UIDAI guidance for requesting an address update through the MyAadhaar portal.',
  intent_phrases: ['change Aadhaar address', 'update address in Aadhaar'],
  category: 'identity-documents', category_label: 'Identity documents', trust_state: 'current', attention_required: true,
}

const pensionSummary: ProcedureSummary = {
  service_id: 'kerala-ign-oap', title: 'Kerala Indira Gandhi National Old Age Pension',
  short_description: 'Verified Kerala guidance for a preliminary readiness check and local-body application.',
  intent_phrases: ['old age pension Kerala', 'Kerala senior pension'],
  category: 'social-security-pension', category_label: 'Social security pension', trust_state: 'current', attention_required: false,
}

const detail: ProcedureDetail = {
  ...summary,
  locale: 'en', translation: englishTranslation,
  official_publisher: 'Unique Identification Authority of India', interaction_modes: ['online'], pack_version: '1.2.0', last_verified_at: '2026-08-28T10:10:25+05:30', review_due_at: '2026-09-11T10:10:25+05:30',
  jurisdiction: { level: 'national', name: 'India' }, department: 'Unique Identification Authority of India',
  requirements: [{ fact_id: 'registered-mobile', text: 'Your mobile number must already be registered with Aadhaar.', source_ids: ['uidai-update-overview'] }],
  required_documents: [{ document_id: 'proof-of-address', name: 'Valid proof of address', guidance: 'Upload a clear colour scan of an accepted document.', source_ids: ['uidai-update-overview'] }],
  fee: {
    verification_status: 'conflicting', amount: null, currency: null,
    display_message: "Fee needs confirmation because UIDAI's official pages currently show different amounts for this service.",
    claims: [
      { amount: '50.00', currency: 'INR', qualifier: 'The online address-update FAQ states this amount, including GST.', source_ids: ['uidai-enrolment-update-faq'] },
      { amount: '75.00', currency: 'INR', qualifier: 'The My Aadhaar service entry displays this amount for address update.', source_ids: ['uidai-my-aadhaar-services'] },
    ],
    resolution_guidance: "UIDAI's official pages currently show different amounts for this service. Confirm the fee on the official portal before payment.",
    source_ids: ['uidai-enrolment-update-faq', 'uidai-my-aadhaar-services'],
  },
  steps: [{ step_id: 'open-portal', order: 1, title: 'Open the official portal', instruction: 'Continue on MyAadhaar.', source_ids: ['uidai-update-overview'] }],
  submission_channels: [{ channel_id: 'online', mode: 'online', name: 'MyAadhaar', guidance: 'Use the official portal.', source_ids: ['uidai-update-overview'] }],
  official_handoff_url: 'https://myaadhaar.uidai.gov.in/',
  tracking_guidance: { fact_id: 'tracking', text: 'Keep the SRN to check status.', source_ids: ['uidai-process'] },
  sources: [
    { source_id: 'uidai-update-overview', publisher: 'Unique Identification Authority of India', title: 'Updating Data on Aadhaar', url: 'https://uidai.gov.in/en/updating-data-on-aadhaar', retrieved_at: '2026-08-28T10:10:25+05:30', official_updated_date: '2026-07-03', sha256: null, source_type: 'webpage' },
    { source_id: 'uidai-enrolment-update-faq', publisher: 'Unique Identification Authority of India', title: 'Enrolment & Update: myAadhaar - Online Update Service FAQ', url: 'https://uidai.gov.in/en/enrolment-and-update', retrieved_at: '2026-08-28T10:10:25+05:30', official_updated_date: '2026-07-02', sha256: null, source_type: 'webpage' },
    { source_id: 'uidai-my-aadhaar-services', publisher: 'Unique Identification Authority of India', title: 'My Aadhaar', url: 'https://uidai.gov.in/en/my-aadhaar', retrieved_at: '2026-08-28T10:10:25+05:30', official_updated_date: '2026-06-26', sha256: null, source_type: 'webpage' },
  ],
  provenance: { fee: ['uidai-enrolment-update-faq', 'uidai-my-aadhaar-services'] }, pack_digest: 'a'.repeat(64),
  limitations: [{ fact_id: 'guidance-only', text: 'Sahayi is guidance only.', source_ids: ['uidai-update-overview'] }],
  additional_review_items: [],
  monitoring: { prototype_available: true, continuously_monitored: false, human_review_required: true, baseline_status: 'review_required', monitored_source_count: 3 },
}

const pensionDetail: ProcedureDetail = {
  ...detail, ...pensionSummary, official_publisher: 'Government of Kerala, Sevana Pension – Social Security System', interaction_modes: ['in_person'], pack_version: '1.0.0', last_verified_at: '2026-08-28T14:15:00+05:30', review_due_at: '2026-09-11T14:15:00+05:30', jurisdiction: { level: 'state', name: 'Kerala' }, department: 'Local Self Government Department, Government of Kerala',
  requirements: [{ fact_id: 'minimum-age', text: 'The official criteria state that the applicant must be age 60 or higher.', source_ids: ['kerala-sevana-criteria'] }],
  required_documents: [{ document_id: 'official-application-form', name: 'Official application form', guidance: 'Use the official application-form page.', source_ids: ['kerala-sevana-application-forms'] }],
  fee: { verification_status: 'not_stated', amount: null, currency: null, display_message: 'No application fee is stated in the official Kerala pages reviewed by Sahayi.', claims: [], resolution_guidance: null, source_ids: ['kerala-sevana-criteria'] },
  steps: [{ step_id: 'apply', order: 1, title: 'Apply through the local body', instruction: 'Use the official form.', source_ids: ['kerala-sevana-criteria'] }],
  submission_channels: [{ channel_id: 'local-body', mode: 'in_person', name: 'Local body of permanent residence', guidance: 'Confirm arrangements before visiting.', source_ids: ['kerala-sevana-criteria'] }],
  official_handoff_url: 'https://welfarepension.lsgkerala.gov.in/ApplicationFormsEng.aspx', tracking_guidance: null,
  sources: [{ source_id: 'kerala-sevana-criteria', publisher: 'Government of Kerala, Sevana Pension – Social Security System', title: 'Criteria for Allotting Indira Gandhi National Old Age Pension Scheme', url: 'https://welfarepension.lsgkerala.gov.in/FAQsEng.aspx?pentypeid=2', retrieved_at: '2026-08-28T14:15:00+05:30', official_updated_date: null, sha256: null, source_type: 'webpage' }, { source_id: 'kerala-sevana-application-forms', publisher: 'Government of Kerala, Sevana Pension – Social Security System', title: 'Social Security Pension – Application Forms', url: 'https://welfarepension.lsgkerala.gov.in/ApplicationFormsEng.aspx', retrieved_at: '2026-08-28T14:15:00+05:30', official_updated_date: null, sha256: null, source_type: 'webpage' }],
  provenance: { fee: ['kerala-sevana-criteria'] }, pack_digest: 'c'.repeat(64), limitations: [{ fact_id: 'guidance-only', text: 'Sahayi provides preliminary guidance only.', source_ids: ['kerala-sevana-criteria'] }],
  additional_review_items: [{ fact_id: 'respectful-review', text: 'The local body must respectfully review remaining official conditions.', source_ids: ['kerala-sevana-criteria'] }],
}

const response = (body: unknown) => Promise.resolve({ ok: true, json: async () => body })

class TestRecognition {
  static instance: TestRecognition | null = null
  lang = ''; continuous = false; interimResults = false
  onstart: (() => void) | null = null
  onresult: (() => void) | null = null
  onerror: ((event: { error?: string }) => void) | null = null
  onend: (() => void) | null = null
  constructor() { TestRecognition.instance = this }
  start() { this.onstart?.() }
  stop() { this.onend?.() }
  abort() { this.onend?.() }
}

const readinessSource = detail.sources[0]
const readinessStep = (question: NonNullable<ReadinessResponse['next_question']>, answered: number, total: number): ReadinessResponse => ({
  locale: 'en', translation: englishTranslation,
  pack_version: '1.2.0', pack_digest: 'b'.repeat(64), evaluation_status: 'incomplete', complete: false,
  progress: { answered, total }, next_question: question, outcome: null,
  reason_trace: [{ trace_type: 'question', trace_id: question.question_id, source_ids: [readinessSource.source_id] }],
  sources: [readinessSource], recommended_next_steps: [], official_handoff_url: null,
  disclaimer: 'This readiness check stores no answers and does not make an eligibility decision.',
})
const mobileQuestion: NonNullable<ReadinessResponse['next_question']> = { question_id: 'mobile-auth-access', prompt: 'Can you receive the mobile authentication required by UIDAI?', help_text: 'Do not enter a mobile number or OTP here.', answer_type: 'boolean', options: null, minimum: null, maximum: null, required: true, sensitivity: 'non_sensitive' }
const routeQuestion: NonNullable<ReadinessResponse['next_question']> = { question_id: 'address-update-route', prompt: 'Which official address-update route do you intend to use?', help_text: 'Choose without entering personal details.', answer_type: 'single_choice', options: [{ option_id: 'own-document', label: 'My own accepted proof of address' }, { option_id: 'head-of-family', label: 'A supported Head-of-Family route' }, { option_id: 'unsure', label: 'I am unsure' }], minimum: null, maximum: null, required: true, sensitivity: 'non_sensitive' }
const poaQuestion: NonNullable<ReadinessResponse['next_question']> = { question_id: 'accepted-poa-ready', prompt: 'Do you have an accepted proof-of-address document?', help_text: 'Do not upload or describe the document here.', answer_type: 'boolean', options: null, minimum: null, maximum: null, required: true, sensitivity: 'non_sensitive' }
const pensionSensitiveQuestion: NonNullable<ReadinessResponse['next_question']> = { question_id: 'family-income-category', prompt: 'Is annual family income within Rs. 1 lakh?', help_text: 'Choose only a category.', answer_type: 'single_choice', options: [{ option_id: 'within', label: 'Within Rs. 1 lakh' }, { option_id: 'prefer-not-to-answer', label: 'Prefer not to answer' }], minimum: null, maximum: null, required: true, sensitivity: 'sensitive' }
const completeReadiness: ReadinessResponse = {
  locale: 'en', translation: englishTranslation,
  pack_version: '1.2.0', pack_digest: 'b'.repeat(64), evaluation_status: 'ready', complete: true, progress: { answered: 3, total: 3 }, next_question: null,
  outcome: { outcome_id: 'own-document-ready', status: 'ready', title: 'You appear ready for the own-document route', explanation: 'Your choices indicate access to mobile authentication and an accepted proof-of-address route.' },
  reason_trace: [{ trace_type: 'rule', trace_id: 'own-document-ready', source_ids: [readinessSource.source_id] }], sources: [readinessSource],
  recommended_next_steps: ['Review UIDAI accepted-document guidance.', 'Continue on the official service.'], official_handoff_url: 'https://myaadhaar.uidai.gov.in/',
  disclaimer: 'This readiness result is personalised guidance, not an eligibility decision or official approval.',
}

const agentReply: AssistantTurnResponse = {
  status: 'ok', locale: 'en', message: 'Choose the verified Aadhaar path.',
  selection: { state: 'selected', service_id: summary.service_id, choices: [] },
  fact_cards: [{ card_id: 'fee-information', title: 'Fee information', text: 'Fee needs confirmation on the official portal.', source_ids: ['uidai-update-overview'] }],
  sources: [readinessSource], actions: [{ action_id: 'start-readiness', label: 'Start deterministic readiness check', service_id: summary.service_id }],
  tool_trace: ['get_verified_procedure'], disclaimer: 'AI guidance is a prototype and never an approval.', fallback: false,
}

const checklistFixture: PersonalizedChecklist = {
  locale: 'en', translation: englishTranslation, service_id: summary.service_id, title: summary.title, pack_version: '1.4.0', pack_digest: 'd'.repeat(64),
  result: { item_id: 'result-ready', text: 'Ready for the demonstrated path.', source_ids: ['uidai-update-overview'] },
  ready: [{ item_id: 'ready-one', text: 'Use the verified official path.', source_ids: ['uidai-update-overview'] }],
  documents: detail.required_documents, confirm: [{ item_id: 'confirm-fee', text: 'Confirm the fee before paying.', source_ids: ['uidai-update-overview'] }],
  steps: [{ item_id: 'step-open', text: 'Open the official service.', source_ids: ['uidai-update-overview'] }], warnings: [], where: [], sources: [readinessSource],
  not_verified: [{ item_id: 'not-verified', text: 'Approval is not verified.', source_ids: ['uidai-update-overview'] }], official_handoff_url: detail.official_handoff_url,
  disclaimer: 'Preparation guidance only.',
}

const formFixture: SyntheticFormAssistance = {
  locale: 'en', translation: englishTranslation, service_id: summary.service_id, title: 'Aadhaar preparation worksheet', mode: 'preparation_worksheet',
  persona: { persona_id: 'fictional-demo', display_name: 'DEMO — fictional citizen', synthetic: true, readiness_answers: { 'mobile-auth-access': true } },
  available_personas: [{ persona_id: 'fictional-demo', display_name: 'DEMO — fictional citizen', synthetic: true, readiness_answers: { 'mobile-auth-access': true } }],
  fields: [
    {
      field_id: 'update-route', label: 'Planned update route', explanation: 'Derived from readiness.', value: null, handling: 'fictional_demo', status: 'preparation_only', source_ids: ['uidai-update-overview'],
      question_id: 'prepare-update-route', question: 'Which route?', why_needed: 'Determines the verified route.', input_type: 'readiness_value', required: true,
      validation_kind: 'structural', minimum_length: null, maximum_length: null, supported_value_sources: ['deterministic_derived_value'], may_appear_on_sheet: true, confirmation_required: true, editable: true,
      choices: [], readiness_question_id: 'address-update-route', document_ids: [],
    },
    {
      field_id: 'new-address', label: 'New address', explanation: 'Kept locally.', value: null, handling: 'citizen_private', status: 'preparation_only', source_ids: ['uidai-update-overview'],
      question_id: 'prepare-new-address', question: 'What new address should your preparation sheet show?', why_needed: 'Review it locally before official action.', input_type: 'textarea', required: true,
      validation_kind: 'non_empty_text', minimum_length: 5, maximum_length: 240, supported_value_sources: ['citizen_confirmed_local_answer', 'citizen_confirmed_local_ocr_suggestion'], may_appear_on_sheet: true, confirmation_required: true, editable: true,
      choices: [], readiness_question_id: null, document_ids: [],
    },
    {
      field_id: 'aadhaar-number', label: 'Aadhaar number', explanation: 'Citizen must provide privately.', value: null, handling: 'not_collected', status: 'preparation_only', source_ids: ['uidai-update-overview'],
      question_id: 'prepare-aadhaar-number', question: 'Aadhaar number', why_needed: 'Use only on the official service.', input_type: 'not_collected', required: false,
      validation_kind: 'not_collected', minimum_length: null, maximum_length: null, supported_value_sources: [], may_appear_on_sheet: true, confirmation_required: false, editable: false,
      choices: [], readiness_question_id: null, document_ids: [],
    },
  ],
  sources: [readinessSource], watermark: 'DEMO — NOT FOR SUBMISSION', privacy_notice: 'Identifiers are not collected.', disclaimer: 'Preparation only.',
  official_handoff_url: detail.official_handoff_url, pack_version: '1.4.0', pack_digest: 'd'.repeat(64),
}

const emptyJourneyState = (): PublicJourneyState => ({
  service_id: null,
  candidate_service_ids: [],
  confirmed: false,
  answers: {},
  current_question_id: null,
  document_evidence: [],
  completed_field_ids: [],
  current_preparation_question_id: null,
})

const graphTurn = ({
  state,
  procedure = null,
  readiness = null,
  checklist = null,
  preparation = null,
  preparationQuestion = null,
  message = 'Continue one step at a time.',
}: {
  state: PublicJourneyState
  procedure?: ProcedureSummary | null
  readiness?: ReadinessResponse | null
  checklist?: PersonalizedChecklist | null
  preparation?: SyntheticFormAssistance | null
  preparationQuestion?: SyntheticFormAssistance['fields'][number] | null
  message?: string
}): ConversationTurnResponse => ({
  status: 'ok',
  locale: 'en',
  assistant_message: message,
  next_action: preparationQuestion ? 'ask_user' : readiness?.complete ? 'official_handoff' : readiness?.next_question ? 'ask_user' : 'confirm_service',
  progress_text: readiness ? `${readiness.progress.answered} of ${readiness.progress.total}` : null,
  actions: [],
  active_procedure: procedure,
  current_question: readiness?.next_question ?? null,
  current_preparation_question: preparationQuestion,
  readiness,
  checklist,
  preparation,
  prepared_field_count: state.completed_field_ids.length,
  preparation_field_count: preparation?.fields.length ?? 0,
  missing_required_field_ids: preparationQuestion ? [preparationQuestion.field_id] : [],
  document_helper_available: readiness?.next_question?.question_id === 'accepted-poa-ready',
  accepted_document_evidence: state.document_evidence,
  contextual_sources: readiness?.sources ?? [],
  official_handoff_url: preparationQuestion ? null : readiness?.official_handoff_url ?? null,
  state,
  diagnostic_category: 'none',
})

const demoSequences: Record<DemoScenarioId, DemoStatusId[]> = {
  'normal-completion': ['preparation-completed', 'demo-submitted', 'simulated-review', 'demo-completed'],
  'action-required': ['preparation-completed', 'demo-submitted', 'simulated-review', 'action-required', 'demo-completed'],
}
const demoJourney = (scenario: DemoScenarioId, current: DemoStatusId = 'preparation-completed', locale = 'en'): DemoJourneyResponse => ({
  locale: locale as DemoJourneyResponse['locale'], service_id: summary.service_id, persona_id: 'fictional-demo', scenario_id: scenario,
  scenario_title: scenario === 'normal-completion' ? 'Normal demo completion' : 'Demo with action required',
  demo_reference: scenario === 'normal-completion' ? 'DEMO-UIDAI-NORMAL' : 'DEMO-UIDAI-ACTION', current_status_id: current,
  statuses: demoSequences[scenario].map((status, index, all) => ({
    status_id: status, title: status === 'action-required' ? 'Action required' : status.split('-').map(word => word[0].toUpperCase() + word.slice(1)).join(' '),
    explanation: `Synthetic explanation for ${status}.`, state: index < all.indexOf(current) ? 'complete' : index === all.indexOf(current) ? 'current' : 'upcoming',
    simulated_time_label: `SIMULATED — step ${index + 1} of ${all.length}`, next_action: 'Advance deliberately.', source_ids: status === 'preparation-completed' ? ['uidai-update-overview'] : [],
  })), can_advance: current !== 'demo-completed', synthetic: true,
  disclosure: 'Simulation only: no application is submitted, no government system is contacted, and only bundled synthetic data is used.',
  disclaimer: 'Synthetic status demonstration only. This is not a government acknowledgement, approval, submission, or tracking service.',
})

function mockApi(options: { procedures?: ProcedureSummary[]; procedure?: ProcedureDetail; readinessInitial?: ReadinessResponse; failCatalogue?: boolean; failDetail?: boolean; failReadiness?: boolean; pendingDetail?: boolean; agentAvailable?: boolean; agentReply?: AssistantTurnResponse; inactivityTimeout?: number; inactivityWarning?: number } = {}) {
  const fetchMock = vi.fn((input: string | URL | Request, init?: RequestInit) => {
    const url = String(input)
    const parsed = new URL(url, 'http://test')
    if (parsed.pathname.endsWith('/health')) return response({ status: 'ok' })
    if (parsed.pathname.endsWith('/public-config')) return response({ application_name: 'Sahayi', kiosk_mode: true, agent_available: options.agentAvailable ?? false, agent_provider: 'groq', agent_model: 'openai/gpt-oss-120b', inactivity_timeout_seconds: options.inactivityTimeout ?? 300, inactivity_warning_seconds: options.inactivityWarning ?? 30 })
    if (parsed.pathname.endsWith('/conversation/turn')) {
      if (options.failReadiness) return Promise.reject(new Error('offline'))
      const body = JSON.parse(String(init?.body)) as {
        event_type: 'start' | 'confirm_service' | 'answer' | 'field_completed' | 'document_evidence'
        confirmed_service_id?: string
        local_candidates?: Array<{ service_id: string }>
        answer?: { question_id: string; value: boolean | number | string }
        document_evidence?: { document_id: string; appears_relevant: boolean; citizen_confirmed: true }
        completed_field_id?: string
        state?: PublicJourneyState
      }
      if (body.event_type === 'start') {
        const candidateIds = body.local_candidates?.map(candidate => candidate.service_id) ?? []
        return response(graphTurn({
          state: { ...emptyJourneyState(), candidate_service_ids: candidateIds },
          procedure: null,
          message: 'Please confirm the service before continuing.',
        }))
      }
      const serviceId = body.confirmed_service_id ?? body.state?.service_id ?? summary.service_id
      const activeSummary = serviceId === pensionSummary.service_id ? pensionSummary : summary
      if (body.event_type === 'confirm_service') {
        const initial = options.readinessInitial ?? readinessStep(serviceId === pensionSummary.service_id ? pensionSensitiveQuestion : mobileQuestion, 0, 1)
        return response(graphTurn({
          state: { ...emptyJourneyState(), service_id: serviceId, confirmed: true, current_question_id: initial.next_question?.question_id ?? null },
          procedure: activeSummary,
          readiness: initial,
          preparation: formFixture,
          message: initial.next_question?.prompt,
        }))
      }
      if (body.event_type === 'field_completed') {
        const completed = [...new Set([...(body.state?.completed_field_ids ?? []), body.completed_field_id!])]
        return response(graphTurn({
          state: { ...(body.state ?? emptyJourneyState()), completed_field_ids: completed, current_preparation_question_id: null },
          procedure: activeSummary,
          readiness: completeReadiness,
          checklist: checklistFixture,
          preparation: formFixture,
          message: 'Your preparation is ready.',
        }))
      }
      if (body.event_type === 'document_evidence') {
        const evidence = body.document_evidence ? [...(body.state?.document_evidence ?? []), body.document_evidence] : body.state?.document_evidence ?? []
        const current = readinessStep(poaQuestion, Object.keys(body.state?.answers ?? {}).length, 3)
        return response(graphTurn({
          state: { ...(body.state ?? emptyJourneyState()), document_evidence: evidence },
          procedure: activeSummary,
          readiness: current,
          message: current.next_question?.prompt,
        }))
      }
      const answers = { ...(body.state?.answers ?? {}), ...(body.answer ? { [body.answer.question_id]: body.answer.value } : {}) }
      let next: ReadinessResponse
      if (body.answer?.question_id === pensionSensitiveQuestion.question_id) {
        next = { ...completeReadiness, evaluation_status: 'alternative_path', outcome: { ...completeReadiness.outcome!, outcome_id: 'use-alternative-channel', status: 'alternative_path', title: 'Use an alternative official channel' } }
      } else if (answers['mobile-auth-access'] === true && !answers['address-update-route']) next = readinessStep(routeQuestion, 1, 2)
      else if (answers['address-update-route'] === 'own-document' && !('accepted-poa-ready' in answers)) next = readinessStep(poaQuestion, 2, 3)
      else if (answers['accepted-poa-ready'] === true) next = completeReadiness
      else next = { ...completeReadiness, evaluation_status: 'alternative_path', outcome: { ...completeReadiness.outcome!, outcome_id: 'use-alternative-channel', status: 'alternative_path', title: 'Use an alternative official channel' } }
      const nextState: PublicJourneyState = {
        ...(body.state ?? emptyJourneyState()),
        service_id: serviceId,
        confirmed: true,
        answers,
        current_question_id: next.next_question?.question_id ?? null,
        current_preparation_question_id: next.complete ? 'prepare-new-address' : null,
      }
      return response(graphTurn({
        state: nextState,
        procedure: activeSummary,
        readiness: next,
        checklist: checklistFixture,
        preparation: formFixture,
        preparationQuestion: next.complete ? formFixture.fields[1] : null,
        message: next.next_question?.prompt ?? 'Your preparation is ready.',
      }))
    }
    if (parsed.pathname.endsWith('/assistant/turn')) return response(options.agentReply ?? agentReply)
    if (parsed.pathname.endsWith('/demo-submission')) {
      const body = JSON.parse(String(init?.body)) as { scenario_id: DemoScenarioId }
      return response(demoJourney(body.scenario_id, 'preparation-completed', parsed.searchParams.get('locale') ?? 'en'))
    }
    if (parsed.pathname.endsWith('/demo-status')) {
      const body = JSON.parse(String(init?.body)) as { scenario_id: DemoScenarioId; status_id: DemoStatusId }
      return response(demoJourney(body.scenario_id, body.status_id, parsed.searchParams.get('locale') ?? 'en'))
    }
    if (parsed.pathname.endsWith('/checklist')) return response(checklistFixture)
    if (parsed.pathname.endsWith('/synthetic-form-assistance')) return response(formFixture)
    if (parsed.pathname.endsWith('/procedures')) return options.failCatalogue ? Promise.reject(new Error('offline')) : response({ locale: parsed.searchParams.get('locale') ?? 'en', translation: englishTranslation, procedures: options.procedures ?? [summary] })
    if (parsed.pathname.endsWith('/readiness/evaluate')) {
      if (options.failReadiness) return Promise.reject(new Error('offline'))
      const answers = JSON.parse(String(init?.body)).answers as Record<string, unknown>
      if (Object.keys(answers).length === 0) return response(options.readinessInitial ?? readinessStep(mobileQuestion, 0, 1))
      if (answers['mobile-auth-access'] === true && !answers['address-update-route']) return response(readinessStep(routeQuestion, 1, 2))
      if (answers['address-update-route'] === 'own-document' && !('accepted-poa-ready' in answers)) return response(readinessStep(poaQuestion, 2, 3))
      if (answers['accepted-poa-ready'] === true) return response(completeReadiness)
      return response({ ...completeReadiness, evaluation_status: 'alternative_path', outcome: { ...completeReadiness.outcome, outcome_id: 'use-alternative-channel', status: 'alternative_path', title: 'Use an alternative official channel' } })
    }
    if (parsed.pathname.includes('/procedures/')) {
      if (options.pendingDetail) return new Promise((_resolve, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))))
      const requestedProcedure = parsed.pathname.includes(pensionSummary.service_id) ? pensionDetail : detail
      return options.failDetail ? Promise.reject(new Error('offline')) : response(options.procedure ?? requestedProcedure)
    }
    return Promise.reject(new Error(`Unexpected request: ${url}`))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function openCatalogue() {
  await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Start' }))
  await screen.findByRole('heading', { name: 'What do you need help with?' })
  fireEvent.click(screen.getAllByRole('button', { name: 'Browse all services' }).at(-1)!)
  await screen.findByRole('heading', { name: 'Supported services' })
}

async function openProcedure() {
  await openCatalogue()
  fireEvent.click(await screen.findByRole('button', { name: /Update your Aadhaar address online/ }))
  await screen.findByRole('heading', { name: 'Update your Aadhaar address online' })
}

async function openAssistant() {
  await openProcedure()
  fireEvent.click(screen.getByRole('button', { name: 'Ask Sahayi AI' }))
  await screen.findByRole('heading', { name: 'Ask Sahayi AI' })
}

describe('Sahayi verified procedure flow', () => {
  beforeEach(() => vi.restoreAllMocks())
  afterEach(() => { vi.useRealTimers(); delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition; TestRecognition.instance = null })

  it('renders the welcome content and loading state', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Sahayi' })).toBeInTheDocument()
    expect(screen.getByText('Government services, explained around what you need.')).toBeInTheDocument()
    expect(screen.getByText('Need help?')).toBeInTheDocument()
    expect(screen.getByText('Checking service availability…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start' })).toBeDisabled()
  })

  it('enables Start and opens the populated service catalogue', async () => {
    mockApi()
    render(<App />)
    await openCatalogue()
    expect(screen.getByRole('button', { name: /Update your Aadhaar address online/ })).toBeInTheDocument()
    expect(screen.getByText(/Official UIDAI guidance/)).toBeInTheDocument()
    expect(screen.getByText('Fee needs confirmation')).toBeInTheDocument()
  })

  it('opens the conversation directly without a service-card wall', async () => {
    mockApi({ procedures: [summary, pensionSummary] })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    expect(await screen.findByRole('heading', { name: 'What do you need help with?' })).toBeInTheDocument()
    expect(document.querySelectorAll('.service-card')).toHaveLength(0)
    expect(document.querySelector('.citizen-progress')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'What do you need help with?' })).toHaveFocus()
  })

  it('offers exactly three accessible languages, updates document language, and keeps the choice in memory across Start Over', async () => {
    const fetchMock = mockApi()
    render(<App />)
    const selector = screen.getByLabelText('Language')
    expect(within(selector).getAllByRole('option').map(option => option.textContent)).toEqual(['English', 'हिन्दी', 'മലയാളം'])
    fireEvent.change(selector, { target: { value: 'hi' } })
    expect(document.documentElement.lang).toBe('hi')
    expect(screen.getByText('आपकी ज़रूरत के अनुसार समझाई गई सरकारी सेवाएँ।')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('मशीन-सहायित प्रोटोटाइप')
    fireEvent.click(await screen.findByRole('button', { name: 'शुरू करें' }))
    await screen.findByRole('heading', { name: 'आपको किस काम में मदद चाहिए?' })
    expect(fetchMock.mock.calls.some(call => String(call[0]).endsWith('/procedures?locale=hi'))).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'फिर से शुरू करें' }))
    expect(screen.getByLabelText('भाषा')).toHaveValue('hi')
    fireEvent.change(screen.getByLabelText('भाषा'), { target: { value: 'ml' } })
    expect(document.documentElement.lang).toBe('ml')
    expect(screen.getByText('നിങ്ങളുടെ ആവശ്യം അടിസ്ഥാനമാക്കി വിശദീകരിച്ച സർക്കാർ സേവനങ്ങൾ.')).toBeInTheDocument()
  })

  it('keeps text available when voice is unsupported and reports microphone denial without breaking conversation', async () => {
    mockApi()
    const view = render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    expect(await screen.findByRole('button', { name: 'Use microphone' })).toBeDisabled()
    expect(screen.getByText(/Voice input is unavailable/)).toBeInTheDocument()
    expect(screen.getByLabelText('Tell us what service you need')).toBeEnabled()
    view.unmount()

    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: TestRecognition })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Use microphone' }))
    act(() => TestRecognition.instance?.onerror?.({ error: 'not-allowed' }))
    expect(screen.getByText(/Microphone permission was denied/)).toBeInTheDocument()
    expect(screen.getByLabelText('Tell us what service you need')).toBeEnabled()
  })

  it('renders both services and Kerala form, destination, respectful review, and sensitive-choice guidance', async () => {
    mockApi({ procedures: [summary, pensionSummary], procedure: pensionDetail, readinessInitial: readinessStep(pensionSensitiveQuestion, 0, 1) })
    render(<App />)
    await openCatalogue()
    fireEvent.click(screen.getByRole('button', { name: /Kerala Indira Gandhi National Old Age Pension/ }))
    await screen.findByRole('heading', { name: pensionDetail.title })
    expect(screen.getByRole('link', { name: /Social Security Pension.*Application Forms/ })).toHaveAttribute('href', pensionDetail.official_handoff_url)
    expect(screen.getByText('Local body of permanent residence')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Additional local-body review' })).toBeInTheDocument()
    expect(screen.getByText(/No application fee is stated/)).toBeInTheDocument()
    expect(screen.queryByText(/₹2,000|₹2000/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Check what you need' }))
    fireEvent.click(screen.getByRole('button', { name: 'Begin readiness check' }))
    expect(await screen.findByText('Privacy:')).toBeInTheDocument()
    expect(screen.getByText(/You may select “Prefer not to answer”/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'Prefer not to answer' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByRole('heading', { name: 'Use an alternative official channel' })).toBeInTheDocument()
    expect(screen.getByText(/not an eligibility decision or official approval/)).toBeInTheDocument()
  })

  it('selects the service and shows trust-card provenance', async () => {
    mockApi()
    render(<App />)
    await openProcedure()
    expect(screen.getByRole('heading', { name: 'Your Sahayi journey' })).toBeInTheDocument()
    expect(screen.getAllByText('Update your Aadhaar address online').length).toBeGreaterThan(1)
    expect(screen.getByText('How Sahayi prepared this')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Verified official guidance' })).toBeInTheDocument()
    expect(screen.getAllByText('Unique Identification Authority of India').length).toBeGreaterThan(0)
    expect(screen.getByText('1.2.0')).toBeInTheDocument()
    expect(screen.getByText('28 Aug 2026')).toBeInTheDocument()
    expect(screen.getByText('One-shot only — not continuously monitored')).toBeInTheDocument()
    fireEvent.click(screen.getByText('How Sahayi protects trust and privacy'))
    expect(screen.getByText(/active facts are never silently replaced/)).toBeInTheDocument()
    const source = screen.getByRole('link', { name: /Updating Data on Aadhaar/ })
    expect(source).toHaveAttribute('target', '_blank')
    expect(source).toHaveAttribute('rel', 'noopener noreferrer')
    fireEvent.click(screen.getByText('Procedure Intelligence demonstration'))
    expect(screen.getByText('Potential change quarantined')).toBeInTheDocument()
    expect(screen.getByText('Approved Procedure Pack remains active')).toBeInTheDocument()
  })

  it('labels the official handoff and applies external-link safety', async () => {
    mockApi()
    render(<App />)
    await openProcedure()
    const handoff = screen.getByRole('link', { name: /Open the official service/ })
    expect(handoff).toHaveAttribute('href', 'https://myaadhaar.uidai.gov.in/')
    expect(handoff).toHaveAttribute('target', '_blank')
    expect(handoff).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByText(/It is not the official service or a government service/)).toBeInTheDocument()
  })

  it('shows a prominent stale warning', async () => {
    mockApi({ procedure: { ...detail, trust_state: 'stale' } })
    render(<App />)
    await openProcedure()
    expect(screen.getAllByRole('alert').some(alert => alert.textContent?.includes('This guidance needs review'))).toBe(true)
    expect(screen.getByText('Stale — review overdue')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Fee needs confirmation' })).toBeInTheDocument()
  })

  it('shows an accessible conflict warning with both source-attributed claims', async () => {
    mockApi()
    render(<App />)
    await openProcedure()
    const warning = screen.getByRole('alert')
    expect(warning).toHaveAccessibleName('Fee needs confirmation')
    expect(warning).toHaveTextContent("UIDAI's official pages currently show different amounts")
    expect(warning).toHaveTextContent('₹50')
    expect(warning).toHaveTextContent('₹75')
    expect(within(warning).getByRole('link', { name: /Online Update Service FAQ/ })).toHaveAttribute('href', 'https://uidai.gov.in/en/enrolment-and-update')
    expect(within(warning).getByRole('link', { name: 'My Aadhaar' })).toHaveAttribute('href', 'https://uidai.gov.in/en/my-aadhaar')
    expect(warning).toHaveTextContent('Confirm the fee on the official portal before payment')
    expect(warning).not.toHaveTextContent(/(?:official|current|recommended) fee is ₹(?:50|75)/i)
    expect(screen.queryByRole('heading', { name: 'Current fee' })).not.toBeInTheDocument()
  })

  it('handles backend failure and an empty catalogue', async () => {
    mockApi({ failCatalogue: true })
    const { unmount } = render(<App />)
    await openCatalogue()
    expect(await screen.findByRole('alert')).toHaveTextContent('We could not load services')

    unmount()
    vi.restoreAllMocks()
    mockApi({ procedures: [] })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Browse all services' }))
    expect(await screen.findByText('No procedures are available')).toBeInTheDocument()
  })

  it('provides Back and Start Over controls', async () => {
    mockApi()
    render(<App />)
    await openProcedure()
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByRole('heading', { name: 'Supported services' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start Over' }))
    expect(screen.getByRole('heading', { name: 'Sahayi' })).toBeInTheDocument()
  })

  it('does not introduce browser persistence', async () => {
    const storageWrite = vi.spyOn(Storage.prototype, 'setItem')
    mockApi()
    render(<App />)
    fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'hi' } })
    fireEvent.change(screen.getByLabelText('भाषा'), { target: { value: 'en' } })
    await openProcedure()
    expect(storageWrite).not.toHaveBeenCalled()
  })

  it('introduces the private readiness check from the procedure page', async () => {
    mockApi()
    render(<App />)
    await openProcedure()
    fireEvent.click(screen.getByRole('button', { name: 'Check what you need' }))
    expect(screen.getByRole('heading', { name: 'Check what you need' })).toBeInTheDocument()
    expect(screen.getByText(/does not store or submit your answers/i)).toBeInTheDocument()
    expect(screen.getByText(/not an eligibility decision/i)).toBeInTheDocument()
    expect(screen.queryByText(mobileQuestion.prompt)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByRole('heading', { name: 'Update your Aadhaar address online' })).toBeInTheDocument()
  })

  it('asks one conditional question per screen with progress and validation', async () => {
    mockApi()
    render(<App />)
    await openProcedure()
    fireEvent.click(screen.getByRole('button', { name: 'Check what you need' }))
    fireEvent.click(screen.getByRole('button', { name: 'Begin readiness check' }))
    expect(await screen.findByRole('heading', { name: mobileQuestion.prompt })).toHaveFocus()
    expect(screen.getByRole('status')).toHaveTextContent('Question 1 of 1')
    expect(screen.queryByText(routeQuestion.prompt)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose an answer')
    fireEvent.click(screen.getByRole('radio', { name: 'Yes' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByRole('heading', { name: routeQuestion.prompt })).toHaveFocus()
    expect(screen.queryByText(mobileQuestion.prompt)).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Question 2 of 2')
  })

  it('supports Back and Start Over while clearing answers', async () => {
    const fetchMock = mockApi()
    render(<App />)
    await openProcedure()
    fireEvent.click(screen.getByRole('button', { name: 'Check what you need' }))
    fireEvent.click(screen.getByRole('button', { name: 'Begin readiness check' }))
    fireEvent.click(await screen.findByRole('radio', { name: 'Yes' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    await screen.findByRole('heading', { name: routeQuestion.prompt })
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(await screen.findByRole('heading', { name: mobileQuestion.prompt })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start Over' }))
    expect(screen.getByRole('heading', { name: 'Sahayi' })).toBeInTheDocument()
    const postedBodies = fetchMock.mock.calls.filter(call => new URL(String(call[0]), 'http://test').pathname.endsWith('/readiness/evaluate')).map(call => JSON.parse(String(call[1]?.body)))
    expect(postedBodies.at(-1)).toEqual({ answers: {} })
  })

  it('shows completed cited reasoning, next steps, and the non-approval disclaimer', async () => {
    const fetchMock = mockApi()
    render(<App />)
    await openProcedure()
    fireEvent.click(screen.getByRole('button', { name: 'Check what you need' }))
    fireEvent.click(screen.getByRole('button', { name: 'Begin readiness check' }))
    fireEvent.click(await screen.findByRole('radio', { name: 'Yes' })); fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(await screen.findByRole('radio', { name: 'My own accepted proof of address' })); fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(await screen.findByRole('radio', { name: 'Yes' })); fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    const resultHeading = await screen.findByRole('heading', { name: completeReadiness.outcome?.title })
    await waitFor(() => expect(resultHeading).toHaveFocus())
    expect(screen.getByText(completeReadiness.outcome?.explanation ?? '')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Updating Data on Aadhaar/ })).toHaveAttribute('href', readinessSource.url)
    expect(screen.getByText(/personalised guidance, not an eligibility decision or official approval/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open the official next step/ })).toHaveAttribute('rel', 'noopener noreferrer')
    await waitFor(() => expect(fetchMock.mock.calls.some(call => String(call[0]).includes('/checklist'))).toBe(true))
  })

  it('handles readiness backend failure without exposing an answer', async () => {
    mockApi({ failReadiness: true })
    render(<App />)
    await openProcedure()
    fireEvent.click(screen.getByRole('button', { name: 'Check what you need' }))
    fireEvent.click(screen.getByRole('button', { name: 'Begin readiness check' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable')
    expect(screen.getByRole('heading', { name: 'Check what you need' })).toBeInTheDocument()
  })

  it('starts with empty readiness state after a fresh mount', async () => {
    mockApi()
    const first = render(<App />)
    await openProcedure()
    fireEvent.click(screen.getByRole('button', { name: 'Check what you need' }))
    fireEvent.click(screen.getByRole('button', { name: 'Begin readiness check' }))
    expect(await screen.findByRole('heading', { name: mobileQuestion.prompt })).toBeInTheDocument()
    first.unmount()
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sahayi' })).toBeInTheDocument())
    expect(screen.queryByText(mobileQuestion.prompt)).not.toBeInTheDocument()
  })

  it('keeps a natural-language query in the browser, suggests Aadhaar, and clears it on confirmation', async () => {
    const fetchMock = mockApi({ procedures: [summary, pensionSummary] })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    const query = await screen.findByLabelText('Tell us what service you need')
    fireEvent.change(query, { target: { value: 'I moved recently and want to update my Aadhaar address.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(/Is this the service you mean\?/)).toHaveTextContent(summary.title)
    for (const [url, init] of fetchMock.mock.calls) {
      expect(String(url)).not.toContain('moved recently')
      expect(String(init?.body ?? '')).not.toContain('moved recently')
    }
    fireEvent.click(screen.getByRole('button', { name: 'Yes, continue' }))
    expect(await screen.findByText(mobileQuestion.prompt)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'What do you need help with?' })).toBeInTheDocument()
    expect(screen.queryByDisplayValue(/moved recently/)).not.toBeInTheDocument()
  })

  it('keeps the deterministic journey in one conversation and prepares the checklist, worksheet, and verified handoff automatically', async () => {
    const fetchMock = mockApi({ procedures: [summary, pensionSummary] })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    fireEvent.change(await screen.findByLabelText('Tell us what service you need'), { target: { value: 'I need to change my Aadhaar address' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, continue' }))
    expect(await screen.findByText(mobileQuestion.prompt)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }))
    expect(await screen.findByText(routeQuestion.prompt)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'My own accepted proof of address' }))
    expect(await screen.findByText(poaQuestion.prompt)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }))
    expect(await screen.findByRole('heading', { name: completeReadiness.outcome?.title })).toBeInTheDocument()
    expect(screen.getAllByText(completeReadiness.outcome?.explanation ?? '')).toHaveLength(1)
    expect(await screen.findByText('What new address should your preparation sheet show?')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Open the official service/ })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('New address'), { target: { value: 'Synthetic Demo Local Address' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and continue' }))
    expect(await screen.findByText('DEMO — NOT FOR SUBMISSION')).toBeInTheDocument()
    expect(screen.getByText('Review prepared information')).toBeInTheDocument()
    expect(screen.getByText('Ready for the demonstrated path.')).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /Open the official service/ })).toHaveAttribute('href', detail.official_handoff_url)
    expect(screen.getAllByText('Synthetic Demo Local Address')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Edit answer' }))
    fireEvent.change(screen.getByLabelText('New address'), { target: { value: 'Edited Synthetic Local Address' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save edit' }))
    expect(screen.getByText('Edited Synthetic Local Address')).toBeInTheDocument()
    const fieldCall = fetchMock.mock.calls.find(call => String(call[0]).endsWith('/conversation/turn') && String(call[1]?.body).includes('field_completed'))
    expect(fieldCall).toBeDefined()
    expect(String(fieldCall?.[1]?.body)).not.toContain('Synthetic Demo Local Address')
    expect(screen.getByRole('heading', { name: 'What do you need help with?' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(call => String(call[0]).endsWith('/conversation/turn'))).toBe(true)
    expect(fetchMock.mock.calls.some(call => String(call[0]).includes('/checklist'))).toBe(false)
    expect(fetchMock.mock.calls.some(call => String(call[0]).includes('/synthetic-form-assistance'))).toBe(false)
  })

  it('routes the Kerala pension request and asks only its next pack-owned question', async () => {
    const fetchMock = mockApi({ procedures: [summary, pensionSummary] })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    fireEvent.change(await screen.findByLabelText('Tell us what service you need'), { target: { value: 'My mother is 67 and I want to know if she can get pension.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(new RegExp(pensionSummary.title))).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Yes, continue' }))
    expect(await screen.findByText(pensionSensitiveQuestion.prompt)).toBeInTheDocument()
    expect(screen.queryByText(mobileQuestion.prompt)).not.toBeInTheDocument()
    const graphCalls = fetchMock.mock.calls.filter(call => String(call[0]).endsWith('/conversation/turn'))
    expect(graphCalls).toHaveLength(2)
    expect(JSON.parse(String(graphCalls[1][1]?.body)).confirmed_service_id).toBe(pensionSummary.service_id)
    expect(document.body).not.toHaveTextContent(/eligible|approved/i)
  })

  it('clears the unified conversation and active task with Start Over and End session', async () => {
    mockApi({ procedures: [summary, pensionSummary] })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    fireEvent.change(await screen.findByLabelText('Tell us what service you need'), { target: { value: 'change Aadhaar address' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(/Is this the service you mean/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start Over' }))
    expect(screen.getByRole('heading', { name: 'Sahayi' })).toBeInTheDocument()
    expect(screen.queryByText(/Is this the service you mean/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    fireEvent.click(await screen.findByRole('button', { name: 'End session' }))
    expect(screen.getByText(/cleared all in-memory session data/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Tell us what service you need')).not.toBeInTheDocument()
  })

  it('hides the free-text composer while a structured pension question is active', async () => {
    mockApi({ procedures: [summary, pensionSummary] })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    const input = await screen.findByLabelText('Tell us what service you need')
    fireEvent.change(input, { target: { value: 'old age pension Kerala' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, continue' }))
    await screen.findByText(pensionSensitiveQuestion.prompt)
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Tell us what service you need')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Browse all services' })).toBeInTheDocument()
  })

  it('supports both example services, ambiguous/no-match fallback, and local PII warning', async () => {
    const fetchMock = mockApi({ procedures: [summary, pensionSummary], procedure: pensionDetail })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    const query = await screen.findByLabelText('Tell us what service you need')
    fireEvent.change(query, { target: { value: 'old age pension Kerala' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(new RegExp(pensionSummary.title))).toBeInTheDocument()
    fireEvent.change(query, { target: { value: '1234 5678 9012' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(screen.getByRole('alert')).toHaveTextContent('remove personal identifiers')
    const beforeUnsupported = fetchMock.mock.calls.length
    fireEvent.change(query, { target: { value: 'I need to change my name in Aadhaar' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(/We do not yet have a verified procedure for that request/)).toBeInTheDocument()
    expect(fetchMock.mock.calls).toHaveLength(beforeUnsupported)
    fireEvent.click(screen.getAllByRole('button', { name: 'Browse all services' }).at(-1)!)
    expect(await screen.findByRole('heading', { name: 'Supported services' })).toBeInTheDocument()
  })

  it('announces local matching, makes no finder request, and clears inference on language change', async () => {
    const fetchMock = mockApi({ procedures: [summary, pensionSummary] })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    const query = await screen.findByLabelText('Tell us what service you need')
    const beforeInference = fetchMock.mock.calls.length
    fireEvent.change(query, { target: { value: 'need aadhaar adress updation after moving' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(/Matched on this device/)).toBeInTheDocument()
    expect(screen.getByText(/This request has not been sent online/)).toHaveTextContent('Matched on this device')
    expect(fetchMock.mock.calls).toHaveLength(beforeInference)
    fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'hi' } })
    expect(await screen.findByLabelText('बताएँ कि आपको कौन-सी सेवा चाहिए')).toHaveValue('')
    expect(screen.queryByText(/इस डिवाइस पर मिलान हुआ/)).not.toBeInTheDocument()
  })

  it('asks the citizen to choose when catalogue phrases are tied', async () => {
    mockApi({ procedures: [{ ...summary, intent_phrases: ['address update'] }, { ...pensionSummary, intent_phrases: ['address update'] }] })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    fireEvent.change(await screen.findByLabelText('Tell us what service you need'), { target: { value: 'address update' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Choose the service you mean')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: new RegExp(summary.title) })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: new RegExp(pensionSummary.title) })).toBeInTheDocument()
  })

  it('shows an unavailable backend state on initial failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    render(<App />)
    await waitFor(() => expect(screen.getByText('Service is temporarily unavailable')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Start' })).toBeDisabled()
  })

  it('requires AI disclosure consent, sends only bounded turn fields, renders verified activity, and Start Over clears memory', async () => {
    const fetchMock = mockApi({ agentAvailable: true })
    render(<App />)
    await openAssistant()
    expect(screen.getByText(/Groq collects usage metadata/)).toBeInTheDocument()
    expect(screen.getByText(/owner-controlled Groq Console setting/)).toBeInTheDocument()
    expect(screen.getByText(/up to four in-memory conversation turns may be sent to GroqCloud/)).toBeInTheDocument()
    expect(screen.queryByLabelText('General service question')).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(call => String(call[0]).endsWith('/assistant/turn'))).toBe(false)
    fireEvent.click(screen.getByRole('checkbox', { name: /consent to this AI turn/ }))
    fireEvent.change(screen.getByLabelText('General service question'), { target: { value: 'How do I update my Aadhaar address?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send to AI' }))
    expect((await screen.findAllByText('Choose the verified Aadhaar path.')).length).toBe(1)
    expect(screen.getByText(/Checked verified procedures/)).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/assistant/turn'))!
    const body = JSON.parse(String(call[1]?.body))
    expect(Object.keys(body).sort()).toEqual(['consent', 'demo_status_id', 'history', 'locale', 'message', 'readiness_answers', 'service_id'])
    expect(body.message).toBe('How do I update my Aadhaar address?')
    fireEvent.click(screen.getByRole('button', { name: 'Start deterministic readiness check' }))
    expect(await screen.findByRole('heading', { name: 'Check what you need' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start Over' }))
    await openAssistant()
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.queryAllByText('Choose the verified Aadhaar path.')).toHaveLength(0)
  })

  it('identifies GroqCloud and its account-controlled retention boundary in every locale', () => {
    for (const locale of ['en', 'hi', 'ml'] as const) {
      expect(UI_MESSAGES[locale].aiDisclosure).toContain('GroqCloud')
      expect(UI_MESSAGES[locale].aiDataUse).toContain('GroqCloud')
      expect(UI_MESSAGES[locale].aiNoZdr).toContain('Zero Data Retention')
      expect(UI_MESSAGES[locale].aiNoZdr).toContain('Groq Console')
    }
  })

  it('uses the selected locale for the AI turn and clears conversation when language changes', async () => {
    const hindiReply: AssistantTurnResponse = { ...agentReply, locale: 'hi', message: 'सत्यापित प्रक्रिया चुनें।', disclaimer: 'AI मार्गदर्शन स्वीकृति नहीं है।' }
    const fetchMock = mockApi({ agentAvailable: true, agentReply: hindiReply })
    render(<App />)
    fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'hi' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'शुरू करें' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'शुरू करें' }))
    fireEvent.click(await screen.findByRole('button', { name: 'सभी सेवाएँ देखें' }))
    fireEvent.click(await screen.findByRole('button', { name: /Update your Aadhaar address online/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Ask Sahayi AI' }))
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.change(screen.getByLabelText('सामान्य सेवा प्रश्न'), { target: { value: 'आधार पता अपडेट में मदद' } })
    fireEvent.click(screen.getByRole('button', { name: 'AI को भेजें' }))
    expect((await screen.findAllByText('सत्यापित प्रक्रिया चुनें।')).length).toBe(1)
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/assistant/turn'))!
    expect(JSON.parse(String(call[1]?.body)).locale).toBe('hi')
    fireEvent.change(screen.getByLabelText('भाषा'), { target: { value: 'ml' } })
    expect(screen.queryAllByText('सत्यापित प्रक्रिया चुनें।')).toHaveLength(0)
    expect(screen.getByText(/Zero Data Retention/)).toBeInTheDocument()
    expect(screen.getByText(/GroqCloud-ലേക്ക്/)).toBeInTheDocument()
  })

  it('blocks multilingual identifier-shaped AI input in the browser without a provider request', async () => {
    const fetchMock = mockApi({ agentAvailable: true })
    render(<App />)
    await openAssistant()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.change(screen.getByLabelText('General service question'), { target: { value: 'मेरा आधार १२३४ ५६७८ ९०१२ है' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send to AI' }))
    expect(screen.getByRole('alert')).toHaveTextContent('remove personal identifiers')
    expect(fetchMock.mock.calls.some(call => String(call[0]).endsWith('/assistant/turn'))).toBe(false)
  })

  it('renders a provider fallback response only once', async () => {
    const fallbackMessage = 'I could not complete the AI-guided turn. The verified procedure catalogue and deterministic checks remain available.'
    mockApi({
      agentAvailable: true,
      agentReply: {
        ...agentReply,
        status: 'fallback',
        message: fallbackMessage,
        selection: { state: 'none', service_id: null, choices: [] },
        fact_cards: [],
        sources: [],
        actions: [],
        tool_trace: [],
        fallback: true,
      },
    })
    render(<App />)
    await openAssistant()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.change(screen.getByLabelText('General service question'), { target: { value: 'Help with this service' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send to AI' }))
    expect(await screen.findAllByText(fallbackMessage)).toHaveLength(1)
  })

  it('renders printable deterministic checklist and synthetic worksheet without private prefill', async () => {
    const print = vi.fn()
    vi.stubGlobal('print', print)
    mockApi()
    render(<App />)
    await openProcedure()
    fireEvent.click(screen.getByRole('button', { name: 'Build personalized checklist' }))
    expect(await screen.findByRole('heading', { name: 'Personalized preparation checklist' })).toBeInTheDocument()
    expect(screen.getByText('Confirm the fee before paying.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Print' }))
    expect(print).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Prepare synthetic demo worksheet' }))
    expect(await screen.findByText('DEMO — NOT FOR SUBMISSION')).toBeInTheDocument()
    expect(screen.getByLabelText('Try with sample citizen')).toHaveValue('fictional-demo')
    expect(screen.getByText(/Citizen must provide privately — not collected/)).toBeInTheDocument()
    expect(screen.queryByText(/1234 5678 9012/)).not.toBeInTheDocument()
  })

  it.each([
    ['en', 'Continue with demo submission', 'No application will be submitted.'],
    ['hi', 'डेमो जमा करने के साथ आगे बढ़ें', 'कोई आवेदन जमा नहीं होगा।'],
    ['ml', 'ഡെമോ സമർപ്പണവുമായി തുടരുക', 'അപേക്ഷ സമർപ്പിക്കില്ല.'],
  ] as const)('shows the localized demo disclosure in %s', async (locale, continueLabel, disclosure) => {
    mockApi()
    render(<App />)
    if (locale !== 'en') fireEvent.change(screen.getByLabelText('Language'), { target: { value: locale } })
    await waitFor(() => expect(screen.getByRole('button', { name: UI_MESSAGES[locale].start })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: UI_MESSAGES[locale].start }))
    fireEvent.click(await screen.findByRole('button', { name: UI_MESSAGES[locale].browseServices }))
    fireEvent.click(await screen.findByRole('button', { name: /Update your Aadhaar address online/ }))
    fireEvent.click(await screen.findByRole('button', { name: UI_MESSAGES[locale].syntheticForm }))
    for (let index = 0; index < formFixture.fields.length; index += 1) fireEvent.click(await screen.findByRole('button', { name: UI_MESSAGES[locale].nextField }))
    fireEvent.click(await screen.findByRole('button', { name: continueLabel }))
    expect(await screen.findByText(disclosure)).toBeInTheDocument()
    expect(screen.getByText(UI_MESSAGES[locale].noGovernmentContact)).toBeInTheDocument()
    expect(screen.getByText(UI_MESSAGES[locale].onlySyntheticData)).toBeInTheDocument()
    expect(screen.getByText(UI_MESSAGES[locale].demoClears)).toBeInTheDocument()
  })

  it('supports deliberate normal and action-required status paths with accessible current status', async () => {
    mockApi({ agentAvailable: true })
    render(<App />)
    await openProcedure()
    fireEvent.click(screen.getByRole('button', { name: 'Prepare synthetic demo worksheet' }))
    for (let index = 0; index < formFixture.fields.length; index += 1) fireEvent.click(await screen.findByRole('button', { name: 'Next demo field' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Continue with demo submission' }))
    fireEvent.click(screen.getByRole('button', { name: 'Action-required scenario' }))
    expect(await screen.findByText('DEMO-UIDAI-ACTION')).toBeInTheDocument()
    const timeline = screen.getByRole('list', { name: 'Simulated status timeline' })
    expect(within(timeline).getByRole('heading', { name: 'Preparation Completed' })).toHaveFocus()
    for (let step = 0; step < 3; step += 1) {
      fireEvent.click(screen.getByRole('button', { name: 'Advance demo deliberately' }))
      await waitFor(() => expect(within(timeline).getByRole('listitem', { current: 'step' })).toHaveTextContent(`SIMULATED — step ${step + 2} of 5`))
    }
    await waitFor(() => expect(within(timeline).getByRole('heading', { name: 'Action required' })).toHaveFocus())
    expect(within(timeline).getByRole('listitem', { current: 'step' })).toHaveTextContent('Action required')
    fireEvent.click(screen.getByRole('button', { name: 'Normal completion scenario' }))
    expect(await screen.findByText('DEMO-UIDAI-NORMAL')).toBeInTheDocument()
    expect(screen.queryByText('DEMO-UIDAI-ACTION')).not.toBeInTheDocument()
    for (let step = 0; step < 3; step += 1) {
      fireEvent.click(screen.getByRole('button', { name: 'Advance demo deliberately' }))
      await waitFor(() => expect(within(timeline).getByRole('listitem', { current: 'step' })).toHaveTextContent(`SIMULATED — step ${step + 2} of 4`))
    }
    expect(screen.getByRole('button', { name: 'Demo completed' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'End session' }))
    expect(screen.getByText(/cleared all in-memory session data/)).toBeInTheDocument()
    expect(screen.queryByText(/DEMO-UIDAI/)).not.toBeInTheDocument()
    await openAssistant()
    expect(screen.getByRole('checkbox')).not.toBeChecked()
  })

  it('passes only the validated current demo status ID to the optional agent tool boundary', async () => {
    const fetchMock = mockApi({ agentAvailable: true })
    render(<App />)
    await openProcedure()
    fireEvent.click(screen.getByRole('button', { name: 'Prepare synthetic demo worksheet' }))
    for (let index = 0; index < formFixture.fields.length; index += 1) fireEvent.click(await screen.findByRole('button', { name: 'Next demo field' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Continue with demo submission' }))
    fireEvent.click(screen.getByRole('button', { name: 'Normal completion scenario' }))
    await screen.findByText('DEMO-UIDAI-NORMAL')
    fireEvent.click(screen.getByRole('button', { name: 'Ask AI to explain this demo status' }))
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.change(screen.getByLabelText('General service question'), { target: { value: 'Explain this demo status' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send to AI' }))
    await screen.findAllByText('Choose the verified Aadhaar path.')
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/assistant/turn'))!
    expect(JSON.parse(String(call[1]?.body)).demo_status_id).toBe('preparation-completed')
  })

  it('End session aborts requests, clears citizen state, and returns a clean welcome', async () => {
    const fetchMock = mockApi({ pendingDetail: true })
    render(<App />)
    await openCatalogue()
    fireEvent.click(screen.getByRole('button', { name: /Update your Aadhaar address online/ }))
    await screen.findByText('Loading procedure guidance…')
    const detailCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/procedures/uidai-'))!
    expect(detailCall[1]?.signal?.aborted).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'End session' }))
    expect(detailCall[1]?.signal?.aborted).toBe(true)
    expect(screen.getByRole('heading', { name: 'Sahayi' })).toBeInTheDocument()
    expect(screen.getByText(/cleared all in-memory session data/)).toBeInTheDocument()
    expect(screen.queryByText('Loading procedure guidance…')).not.toBeInTheDocument()
  })

  it('warns, continues, and clears on kiosk inactivity using elapsed time', async () => {
    mockApi({ inactivityTimeout: 60, inactivityWarning: 10 })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    await act(async () => { vi.advanceTimersByTime(50_000) })
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Your session will end soon')
    fireEvent.click(screen.getByRole('button', { name: 'Continue session' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    await act(async () => { vi.advanceTimersByTime(49_000) })
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    await act(async () => { vi.advanceTimersByTime(1_000) })
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    await act(async () => { vi.advanceTimersByTime(10_000) })
    expect(screen.getByRole('heading', { name: 'Sahayi' })).toBeInTheDocument()
    expect(screen.getByText(/Session cleared after inactivity/)).toBeInTheDocument()
  })

  it('clears by elapsed time when a throttled hidden tab becomes visible', async () => {
    mockApi({ inactivityTimeout: 60, inactivityWarning: 10 })
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    const later = Date.now() + 61_000
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    await act(async () => {
      vi.setSystemTime(later)
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(screen.getByText(/Session cleared after inactivity/)).toBeInTheDocument()
    delete (document as unknown as Record<string, unknown>).visibilityState
  })
})
