# NextCare Task State

Last updated: 2026-08-08

## Active milestone

Phase 1 heart-attack ML, Prototype ESI Subset, XAI, and the Agentic Clinical
Reasoning implementation with Groq + local RAG + local KG, Dynamic Priority,
local clinical-document OCR, speech-to-clinical-text, and frontend integration are
complete and verified. Persistent medical-staff authentication and clinical API
protection are also complete and verified. Final repository documentation and deterministic judge
data are complete. Live Groq authentication, strict minimal output, and one
synthetic English STT path are verified. Live clinical workflows confirmed
dynamic tool selection and failure isolation but did not reach structured
synthesis. Full ESI, medication intelligence, and remaining explanation modes
remain.

## Completed checkpoints

| ID | Task | Status | Evidence |
| --- | --- | --- | --- |
| P1-B01–B05 | Clinical data foundation | complete | Patient/encounter/history/observations/provenance APIs and migrations. |
| P1-090 | Supervisor-directed LangGraph | complete | Conditional routing, shared state/trace, loop and failure isolation. |
| P1-050 | Validate approved cardiac dataset | complete | 1,319 rows; checksum/schema bound; missing/duplicates/invalid/leakage audit persisted. |
| P1-060 | Train and package classifier | complete | Logistic Regression and Random Forest compared; versioned RF artifact and recreation metadata generated. |
| P1-070 | Integrate inference and SHAP | complete | `CardiacRiskTool`, Triage/Risk persistence, Tree SHAP, XAI persistence, workflow path, and benchmarks implemented. |
| P1-071 | ML/XAI verification | complete | Model, SHAP, migration, OpenAPI, and real API demo verified. |
| P1-080 | Prototype emergency triage policy | complete | `prototype-esi-subset-1.0.0`, append-only assessments, reassessment, XAI/Safety integration, benchmark, and two-run API demo; 35 tests pass. |
| P1-090A | Agentic Clinical Reasoning checkpoint | implementation complete; live partial | Provider abstraction, PHI-minimized payload, dynamic five-tool loop, local RAG/KG, strict schema, persistence, Safety/XAI; 62 tests pass. Live connectivity succeeded with `openai/gpt-oss-20b`; one live workflow selected history → RAG → KG, then a later Groq tool-selection request ended `PROVIDER_FAILURE` before synthesis. |
| P1-100 | Dynamic Priority Agent and patient queue | complete | `dynamic-priority-1.0.0`, `vital-deterioration-1.0.0`, queue projection/history migration, APIs, audits, Safety/fourth-XAI-channel integration, four-patient workflow demo, benchmarks, and 81 tests pass. |
| P1-115 | Multimodal OCR | complete | Local Tesseract/Poppler adapter, bounded validated upload APIs, persisted document/result provenance, versioned allow-listed lab parser, conflict preservation/manual precedence, Multimodal/ClinicalState integration, real host smoke test, and 85 tests pass. |
| P1-116 | Speech-to-clinical-text | complete | Replaceable Groq Whisper adapter, validated bounded audio APIs, persisted transcript/model/provenance, `clinical-text-extractor-1.0.0`, negation/conflict/manual-precedence handling, Multimodal/Clinical NLP integration, provider-unavailable isolation, and 89 tests pass. |
| P1-105 | Final backend/API cleanup | complete | Stable errors, restricted CORS, queue transition rules/minimal display context, latest assessment/history projections, debug/compatibility routes hidden from OpenAPI, contract rewrite, and 94 tests pass. |
| P1-110 | Frontend integration | complete | Teammate design retained; real queue/patient/encounter/observation/workflow/OCR/speech APIs integrated; unsupported mock capabilities removed; lint, type-check, and production build pass. |
| P1-120 | Registration-to-dashboard vertical slice | complete | Live servers created a synthetic patient/encounter, persisted manual inputs, completed two workflow runs, detected worsening vitals, recalculated the same queue entry to rank 1/`CRITICAL`, exercised status transitions, served the UI, and a headless browser hydrated through the real CORS/API path. |
| P1-130 | Deployment, recovery, and limitations documentation | complete | Root/frontend runbooks and `.ai` architecture, API, environment, workflow, deployment, decisions, context, and state reflect the integrated system. |
| P1-140 | Final judge/developer documentation | complete | Root README documents architecture, agents, state/data flow, ML, triage, reasoning, RAG/KG, XAI, OCR/speech, queue, offline boundary, persistence, setup, API, tests, benchmarks, privacy, mappings, limitations, and disclaimer. |
| P1-150 | Final engineering verification | complete with one environment limitation | 94 backend tests; lint/typecheck/client+SSR build; fresh migrations; live synthetic STT; real OCR; deterministic four-patient seed; live vertical slice; provider isolation; OpenAPI/API/secret/architecture/frontend audits. Current headless Firefox screenshot recapture was blocked by the host renderer, while the prior hydration check remains documented. |
| P1-160 | Medical-staff authentication | complete | Persistent role/active staff accounts, Argon2 hashes, environment-signed 30-minute JWTs with a development-only ephemeral fallback, reusable clinical-router dependency, no signup, explicit provisioning CLI, frontend login/session expiry/logout, and focused authentication tests. |
| P1-170 | Round-two Vercel judge deployment | implementation complete; account setup pending | Vercel Services manifest, Nitro-packaged TanStack frontend, FastAPI container with OCR tools and 300-second duration, managed-Postgres/psycopg support, explicit migration/staff scripts, same-origin API, verified cardiac artifact packaging, PostgreSQL migration smoke, 114 backend tests, and Vercel-mode frontend build. Optional final-round kiosk launcher is prepared. Neon/Vercel resource provisioning remains an account-owner action. |

## Current model

- Dataset: `Heart Attack.csv`, DOI `10.17632/65gxgy2nmg.2`.
- Model: `RandomForestClassifier`, version `cardiac-risk-rf-1.0.0`.
- Split: stratified 80/20, seed 42, fixed threshold 0.5.
- Test positive recall: 0.9938; ROC-AUC: 0.9990.
- Status: hackathon decision-support prototype, not clinically validated.
- Artifact: the verified `cardiac_risk_random_forest_v1.0.0.joblib` is allow-listed
  for the hackathon container; all other artifacts and raw training data remain
  ignored. Metadata records its SHA-256.

## Agent capability state

| Agent/capability | State |
| --- | --- |
| Triage/Risk cardiac model | implemented; incomplete input produces no prediction |
| Triage/Risk emergency severity | implemented as provisional Prototype ESI Subset; not full ESI |
| XAI Tree SHAP | implemented and persisted |
| XAI decision and triage rule traces | implemented; model contributions remain separate |
| XAI clinical reasoning evidence | implemented separately from SHAP and triage trace |
| XAI priority rule trace | implemented as a fourth separate deterministic channel |
| XAI counterfactual/saliency | pending capability |
| Clinical Reasoning/Groq | implemented and mock-verified; live connectivity/tool selection verified; live structured workflow synthesis still unverified after sanitized provider failures |
| Local RAG | implemented; corpus/index versioned with provenance |
| Medical Knowledge Graph | implemented; 17 nodes/17 source-backed edges |
| Priority/dynamic queue | implemented; usable triage required; persistent projection plus append-only calculations |
| Multimodal OCR | implemented locally; conservative lab extraction with persisted provenance and conflicts |
| Speech transcription | implemented through one replaceable Groq Whisper adapter; one synthetic live STT/negation/provenance path verified; no offline STT model installed |
| Clinical NLP free text | deterministic allow-listed symptom extraction with explicit nearby negation handling |

## Remaining Phase 1 backlog

No remaining task from the requested Phase 1 implementation sequence. Broader
product capabilities listed below remain intentionally out of scope.

## Known limitations/blockers

- Dataset units and assay details are not documented reliably.
- The single-center dataset has no external or prospective clinical validation.
- Troponin and CK-MB may make performance unsuitable for interpretation as early
  pre-test risk.
- Full ESI decision points need immediate-intervention need, airway/breathing/
  circulation observations, consciousness/mental status, clinician high-risk
  assessment, and anticipated resource count; these are not available.
- The implemented policy is always provisional, is not clinically validated,
  and does not replace an experienced triage clinician.
- The 12-chunk corpus and 17-edge KG cover only the present ACS/chest-pain demo;
  they are not comprehensive or clinically validated knowledge bases.
- The local hashing-vector embedding is lightweight and lexical, not a general
  medical semantic embedding model.
- Live verification on 2026-08-08 authenticated successfully and returned a
  minimal strict response in 776.386 ms. The one clinical workflow completed in
  5,253.397 ms and preserved deterministic outputs, but reasoning ended `PARTIAL`
  after three successful tool turns and a subsequent sanitized provider failure.
- A final synthetic live reasoning workflow also completed with all deterministic
  channels intact; Groq selected RAG successfully, then reasoning ended `PARTIAL`
  after a sanitized provider failure (3,786.711 ms agent, 3,601.649 ms provider).
- Raw cardiac data and unapproved generated artifacts remain ignored. The single
  verified hackathon artifact is allow-listed and checksum-checked during the
  container build.
- Dynamic priority is deterministic and auditable but not clinically validated;
  its vital-delta and scoring thresholds require clinical governance before use.
- Waiting time changes only when explicitly recalculated; no background worker or
  event bus is implemented.
- The frontend is connected and server-authoritative. It has a reproducible live
  contract smoke script and a headless-browser hydration check, but no component
  or browser automation suite yet. During the final checkpoint, Firefox could not
  recapture a screenshot because its headless renderer reported
  `RenderCompositorSWGL failed mapping default framebuffer`; the HTTP vertical
  slice and prior browser hydration evidence remain valid.
- The current host lacks Tesseract English trained data; OCR uses the available
  Afrikaans Latin-script fallback and records that language on every result.
- Speech transcription requires Groq network access and may contain clinical or
  identifying speech; no offline model is installed. Audio bytes are not retained.
- Staff access tokens are short-lived and browser-session scoped, but this
  hackathon implementation has no refresh-token flow or server-side revocation
  list. Roles currently share the same clinical API authorization.

## Intentionally omitted

- Full ESI levels and clinician override/governance workflow.
- Medical-image interpretation, live wearable adapter, external EHR connector,
  medication/prescription intelligence, and background queue scheduler.
- Fine-grained RBAC, refresh-token/revocation infrastructure, encryption-at-rest
  governance, offline cloud synchronization, and regulatory certification.

## Future / optional

- Clinically governed validation, broader corpus/KG review, offline STT, generated
  OpenAPI frontend types, and frontend component/browser automation.

## Next task

No remaining task in the requested sequence. Future work requires new scope and
clinical governance, especially full ESI inputs/validation and medication or
imaging capabilities.
