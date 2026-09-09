# NextCare Architectural Decision Log

Last updated: 2026-08-08

The technology constraints supplied for Phase 1 (React + Vite, Python + FastAPI,
LangGraph, edge-first operation, conventional ML, and model-derived
explainability) are accepted project constraints rather than redesign choices.
The decisions below fill gaps required to implement the first vertical slice.

## D-001 — Use a local modular monolith

Status: accepted

Keep one FastAPI backend with explicit API, domain, persistence, service, ML, and
workflow modules, plus one React frontend. LangGraph runs inside the backend
process. This is the smallest deployable shape for kiosk mode while keeping
clinical-condition workflows and infrastructure boundaries replaceable later.

## D-002 — Use SQLite locally through SQLAlchemy and Alembic

Status: accepted

SQLite is the local/edge Phase 1 system of record because it runs without a
network service and supports transactional local operation. The round-two cloud
submission uses managed PostgreSQL as recorded in D-037. SQLAlchemy isolates persistence from
domain/service code, and Alembic provides repeatable schema evolution. Stable UUID
identifiers, UTC timestamps, and explicit sync/audit metadata preserve a path to
future cloud replication without implementing synchronization now.

## D-003 — Persist clinical facts separately and retain provenance

Status: accepted

Patient is separate from ClinicalEncounter, and a patient can have many
encounters. Symptoms, timestamped VitalSigns readings, and LabResults panels are
encounter-owned records rather than fields on Patient. Clinical observations
retain one of `MANUAL`, `SIMULATOR`, `OCR`, `SPEECH`, `EHR`, or `WEARABLE`. The
wearable value preserves a future-compatible contract; no live wearable adapter
is implemented.

Predictions retain the exact feature snapshot and model version used. Explanations
retain model-derived feature contributions. Triage assessments retain the policy
version, complete rule trace, missing information, provisional state, and input
snapshot. No clinician-override workflow is implemented. AuditEvent and all
assessment histories are append-only at the application layer.

## D-004 — Keep cardiac risk, clinical severity, and queue priority independent

Status: accepted

The trained classifier outputs heart-attack class/probability only. A separate,
versioned deterministic triage service produces a clearly labelled provisional
severity from explicit clinical rules; cardiac output is supporting context only
and cannot directly assign severity. Dynamic queue `priority` is a third contract
implemented by a separately versioned deterministic policy. The policy is not inferred from the dataset target and
is not presented as a validated ESI score.

## D-005 — Use LangGraph with a replaceable Supervisor routing policy

Status: accepted

The implemented graph routes Intake to a Supervisor and returns every specialist
to that Supervisor. Conditional edges execute `next_action`. The current policy
is deterministic and state/completion based; it is isolated from the graph node
so a future LLM can augment or replace routing without redesigning specialists.
No LLM is used for Supervisor routing. The later Groq integration is isolated
inside Clinical Reasoning. Clinical persistence remains independently testable.

## D-006 — Use REST plus lightweight queue polling for Phase 1

Status: accepted

The frontend saves encounter sections through JSON REST endpoints and invokes one
explicit assessment endpoint. The queue is an ordered server-side projection and
the frontend refreshes it after mutations and on a short polling interval. This
meets the local dynamic-queue need without adding WebSocket infrastructure; the
transport can be replaced later without changing queue entities.

## D-007 — Use TypeScript and one centralized frontend API boundary

Status: accepted

TanStack Start routes and the centralized client use TypeScript while several
retained teammate components use JSX. FastAPI's OpenAPI document is authoritative,
and `frontend/src/lib/api.ts` keeps the currently consumed boundary types and all
fetch behavior in one place. No OpenAPI code-generation command is configured;
future generation can replace these maintained types without changing components.

## D-008 — Store laboratory data as generic observations

Status: accepted

Each LabResult row stores a test name, numeric value, optional unit, collection
time, source, and optional reference metadata. Troponin, CK-MB, and blood sugar are
therefore data values rather than database columns. This keeps the current API and
schema usable for later laboratory test types without introducing a separate
entity model or migration for every test.

## D-009 — Represent unavailable intelligence explicitly

Status: accepted

Unavailable model, provider, multimodal, explanation, and queue capabilities
return `PENDING_CAPABILITY` or `PARTIAL` with reasons and null/empty canonical
outputs. A missing optional capability does not fail the workflow. This prevents
scaffolding from being mistaken for a clinical result.

## D-010 — Keep one ordered in-state execution trace

Status: accepted

All agent executions share one trace contract. Workflow start and terminal states
are persisted as AuditEvents, while detailed node decisions stay in
`agent_trace`; this preserves observability without creating excessive DB events.

## D-011 — Bind training to an approved checksum and stable feature schema

Status: accepted

Training accepts only `Heart Attack.csv` with the approved SHA-256 and exact raw
schema. `ml/feature_schema.json` maps misspelled raw names to stable application
features. This prevents silent dataset substitution and stops raw CSV naming from
leaking into runtime contracts.

## D-012 — Exclude documented invalid rows before splitting

Status: accepted

Exact duplicates are removed first; missing required data fails preparation. The
current dataset has neither. Three heart rates above 300 and eight rows with
diastolic BP above systolic BP are excluded before stratified splitting. The
policy and affected CSV lines are recorded in `ml/dataset_report.json`.

## D-013 — Select Random Forest for sensitivity and Tree SHAP compatibility

Status: accepted

With seed 42, fixed threshold 0.5, and an untouched 20% stratified test set,
Random Forest achieved 0.9938 positive recall and 0.9990 ROC-AUC versus 0.6957 and
0.8933 for Logistic Regression. Random Forest is selected because the emergency
support context prioritizes sensitivity and the model remains locally fast and
Tree-SHAP compatible. These metrics are not clinical validation.

## D-014 — Never infer undocumented measurement units

Status: accepted

The source defines feature meanings but not dependable units, and its glucose
description conflicts with the continuous file. Runtime passes numeric values
without conversion or binarization and records a warning/source snapshot. Unit
and assay ambiguity is a known limitation requiring future clinical data-contract
work.

## D-015 — Persist predictions and model contributions append-only

Status: accepted

Every successful agent inference creates a new `RiskPrediction`; Tree SHAP creates
an `Explanation` referencing it. Repeat runs do not overwrite history. SHAP output
is labelled model feature contribution, never clinical causation.

## D-016 — Implement only an auditable ESI-informed subset

Status: accepted

Policy `NEUROBOTS Prototype ESI Subset` version
`prototype-esi-subset-1.0.0` follows the ordering and high-risk concepts in the
Emergency Nurses Association ESI Handbook v5 and the AHRQ overview, but does not
claim full ESI compliance. `TRIAGE-001` screens adult high-risk vitals;
`TRIAGE-002` checks the local chest-pain/dyspnea-or-sweating cluster;
`TRIAGE-003` records severe reported distress as consideration only;
`TRIAGE-004` records high cardiac output as support only; and `TRIAGE-005` marks
missing full-ESI inputs. Because intervention need, mental status, clinician
high-risk assessment, and resource count are unavailable, all results are
provisional, level 1 is never inferred, and levels 3–5 remain undetermined.

## D-017 — Persist every triage reassessment append-only

Status: accepted

Every policy run creates a `TriageAssessment` with the policy/version, severity,
provisional/completeness metadata, full rule trace, missing fields, exact input
snapshot, latency, and timestamp. A newer vital triggers a new record on the next
workflow execution; previous assessments are never overwritten.

## D-018 — Use Groq through a provider-neutral boundary

Status: accepted

Use official `groq` SDK 0.37.1 through `LLMProvider` and `GroqProvider`. Reuse a
centrally cached, lazily initialized client; sanitize errors; never log secrets or
raw requests. `openai/gpt-oss-20b` is the default because current Groq documentation
lists local tool use, JSON Schema mode, reasoning, and high throughput. The model
is configurable but cannot change during an encounter.
Groq currently does not support tool use and Structured Outputs in the same call,
so the provider uses tool-selection calls followed by a separate strict-schema
synthesis call.

## D-019 — Preserve an explicit edge/cloud boundary

Status: accepted

Only a purpose-built PHI-minimized payload and controlled tool results may reach
Groq. Names, phone numbers, external/database IDs, exact DOB, and raw notes are
excluded. Database, ML, SHAP, triage, RAG, vector index, KG, and audits stay local.

## D-020 — Use compact, source-attributed summaries for the corpus

Status: accepted

Store a small 12-chunk ACS/chest-pain corpus of paraphrased facts and limited
appropriate excerpts with complete attribution. Do not copy handbooks or claim
comprehensive medical knowledge.

## D-021 — Use a deterministic local hashing-vector index

Status: accepted

Use scikit-learn's local word/bigram `HashingVectorizer` at dimension 4096 and a
compressed NumPy matrix instead of a cloud vector database or runtime download.
Version the embedding recipe, corpus, and index. Its lexical nature is documented
as a limitation.

## D-022 — Use NetworkX for the source-backed medical KG

Status: accepted

Use a local `MultiDiGraph` with 17 nodes and 17 curated edges. Every edge cites a
source and graph version. Expose constrained lookup only, never arbitrary graph,
Python, filesystem, shell, SQL, HTTP, or browsing access.

## D-023 — Let Groq select from exactly five tools

Status: accepted

Expose patient history, current vitals, current labs, local guideline retrieval,
and local KG query. Bind identifiers locally. Limit execution to six reasoning
steps, five calls, duplicate protection, and 45 seconds. Do not hardcode a fixed
tool sequence.

## D-024 — Persist validated visible reasoning, not chain-of-thought

Status: accepted

Validate the differential-consideration schema with Pydantic, use qualitative
support, reject invented numeric disease probabilities, and persist visible
evidence, tool metadata, termination, and latency append-only. Never request or
persist hidden chain-of-thought.

## D-025 — Separate four explanation channels

Status: accepted

XAI exposes SHAP model contributions, deterministic triage rules, clinical
reasoning evidence, and deterministic priority rules separately. Safety checks reasoning grounding, provenance,
schema, provider failure, certainty language, numeric disease claims, and obvious
deterministic contradictions without overwriting valid ML or triage.

## D-026 — Use a deterministic independently versioned queue policy

Status: accepted

Policy `NEUROBOTS Dynamic Priority Policy` version `dynamic-priority-1.0.0`
requires usable triage, uses severity as its strongest signal, and applies only
fixed/capped modifiers for supported deterioration, thresholded cardiac support,
and waiting time. Provisional status is a zero-point flag. An LLM never decides
queue order, and `priority_band` is not an ESI level.

## D-027 — Maintain a current queue projection plus append-only calculations

Status: accepted

Keep one `QueueEntry` per encounter for fast dashboard reads while appending a
`QueuePriorityCalculation` for every successful calculation. Reassessment updates
the current projection without deleting earlier rule traces or input snapshots.
`COMPLETED` and `REMOVED` entries remain persisted and leave the default waiting
list.

## D-028 — Rank deterministically with bounded waiting fairness

Status: accepted

Order by score descending, then earlier `waiting_since`, earlier entry creation,
and UUID. Waiting adds one point per 30 minutes capped at five, so elapsed time
can resolve close cases but cannot make a stable routine patient outrank a clearly
critical emergency solely because of waiting.

## D-029 — Integrate the teammate frontend through the stable API boundary

Status: accepted

Preserve the teammate dashboard's layout and visual system while replacing its
mock hooks with one typed API client and React Query. Render cardiac risk,
provisional triage, clinical reasoning, and operational priority separately.
Delete mock-only clinical features that have no backend capability, and show
provider/capability absence explicitly. Queue order remains server-authoritative.

## D-030 — Use local bounded OCR with conservative clinical parsing

Status: accepted

Use the installed Tesseract and Poppler command-line tools behind a reusable
`OCRService`. Validate MIME signatures, sanitize filenames, limit uploads to 10
MiB and PDFs to five pages, run only fixed argument lists in temporary storage,
and retain metadata/results rather than uploaded bytes. Extract only allow-listed
numeric labs through versioned deterministic parsing. Append OCR observations
with provenance, preserve conflicts, and prefer existing manual labs in the fused
current-value projection. Medical-image diagnosis remains out of scope.

## D-031 — Use one replaceable cloud STT adapter with local extraction

Status: accepted

No practical offline speech model is installed. Keep `SpeechService` provider-
neutral and implement only Groq Whisper, reusing the existing SDK/configuration.
Validate WAV/MP3/MP4/M4A/OGG/WebM/FLAC signatures, limit audio to 20 MiB, request
English transcription, and never let the STT layer diagnose. Do not retain audio
bytes. Persist transcript/model/provenance and run a small deterministic,
versioned symptom extractor locally with explicit negation handling. Preserve
manual/speech conflicts and prefer manual assertions in the fused current view.

## D-032 — Expose a stable persisted assessment projection

Status: accepted

Keep the full workflow response for immediate execution diagnostics, but give the
frontend `assessment` and `assessment-history` read models assembled from persisted
rows. Keep cardiac risk, prototype triage, evidence-backed reasoning, SHAP, and
operational priority separate. Standardize API errors, restrict CORS to configured
local origins, expose only minimal queue display context, enforce terminal queue
states, and hide simulator/compatibility aliases from OpenAPI rather than deleting
the verified internal paths.

## D-033 — Keep the frontend server-authoritative

Status: accepted

Use one fetch client plus React Query for the teammate UI. Poll the ordered queue
and refresh persisted assessment projections after mutations; do not recreate
priority ordering or clinical inference in the browser. Network/provider absence
must be visible, not replaced by mock data. Retain only UI surfaces backed by a
real implemented capability.

## D-034 — Keep restricted data and trained artifacts out of Git

Status: accepted

Ignore `backend/data/raw/` and `backend/ml/artifacts/`. Track the feature schema,
approved checksum, dataset audit, training code, model metadata, and lockfile so a
governed local copy of the approved dataset can reproduce the artifact. A fresh
clone may run without the artifact but must expose cardiac ML and SHAP as
unavailable rather than silently substituting a model or downloading data.

## D-035 — Keep judge data synthetic, deterministic, and locally reproducible

Status: accepted

Use the idempotent development seed to create one returning primary patient and
three varied waiting patients, then run only the deterministic local workflow
with Groq explicitly unavailable. Give the primary case a completed historical
encounter, a current chest-pain encounter, complete cardiac-model inputs, and two
current vital measurements for trend comparison. Do not embed real patient data,
provider responses, uploaded files, or credentials in the reproducibility
artifact.

## D-036 — Gate all clinical APIs with provisioned staff bearer tokens

Status: accepted

Persist staff accounts through SQLAlchemy with unique normalized email, Argon2 hashes via
`pwdlib`, explicit active state, and the initial `DOCTOR`, `NURSE`, and `ADMIN`
roles. Do not expose public registration or silently create an account at startup;
use an interactive provisioning command. Issue short-lived HS256 JWT access
tokens from an environment-provided secret and re-read the active staff record on
every protected request. Permit a random process-local secret only in the named
development environment so a one-process hackathon demo works without secret
setup; require explicit configuration everywhere else. Apply one reusable dependency to the clinical API
router, leaving only health and login public. The browser stores the token only
for its current session and clears it on logout or any protected 401. Fine-grained
role permissions, refresh tokens, and a token revocation store remain future work.

## D-037 — Deploy the judge submission as Vercel services backed by managed PostgreSQL

Status: accepted

Use the repository root as a Vercel Services project containing the existing Vite
frontend and a FastAPI container. Route `/api/*` to the backend and all remaining
application paths to the frontend so authentication remains same-origin. Use
managed PostgreSQL via psycopg in cloud environments while retaining SQLite for
local development and tests. Apply Alembic explicitly before a release; never on
container startup. Allow-list only the verified cardiac `.joblib` and verify its
SHA-256 while building rather than retraining or downloading ungoverned data.
For the final round, the same deployed URL may optionally be opened fullscreen by
a restricted kiosk OS account, with staff entering credentials at the login
screen. The cloud submission has no offline failover and makes no HIPAA/GDPR
compliance claim.
