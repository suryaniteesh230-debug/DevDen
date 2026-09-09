# NextCare Implemented Architecture

Last updated: 2026-08-08

## Current scope

The backend implements an offline clinical-data foundation, Supervisor-directed
LangGraph orchestration, a versioned conventional cardiac classifier, auditable
risk prediction persistence, Tree SHAP contributions, a separately versioned
deterministic Prototype ESI Subset, an evidence-backed Clinical Reasoning Agent,
and a persistent deterministic dynamic patient queue, plus local clinical-document
OCR ingestion, speech-to-clinical-text, and an integrated React dashboard. Access
is gated by persistent medical-staff accounts, Argon2 password hashing, and
short-lived signed bearer tokens.
Clinical reasoning uses
the official Groq SDK behind a provider-neutral
boundary, dynamically selects from five local tools, and synthesizes validated
output from a local RAG corpus and source-backed medical knowledge graph. It does
not implement full ESI or autonomous diagnosis. The frontend consumes persisted
assessment and queue projections and never substitutes mock clinical results.

This is a clinical decision-support prototype. The model reflects one supplied
dataset and has not undergone clinical validation for real-world deployment.

## Main inference path

```text
FastAPI workflow endpoint
  -> LangGraph -> Supervisor -> Data Fusion
  -> Triage/Risk Agent -> CardiacRiskTool -> RiskPrediction
                       -> EmergencyTriageTool -> TriageAssessment
  -> Supervisor -> Clinical Reasoning -> Groq local-tool loop
                  -> local RAG / local KG / patient-context repositories
                  -> ClinicalReasoningResult
  -> Supervisor -> Priority -> DynamicQueueService -> QueueEntry/current rank
  -> Supervisor -> Safety -> Supervisor
  -> XAI Agent -> SHAP + triage + reasoning + priority channels -> Explanation
  -> Supervisor -> FINISH
```

There is no parallel HTTP-only ML implementation. The reusable Python tools are
invoked by the existing agents, and every specialist returns to Supervisor. The
fast path completes before Groq is invoked and never depends on cloud availability.

## Approved dataset and stable schema

The local `data/raw/Heart Attack.csv` matches “An Extensive Dataset for the Heart
Disease Classification System”, DOI `10.17632/65gxgy2nmg.2`: 1,319 rows, eight
features, and target `class`. Its SHA-256 is
`f090acd9aa6ed0df3abd55832a82bf932dcf71987175f68617dd57fb074f4665`.

Raw names are isolated behind `ml/feature_schema.json`:

| Raw | Internal |
| --- | --- |
| `age` | `age` |
| `gender` | `gender` |
| `impluse` | `heart_rate` |
| `pressurehight` | `systolic_bp` |
| `pressurelow` | `diastolic_bp` |
| `glucose` | `blood_sugar` |
| `kcm` | `ck_mb` |
| `troponin` | `troponin` |

Gender uses the published male=1/female=0 mapping. Source measurement units are
not documented dependably, and the published glucose description conflicts with
the continuous file values. No unit conversion or glucose binarization occurs;
runtime predictions carry a warning about unverified units.

## Reproducible model

The preparation process drops exact duplicates, rejects missing required values,
and excludes domain-invalid rows before a stratified 80/20 split with seed 42.
The supplied file has no missing or duplicate rows. Eleven rows are excluded:
three heart rates above 300 and eight diastolic readings above systolic readings.

At threshold 0.5, the untouched test split produced:

| Model | Accuracy | Precision + | Recall/sensitivity + | Specificity | F1 + | ROC-AUC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Logistic Regression | 0.7786 | 0.9256 | 0.6957 | 0.9109 | 0.7943 | 0.8933 |
| Random Forest | 0.9885 | 0.9877 | 0.9938 | 0.9802 | 0.9907 | 0.9990 |

Random Forest version `cardiac-risk-rf-1.0.0` is selected for much higher
positive-class sensitivity and discrimination while remaining a small local
tabular model compatible with Tree SHAP. The high performance likely reflects
the strongly diagnostic contemporaneous troponin/CK-MB fields and must not be
generalized beyond this dataset.

## Persistence

`RiskPrediction` is append-only per execution and stores encounter, model/version,
class, probability, threshold, exact input snapshot, latency, and timestamp.
`Explanation` references one prediction and stores method, explainer/model
versions, ranked feature contributions, and generation time. Nullable future
fields reserve counterfactual, clinical-evidence, and saliency outputs without
fabricating them.

`TriageAssessment` is append-only per evaluation and stores encounter,
policy/version, severity label, provisional flag, completeness/confidence
metadata, every rule check, missing information, exact input snapshot, latency,
and timestamp. A new vital followed by another workflow run appends a new row and
does not mutate the old assessment.

`ClinicalReasoningResult` is append-only per reasoning attempt and stores the
workflow/encounter, agent/provider/model/schema versions, validated visible
output, retrieved source IDs, KG evidence, controlled tool trace, termination
reason, and latency. It never stores chain-of-thought.

`QueueEntry` is the current one-per-encounter operational projection. It stores
status, score/band, upstream assessment references, policy metadata, reason
codes, rule trace, calculation snapshot, deterioration state, and waiting/
recalculation timestamps. `QueuePriorityCalculation` appends every calculation,
so reassessment history remains auditable while the current entry and rank update
efficiently. Terminal entries remain stored but leave the default waiting queue.

`ClinicalDocument` stores bounded-upload metadata and SHA-256, the sanitized
filename, OCR engine/version/language, text and confidence, conservative parsed
fields, explicit conflicts, created lab IDs, and processing timestamps. Uploaded
bytes are processed in an isolated temporary directory and are not retained.
OCR-derived labs are append-only with source `OCR` and document/parser provenance.

## Clinical document OCR boundary

`TesseractOCRService` is reusable without FastAPI, LangGraph, or persistence. It
accepts signature-validated PNG, JPEG, TIFF, WebP, and PDF inputs, processes up to
five PDF pages locally, and applies a timeout. Tesseract English language data is
preferred; the current host only has the Latin-script Afrikaans pack, so the
actual fallback language is included in `ocr_engine_version`.

`ClinicalDocumentParser` version `clinical-document-parser-1.0.0` extracts only
allow-listed numeric laboratory names. It does not diagnose, interpret medical
images, or infer prescriptions. Conflicting manual and OCR labs are both kept and
returned for review; Data Fusion gives manual labs precedence in its current-lab
projection while exposing all observations and multimodal conflicts.

## Speech-to-clinical-text boundary

`SpeechService` is independent of FastAPI, LangGraph, persistence, and clinical
interpretation. No local STT model is installed, so the single implemented adapter
uses Groq `whisper-large-v3-turbo` for explicitly uploaded English audio. Audio
signatures and a 20 MiB limit are enforced and uploaded bytes are not retained.
Provider absence/failure is isolated from the local deterministic workflow.

`ClinicalTextExtractor` version `clinical-text-extractor-1.0.0` recognizes a small
allow-list of symptom phrases and explicit nearby negations. `SpeechTranscription`
stores transcript, provider/model/language, confidence availability, extracted
symptoms, conflicts, linked symptom IDs, latency, hash, and timestamps. Extracted
symptoms are append-only with source `SPEECH`; manual symptom assertions take
precedence in the fused current view while both records remain available.

## Stable frontend read boundary

The workflow endpoint remains the orchestration/debug response. Frontend review
uses read-only latest-assessment and append-only assessment-history projections,
which join persisted cardiac, triage, SHAP, reasoning, priority, OCR, and speech
channels without asking the UI to interpret raw ClinicalState. API errors share a
stable envelope. Local-development CORS uses an explicit allow-list, and queue
status changes enforce terminal-state rules.

The React/TanStack Start dashboard uses one centralized fetch boundary and React
Query. It polls only the server-ranked queue, selects the persisted assessment
projection for review, and writes patient/encounter/observation/OCR/speech inputs
through their documented APIs. Cardiac model output, provisional triage, operational
priority, clinical reasoning, and their explanation channels remain visually and
semantically separate. There is no mock-data fallback.

## Medical-staff authentication boundary

`StaffUser` stores a normalized unique email, full name, Argon2 password hash,
role (`DOCTOR`, `NURSE`, or `ADMIN`), active state, and creation timestamp. There
is no signup API and accounts are created only through the explicit
`python -m app.create_staff` provisioning command.

`POST /api/auth/login` validates generic credentials and returns a short-lived
HS256 JWT access token. Signing uses `NEUROBOTS_AUTH_SECRET_KEY`. Local
`development` generates a cryptographically random process-local fallback when
the setting is empty; non-development environments require an explicit secret of
at least 32 characters. No signing secret is hard-coded.
`GET /api/auth/me` returns the active authenticated staff member and never the
password hash. A reusable FastAPI dependency protects the complete clinical API
router, while `/health` and login remain public. The dependency rechecks the
database account on each request, so disabled accounts lose API access even if a
previous token has not expired.

The frontend keeps the access token in browser session storage, adds it through
the centralized API client, and returns to the staff login screen on a 401. This
hackathon mechanism has no refresh token or server-side token revocation list and
is not a regulatory-compliance claim. Tokens created with the development fallback
expire immediately when the backend process restarts.

## Dynamic priority boundary

`NEUROBOTS Dynamic Priority Policy` version `dynamic-priority-1.0.0` is an
operational ordering policy, not cardiac probability and not ESI. A successful,
determinate persisted triage assessment is mandatory. Severity is the dominant
base score (`CRITICAL` 90, `VERY_HIGH`/`PROTOTYPE_ESI_2` 75, `HIGH` 60,
`MODERATE` 40, `ROUTINE` 20). Supported deterioration adds 15, thresholded high
positive cardiac output adds a fixed 5, and waiting adds one point per 30 minutes
capped at 5. Provisional state is preserved without a score penalty. Operational
bands are `CRITICAL`, `VERY_HIGH`, `HIGH`, `MODERATE`, and `ROUTINE`.

Vital policy `vital-deterioration-1.0.0` compares only the latest two
chronological readings. It detects heart-rate rise >=20, systolic-BP drop >=20,
SpO2 drop >=3, or respiratory-rate rise >=6. One reading or no comparable
supported fields produces `UNKNOWN`, never an invented trend. Queue ordering is
score descending, earlier `waiting_since`, earlier entry creation, then UUID.

## Prototype triage boundary

Policy `NEUROBOTS Prototype ESI Subset` version
`prototype-esi-subset-1.0.0` is informed by the Emergency Nurses Association ESI
Handbook v5 and AHRQ's ESI overview. It represents only a high-risk adult vital
screen and a local high-risk symptom cluster, plus supporting severe-distress and
cardiac-model signals. It never emits level 1 or levels 3–5 because the current
state lacks full decision-point inputs and anticipated resource count. All output
is provisional and not clinically validated.

Stable rules are `TRIAGE-001` adult high-risk vital screen, `TRIAGE-002` chest
pain plus dyspnea/sweating cluster, `TRIAGE-003` severe reported distress as a
consideration only, `TRIAGE-004` cardiac-model support only, and `TRIAGE-005`
provisional gating for missing full-ESI inputs.

## Current agent behavior

- Data Fusion selects the latest current-encounter vitals and latest lab per test.
- Triage/Risk derives encounter age, encodes gender, builds the eight-feature
  snapshot, invokes `CardiacRiskTool`, and persists successful predictions.
- Missing required features return `INCOMPLETE_INPUT`; no prediction is persisted.
- Independently, Triage/Risk invokes `EmergencyTriageTool` from fused context and
  optional cardiac context, then persists the result even when cardiac prediction
  is unavailable. `esi` and `assigned_priority` remain null.
- Clinical Reasoning sends a PHI-minimized payload to Groq. It omits names, phone
  number, external ID, database IDs, exact birth date, and raw notes. The model
  chooses tools dynamically and receives only filtered clinical tool results.
- The loop permits at most six model steps and five tool calls, rejects duplicate
  calls, applies a 45-second total budget, validates a strict Pydantic schema, and
  records an auditable trace without private chain-of-thought.
- Priority calls `DynamicQueueService`, updates the encounter queue projection,
  appends a calculation, records audit events, and populates
  `ClinicalState.priority`. It returns `PENDING_TRIAGE` without persistence when
  upstream triage is missing or undetermined.
- Multimodal loads persisted OCR documents, text, extracted fields, provenance,
  and conflicts into ClinicalState. OCR runs only at explicit ingestion time.
- Multimodal also loads persisted speech transcripts and extracted symptoms;
  Clinical NLP normalizes them without turning negated mentions into positives.
- XAI uses Tree SHAP for a successful prediction and exposes four separate
  channels: model contributions, deterministic triage rule trace, clinical
  reasoning evidence, and deterministic priority rule trace.
- Safety additionally validates priority policy/version, score/band,
  provisional consistency, triage/vital freshness, and absence of priority after
  a critical workflow halt. It never assigns priority.
- Counterfactual explanation and imaging saliency remain pending.

## Provider and edge boundary

`LLMProvider` is the replaceable interface; `GroqProvider` is the current
implementation. The cached provider safely reuses one lazily constructed Groq
client. The documented default is `openai/gpt-oss-20b`, selected from Groq's
current official catalog because it supports local tool calling, reasoning, JSON
Schema structured output, and low-latency inference. `GROQ_MODEL` overrides it.
A response reporting another model is rejected, preventing silent model switches.
Because Groq does not currently combine tool use and Structured Outputs in one
request, tool-selection turns run first and a separate strict JSON-Schema call
performs final synthesis.

Patient persistence, observations, cardiac ML, SHAP, triage, corpus, embeddings,
vector index, graph, and audit remain local. Only the PHI-minimized payload and
explicitly requested tool results leave the edge. Groq built-in web, browser,
code execution, arbitrary HTTP, filesystem, shell, and SQL tools are not exposed.

The minimized payload and selected tool results can still contain sensitive
clinical facts and observation timestamps. This is data minimization, not a claim
of complete de-identification; deployment still requires consent, vendor, access,
retention, and network review.

## Provisioning boundary

The raw dataset under `backend/data/raw/` and unapproved trained artifacts under
`backend/ml/artifacts/` are intentionally Git-ignored. For the connected
hackathon deployment, only the verified 444,973-byte
`cardiac_risk_random_forest_v1.0.0.joblib` is allow-listed and its recorded
SHA-256 is enforced during the container build. A clone without that file reports
cardiac inference unavailable until the approved checksum-bound dataset is
provisioned and `ml/train_cardiac_model.py` creates the artifact (or a governed
matching artifact is provisioned separately). The corpus, hashing index,
KG, metadata, migrations, and application code are tracked.

## Local RAG and medical knowledge graph

Corpus `acs-corpus-1.0.0` contains 12 compact paraphrased/source-attributed
chunks scoped to suspected ACS, myocardial infarction, and emergency chest-pain
support. Sources are the 2025 ACC/AHA/ACEP/NAEMSP/SCAI ACS resources, 2021
AHA/ACC Chest Pain guideline, 2023 ESC ACS guideline, Fourth Universal Definition
of MI, CDC, and AHA patient messages. It is explicitly non-comprehensive.

The retriever uses deterministic local embedding recipe
`sklearn-hashing-vectorizer-word-bigram-v1`, dimension 4096. Persisted index
`clinical-hashing-index-1.0.0` records corpus/model/dimension metadata. Queries
are capped at 500 characters, `top_k` at 5, snippets at 900 characters, and every
result includes provenance. This lightweight lexical embedding is a known
hackathon limitation, not a general medical semantic model.

NetworkX `MultiDiGraph` version `acs-kg-1.0.0` contains 17 nodes and 17 curated
edges. Every edge has an edge ID, relation, source ID, source reference, and graph
version. Queries are constrained text-to-edge lookups capped at eight results.

## Failure and audit

The existing shared trace contract and routing guards remain. Workflow audit emits
one started and one completed/failed event. Predictions, triage, explanations,
reasoning results, and priority calculations are append-only. Queue creation,
recalculation, and status changes emit `QUEUE_ENTRY_CREATED`,
`QUEUE_PRIORITY_RECALCULATED`, and `QUEUE_STATUS_CHANGED`. Missing key, timeout, API/provider error,
invalid structured output, duplicate loop, and step/tool exhaustion are isolated.
Cardiac inference, triage, SHAP, patient operations, Safety, XAI, and workflow
completion remain available.
