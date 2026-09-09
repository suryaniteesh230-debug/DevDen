# NextCare Project Context

Last updated: 2026-08-08

NextCare is an edge-first clinical decision-support prototype for suspected
myocardial infarction encounters. The backend now joins provenance-aware clinical
records, Supervisor-directed agents, conventional local cardiac classification,
append-only predictions, SHAP model contributions, an independent deterministic
Prototype ESI Subset, a genuinely agentic Clinical Reasoning specialist using
Groq plus local RAG and a local medical knowledge graph, and a persistent
deterministic dynamic patient queue.

The approved local dataset contains 1,319 Zheen Hospital observations described
by DOI `10.17632/65gxgy2nmg.2`. Model version `cardiac-risk-rf-1.0.0` is trained on
1,046 records and evaluated once on a stratified untouched set of 262 after 11
invalid rows were excluded. Positive sensitivity is 0.9938 on that split.

This performance is dataset-specific. The source does not reliably document
measurement units or assay details, biomarkers may encode contemporaneous
diagnostic evidence, and there is no external or clinical validation. Predictions
must never be presented as autonomous diagnosis.

Implemented: cardiac inference through the existing Triage/Risk Agent, exact
feature snapshots, prediction history, Tree SHAP through XAI, explanation
persistence, `NEUROBOTS Prototype ESI Subset` version
`prototype-esi-subset-1.0.0`, append-only triage assessments, reassessment from
the latest vital, missing-input isolation, Safety/XAI integration, workflow API
integration, local latency benchmarking, official Groq SDK/provider abstraction,
a PHI-minimized payload, dynamic five-tool loop, curated 12-chunk local corpus,
4096-dimensional persisted local vector index, 17-node/17-edge NetworkX graph,
strict qualitative differential schema, append-only reasoning persistence,
reasoning-aware Safety, `NEUROBOTS Dynamic Priority Policy`
`dynamic-priority-1.0.0`, repeated-vital deterioration detection, persistent
queue projection plus append-only calculations, ordered queue/status APIs,
queue auditing, priority-aware Safety, and a fourth priority trace in XAI.
Local clinical-document OCR is also implemented with Tesseract/Poppler, bounded
signature-validated uploads, versioned conservative lab parsing, append-only OCR
provenance, explicit conflict reporting, and manual-value precedence in fusion.
English speech-to-clinical-text is implemented through a replaceable Groq Whisper
adapter because no offline STT runtime is installed. Audio is not retained;
transcripts, model metadata, deterministic negation-aware symptom extraction,
SPEECH provenance, conflicts, and linked symptom IDs are persisted.
The backend API stabilization checkpoint adds consistent error envelopes,
restricted local CORS, queue transition validation/minimal display context,
clean latest-assessment and assessment-history projections, and an OpenAPI surface
with compatibility/debug aliases hidden.

Medical-staff authentication is now implemented without public registration.
Persistent `StaffUser` records use Argon2 password hashes and the initial
`DOCTOR`, `NURSE`, and `ADMIN` role enum. A short-lived environment-signed bearer
token plus a shared FastAPI dependency protects the clinical router, while health
and login stay public. The frontend starts at a matching staff login screen,
automatically attaches the token, and returns to login when authentication fails.

The policy is informed by the Emergency Nurses Association ESI Handbook v5 and
AHRQ's ESI overview. It can surface a provisional level-2 pattern from an adult
high-risk vital screen or explicit high-risk symptom cluster. It cannot implement
level 1 or distinguish levels 3–5 because immediate-intervention, mental-status,
clinician high-risk, and anticipated-resource inputs are unavailable. It is a
hackathon clinical decision-support prototype, is not clinically validated, and
does not replace clinician assessment.

Groq is optional and outside the fast path. The application never sends names,
phone numbers, external/database identifiers, exact DOB, or raw notes in the
initial cloud payload. Missing key, timeout, invalid output, and API failure do not
remove or overwrite deterministic results. The small RAG corpus and KG are
source-attributed but not comprehensive, and Groq output remains non-diagnostic.

The teammate frontend is integrated with the persisted backend contract while
preserving its visual language. It supports patient registration/search/history,
encounter creation, manual observations, OCR and speech intake, workflow runs,
queue polling/status changes, and review of the four distinct assessment channels.
Mock clinical data and unsupported wearable, imaging, prescription, EHR, and
fabricated-auth paths were removed. Provider failure is rendered explicitly.

The restricted raw cardiac dataset and unapproved `.joblib` artifacts are ignored.
The verified 444,973-byte hackathon artifact is allow-listed and checksum-verified
in the Vercel container; a clone without it must provision the approved dataset
and reproduce or supply the matching artifact before cardiac ML/SHAP is available. No automatic dataset
download is implemented. The root README is the judge/developer entry point and
maps architecture, commands, APIs, benchmarks, deliverables, challenge
requirements, privacy boundaries, and limitations to the implemented code.

The final development seed is idempotent and clearly synthetic. `DEMO-001` is a
returning patient with historical and current encounters, complete chest-pain
inputs, and repeated current vitals; `DEMO-002` through `DEMO-010` create varied
symptom-based cardiac, respiratory, infectious, metabolic, renal, hypertensive,
and injury cases. Triage-determinate cases enter the ranked queue; the rest stay
in pending intake. Their local workflows are seeded with Groq unavailable so
judge setup never makes an implicit cloud request.

Pending: full clinically reviewed ESI, medication intelligence, counterfactual
and imaging explanations, background/event-driven queue recalculation, and all
clinical validation.

NextCare is the official product name. The implementation retains the historical
`NEUROBOTS` codename only where compatibility requires it, including environment
variables and persisted policy identifiers.
