# Privacy and safety boundary

Sahayi minimizes citizen data by separating local service discovery, deterministic procedure APIs, optional consent-gated cloud processing, and offline administration.

## What remains in browser memory

The raw service-search query, primary conversation history, every personal preparation value, its local source/confirmation/validation/edit revision, chosen document bytes, filename, raw OCR text, temporary PDF/image canvases, and unconfirmed document conclusion never leave the browser. Language, selection, readiness answers/history, checklist, populated preparation preview, synthetic demo reference/status, optional-agent consent and conversation, voice transcript, and navigation state live in React memory. The browser sends only allowlisted service/question IDs, bounded closed-choice readiness categories, completed field IDs, and an explicitly citizen-confirmed `{document_id, appears_relevant, citizen_confirmed:true}` clue to deterministic APIs. Sahayi does not add cookies, `localStorage`, `sessionStorage`, IndexedDB, Cache API, a service worker, analytics, telemetry, or browser-persisted citizen state. Tesseract's internal data caching is disabled; self-hosted static OCR assets may use ordinary HTTP cache behavior.

The local finder blocks obvious Aadhaar-, Indian-phone-, email-, and numbered-address-shaped values before matching. This is a warning gate, not a guarantee that every personal detail can be recognized. Citizens are instructed not to enter identifiers or private details.

Voice input is an explicit browser enhancement and never auto-starts. Browser recognition may use browser/vendor processing and is not guaranteed to be on-device; Sahayi does not persist or log audio or transcripts. Transcripts pass through the same identifier gate before deterministic or optional cloud processing. Unsupported browsers retain the full text path. Navigation, locale changes, unmount, Start Over, End session, and inactivity clearing stop recognition and speech synthesis.

Document assistance is also explicit and optional. MIME and magic bytes must agree for JPEG, PNG, WebP, or PDF; file, pixel, page, single-job, per-page, and total-time limits fail closed. PDF pages are rendered locally to temporary canvases and OCR runs in a browser Web Worker using same-origin pinned code and trained data. Identifier-shaped OCR values are redacted before deterministic matching. Low-confidence text stays unknown, results require citizen confirmation, and the UI never calls the result genuine, valid, accepted, or government-approved. Cancel, replacement, completion, navigation, locale change, Start Over, End session, inactivity, error, and unmount terminate/clear local resources.

## What reaches FastAPI

Deterministic routes receive only the current locale, allowlisted service/persona/scenario/status/question/field IDs, bounded closed-choice readiness answers, completed field IDs, and optional confirmed allowlisted document evidence. They do not accept names, addresses, account numbers, preparation values, file bytes, filenames, raw OCR text, exact financial values, arbitrary form text, OTPs, payment data, or real application references. The strict conversation-turn request rejects unknown fields and permits arbitrary message text only for an affirmative-consent cloud-clarification event after identifier screening. Requests are validated, processed without a durable session, and not logged by Sahayi. API responses use `Cache-Control: no-store`.

The server graph is recompiled/invoked as a bounded stateless transition for each request. It has no checkpointer, store, database, persistent thread, LangSmith tracing, or telemetry. Every carried service/question/answer/document ID is treated as untrusted and recomputed against the active Procedure Pack.

The primary preparation sheet overlays browser-memory citizen values on a server-supplied structural field definition; its API representation never contains those values. Identifier and unsupported fields stay blank. A separate synthetic worksheet uses predefined fictional values, and demo submission/status accepts only obvious `DEMO-...` references. No government endpoint is contacted.

## Optional cloud processing

The assistant is disabled unless a server flag and server-only Groq key are both configured. Before use, the UI names GroqCloud, explains that a minimized identifier-screened message and up to four memory-only turns may be processed there, and requires affirmative consent. Browser and backend gates screen the current message and prior turns for common identifier shapes. The API does not accept files, arbitrary metadata, or real references.

Groq documents that usage metadata is always collected and says inference customer data is not retained by default except for limited reliability/abuse purposes; an organization owner may separately enable Zero Data Retention in Groq Console Data Controls. Sahayi does not set, verify, or guarantee that account setting and does not claim control over retention or logging by the browser, network, hosting platform, or Groq. Account data controls, access controls, spend/rate limits, model permission, and applicable terms require owner review before enabling the feature.

The Groq key, internal prompts, raw provider output, provider IDs, and tool arguments remain server-side and are not returned through public configuration or assistant responses. Public configuration may identify the selected provider/model and whether the feature is available. Sahayi does not log answer bodies, raw agent prompts, provider output, or citizen messages.

## Clearing and session end

**End session** aborts tracked requests and OCR workers, invalidates late responses, clears file inputs, byte buffers, canvases, PDF tasks, OCR conclusions, any tracked object URLs, and every in-memory citizen workflow state, then returns to the localized welcome screen. The same clearing operation runs after the bounded inactivity warning expires; restoring a hidden tab recomputes elapsed time. Language changes and Start Over also clear relevant state.

This confirmation covers Sahayi's own in-memory state only. It does not promise erasure from browser/network/provider infrastructure outside Sahayi's control.

## Durable and administrative data

Durable repository data is limited to source code, static UI copy, versioned Procedure Packs, generated schema/model artifacts, owned synthetic datasets/evaluations, an offline monitoring fixture, and bounded Procedure Intelligence workflow artifacts. There is no citizen database. Scheduled checks invoke the one-shot allowlisted monitor, never carry citizen information or credentials, never mutate facts, and visibly require human review for changed/error states. They are not hosted citizen functionality or automatic fact activation.

## Safety rules and limitations

- Procedure Packs and deterministic rules—not AI—decide displayed facts and readiness outcomes.
- Every local service proposal requires confirmation. Readiness is not eligibility, approval, submission, or legal advice.
- Conflicting official facts remain visible and source-linked rather than silently resolved.
- Hindi and Malayalam are machine-assisted prototypes pending native/legal review.
- Only synthetic model evaluation and demo personas are included; no real-world accuracy or production claim is made.
- Real submission/status, government authentication, OTP/payment, server file upload, analytics, and telemetry are absent. Local OCR is printed-text preparation assistance, not authenticity verification, and can be wrong. Voice remains browser-dependent prototype assistance, not certified pronunciation or complete accessibility coverage.

Any future collection, persistence, third-party integration, or telemetry requires an explicit privacy design, retention decision, threat review, and user approval before implementation.
