# NextCare Clinical Workflow

Last updated: 2026-08-08

## Invocation

Python: `run_clinical_assessment(patient_id, encounter_id, session=...)`.

HTTP: `POST /api/encounters/{encounter_id}/workflow`.

## Supervisor execution

Intake enters Supervisor. Supervisor deterministically routes Patient Resolution,
Multimodal, Clinical NLP, Data Fusion, Triage/Risk, Clinical Reasoning, Priority,
Safety, and XAI; every specialist returns to Supervisor. The policy remains
deterministic and replaceable. Groq is used only inside the non-critical Clinical
Reasoning specialist.

## Functional cardiac path

After Data Fusion, Triage/Risk builds exactly these features from current state:
encounter age, encoded gender, latest heart rate/systolic/diastolic BP, and latest
blood sugar/CK-MB/troponin. Previous vitals are never substituted for the latest
reading. The exact numeric snapshot and observation references are retained.

Complete input invokes the warmed `CardiacRiskTool`, then appends a
`RiskPrediction`. Incomplete input produces `INCOMPLETE_INPUT`, lists missing
features in state, and persists no risk prediction.

Independently of that result, the same agent passes fused context and optional
cardiac context to `EmergencyTriageTool`. Policy
`prototype-esi-subset-1.0.0` evaluates `TRIAGE-001` through `TRIAGE-005`, appends
a `TriageAssessment`, and returns a provisional `PROTOTYPE_ESI_2` or
`UNDETERMINED`. Cardiac probability is supporting context only: it cannot become
severity. `esi` and `assigned_priority` remain null because operational queue
priority is a separate downstream contract.

When a prediction exists, XAI invokes Tree SHAP, appends an `Explanation`, and
returns eight ranked model feature contributions plus the real agent decision
trace. It exposes deterministic triage rules, clinical reasoning evidence, and
priority rules as separate channels from `model_contributions`. SHAP values
describe model behavior, not clinical causation.

## OCR document path

The document API processes bounded signature-validated images/PDFs through the
reusable local `TesseractOCRService`, then uses
`clinical-document-parser-1.0.0` to extract only allow-listed numeric labs.
`ClinicalDocument`, OCR lab observations, provenance, conflicts, and a focused
audit are persisted together. Uploaded bytes are not retained.

On the next workflow run, Multimodal loads the document text/results into
ClinicalState. Data Fusion preserves every lab row, exposes document conflicts,
and selects the latest manual value for a test when manual and OCR values coexist.
OCR never performs medical-image diagnosis.

## Speech path

The speech API validates and bounds an explicitly uploaded audio file, then calls
the replaceable `SpeechService`. The current adapter uses Groq
`whisper-large-v3-turbo` for English transcription because no local STT model is
installed. It does not diagnose and audio bytes are not persisted.

`clinical-text-extractor-1.0.0` deterministically recognizes an allow-list of
symptom phrases and nearby negation. The transcript and provider/model metadata,
extracted symptom records with source `SPEECH`, conflicts, and audit are persisted
together. Multimodal loads these records on the next workflow; Clinical NLP
normalizes them. Data Fusion retains all symptom assertions, surfaces conflicts,
and uses manual assertions in its current projection when sources disagree.

## Dynamic priority path

Priority requires a successful, determinate persisted triage assessment. Missing
or `UNDETERMINED` triage yields `PENDING_TRIAGE` and no queue row. Otherwise the
existing Priority Agent invokes `DynamicQueueService`, evaluates `NEUROBOTS
Dynamic Priority Policy` `dynamic-priority-1.0.0`, updates the current one-per-
encounter `QueueEntry`, appends `QueuePriorityCalculation`, records a focused
queue audit, and populates `ClinicalState.priority`.
Creation emits `QUEUE_ENTRY_CREATED`; later calculations emit
`QUEUE_PRIORITY_RECALCULATED`; operational status changes emit
`QUEUE_STATUS_CHANGED`.

Rules remain separate: `PRIORITY-001` severity base, `PRIORITY-002` repeated-
vital deterioration, `PRIORITY-003` fixed thresholded cardiac support,
`PRIORITY-004` capped waiting adjustment, and `PRIORITY-005` provisional flag.
Cardiac probability never becomes the score, and the resulting band is not ESI.
Waiting adds one point per 30 minutes up to five.

Deterioration compares only the two latest chronological readings and checks
heart-rate rise >=20, systolic-BP drop >=20, SpO2 drop >=3, and respiratory-rate
rise >=6. One reading or no comparable fields is `UNKNOWN`. Ranking is score
descending, earlier waiting start, earlier queue entry, then UUID.

Safety runs after Priority and validates metadata, values, provisional state,
and triage/vital snapshot freshness without assigning priority. XAI then emits
four separate explanation channels.

## Agentic reasoning path

After the fast path, Clinical Reasoning builds `PHI-minimized reasoning payload
v1`: approximate age, relevant gender, normalized symptoms, current values,
cardiac model output, and prototype triage output. It excludes names, phone,
external/database IDs, exact DOB, and raw notes.

Groq model `openai/gpt-oss-20b` is the configurable default behind `LLMProvider`.
The model sees exactly five local functions and chooses useful calls:

```text
get_patient_history
get_current_vitals
get_current_labs
retrieve_clinical_guidelines
query_medical_knowledge_graph
```

Patient and encounter IDs are bound locally, not model arguments. Tool results are
structured, capped, and provenance-bearing. The model may request another tool or
finish with the strict Pydantic schema; no call or ordering is mandatory.

The loop stops after six reasoning steps, five calls, a duplicate call, 45 seconds,
invalid output, or provider failure. It records tool, purpose, result references,
status, and latency, never chain-of-thought. Successful output contains qualitative
differential considerations, symptom associations, actual RAG/KG evidence, missing
information, evidence-backed considerations, uncertainty, and limitations.
`ClinicalReasoningResult` persists every success or safe failure.

After workflow completion, the UI reads the persisted latest projection from
`GET /api/encounters/{encounter_id}/assessment`. Historical review uses the
corresponding `assessment-history` endpoint. These projections never merge the
four distinct assessment channels into one score.

Safety checks schema/grounding/provenance, empty retrieval, provider failure,
excess certainty, invented numeric disease probability, and obvious deterministic
contradictions. It never overwrites valid cardiac or triage data. Missing key,
timeout, API failure, and invalid output leave the deterministic path intact.

Reassessment is explicit: add a timestamped vital measurement, invoke the same
workflow endpoint again. The latest vital produces new append-only
RiskPrediction/TriageAssessment/Explanation/QueuePriorityCalculation records;
the current QueueEntry is recalculated and the queue may reorder. Older snapshots
remain unchanged.

## Reproduction

From `backend/`:

```bash
.venv/bin/python -m app.seed
.venv/bin/python ml/train_cardiac_model.py
.venv/bin/python ml/benchmark_cardiac_model.py
.venv/bin/python triage/benchmark_triage_policy.py
.venv/bin/python triage/demo_triage_reassessment.py
.venv/bin/python clinical_knowledge/benchmark_local_knowledge.py
.venv/bin/python clinical_knowledge/benchmark_reasoning_agent.py
.venv/bin/python priority/benchmark_dynamic_queue.py
.venv/bin/python priority/demo_dynamic_queue.py
.venv/bin/python -m pytest
```

The idempotent seed creates a ten-patient synthetic judge dataset. The primary
`DEMO-001` case has historical and current encounters plus repeated current
vitals; the other cases vary symptoms, physiology, and available labs. Seed
workflows deliberately use the provider-unavailable path and never make a cloud
request. Triage-determinate cases enter the queue, while cases outside the
prototype's narrow triage subset remain in pending intake.

Training validates the approved checksum/schema, excludes documented invalid
rows, uses a stratified split and seed 42, compares Logistic Regression and Random
Forest, and writes versioned metadata/artifact outputs. The raw dataset and
unapproved artifacts are Git-ignored; the single verified hackathon `.joblib` is
allow-listed and checksum-bound. Provision the approved
`data/raw/Heart Attack.csv` before retraining.

For the integrated UI boundary, start FastAPI on port 8000 and Vite on port 5173,
then run `.venv/bin/python scripts/verify_vertical_slice.py` from `backend/`. The
current verifier completed two workflows with successful cardiac, SHAP, and
triage channels; preserved provider-unavailable reasoning isolation; detected
worsening vitals; updated the same queue entry to `CRITICAL` at rank 1; exercised
`WAITING → CALLED → IN_ASSESSMENT`; returned append-only history; and confirmed
that the frontend was served. The script does not perform browser automation;
there is no committed frontend browser/component test suite.
