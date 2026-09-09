# NextCare Backend Environment

Last updated: 2026-08-08

## Supported Python

The backend declares Python `>=3.12,<3.14` and was verified with Python 3.13.12.
Do not use the old repository-root `.venv`; create `backend/.venv` from the
dependency declaration.

## Setup with uv

Run from the repository root:

```bash
cd backend
uv sync --extra dev --locked
cp .env.example .env
# Generate a secret with `openssl rand -hex 32` and paste it into
# NEUROBOTS_AUTH_SECRET_KEY in backend/.env.
.venv/bin/alembic upgrade head
.venv/bin/python -m app.create_staff \
  --email doctor@nextcare.demo \
  --full-name "Dr. Demo" \
  --role DOCTOR
```

## Run

From `backend/`:

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The health endpoint is `http://127.0.0.1:8000/health`; generated API documentation
is at `http://127.0.0.1:8000/docs`.

## Test

From `backend/`:

```bash
.venv/bin/python -m pytest
```

Tests use a separate temporary SQLite database and do not modify the development
database.

The current deployment checkpoint has 114 passing tests. Automated tests use scripted/mock
providers and never require a live API key.

## Frontend setup and verification

From `frontend/`:

```bash
ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci --ignore-scripts
npm run dev -- --host 127.0.0.1 --port 5173
npm run lint -- --quiet
npm run typecheck
npm run build
```

The centralized client defaults to `http://127.0.0.1:8000` during development and
to the current origin in production. Set `VITE_API_BASE_URL=/` for Vercel's
same-origin routing, or set an explicit origin in `frontend/.env.local`. The UI has no mock
fallback; an unreachable backend is displayed as unavailable.

With both servers running, exercise the real registration-to-dashboard contract:

```bash
cd backend
.venv/bin/python scripts/verify_vertical_slice.py
```

The verifier creates clearly synthetic development records, submits manual
symptoms/vitals/labs, runs the Supervisor, checks persisted assessment/history and
the server-ranked queue, and confirms that the frontend is served. It is intended
for a development database, not production.

The test bootstrap clears `GROQ_API_KEY` before importing the application, so a
developer shell cannot accidentally send live requests. Automated verification
therefore remains deterministic even when an ignored local credential exists.

## ML dependencies and reproduction

The lockfile pins the resolved Python 3.13 environment, including NumPy 2.1.3,
scikit-learn 1.9.0, joblib 1.5.3, SHAP 0.52.0, Numba 0.66.0, llvmlite 0.48.0,
official Groq SDK 0.37.1, and NetworkX 3.6.1.
Numba/llvmlite are constrained explicitly because unconstrained SHAP resolution
selected an obsolete llvmlite incompatible with Python 3.13.

From `backend/`, recreate training metadata and the ignored artifact with:

```bash
.venv/bin/python ml/train_cardiac_model.py
```

Run the warmed service benchmark with:

```bash
.venv/bin/python ml/benchmark_cardiac_model.py
.venv/bin/python triage/benchmark_triage_policy.py
.venv/bin/python triage/demo_triage_reassessment.py
.venv/bin/python clinical_knowledge/benchmark_local_knowledge.py
.venv/bin/python clinical_knowledge/benchmark_reasoning_agent.py
.venv/bin/python priority/benchmark_dynamic_queue.py
.venv/bin/python priority/demo_dynamic_queue.py
```

The latest 500-run `CardiacRiskTool` benchmark measured mean 14.64 ms, p50 14.52
ms, and p95 15.33 ms. The Triage/Risk Agent including SQLite persistence measured
mean 15.48 ms, p50 15.35 ms, and p95 16.33 ms over 50 runs.

The latest 1,000-run standalone `EmergencyTriageTool` benchmark measured mean
0.0106 ms, p50 0.0093 ms, and p95 0.0157 ms. The 500-run combined
`CardiacRiskTool` + `EmergencyTriageTool` fast path measured mean 14.64 ms, p50
14.46 ms, and p95 15.52 ms, below the 500 ms target. These fast-path measurements
exclude HTTP, LangGraph, persistence, and SHAP. The demo command writes the full
two-run API evidence to `triage/reassessment_demo.json`.

The 1,000-run warm local knowledge benchmark measured RAG mean 0.3937 ms,
p50 0.3749 ms, p95 0.5231 ms and KG mean 0.1418 ms, p50 0.1339 ms, p95 0.1881
ms. A 200-run complete ClinicalReasoningAgent benchmark with a zero-latency
scripted provider measured mean 5.7264 ms, p50 5.3945 ms, p95 6.1045 ms. That
measurement includes local RAG, KG, validation, and SQLite persistence but excludes
Groq network latency. Results are in `clinical_knowledge/latency_benchmark.json`.

## Live Groq verification

On 2026-08-08, `openai/gpt-oss-20b` authenticated through `GroqProvider` and
returned a minimal strict structured response in 776.386 ms. The single live HTTP
clinical workflow completed without halting in 5,253.397 ms; cardiac risk, triage,
Safety, SHAP, and all three then-existing XAI channels remained available. Clinical Reasoning
took 5,124.599 ms and dynamically selected patient history, local guideline
retrieval, then the medical KG. The three successful Groq tool-selection turns
took 2,261.945 ms, 881.473 ms, and 1,582.671 ms. A subsequent Groq request followed
the sanitized `APIStatusError`/`PROVIDER_FAILURE` path before strict synthesis, so
the live reasoning result is partial rather than live-verified. No retry was made.

The final 2026-08-08 checkpoint ran one additional synthetic reasoning workflow.
The workflow completed and preserved all local channels. Groq selected local RAG,
whose tool execution succeeded, then a subsequent provider request followed the
sanitized `PROVIDER_FAILURE` path. The agent measured 3,786.711 ms total and
3,601.649 ms provider latency. It did not produce a live structured reasoning
result, so live synthesis remains unverified.

The same checkpoint ran exactly one live STT call using a 7.24-second offline-
synthesized, non-sensitive English fixture. `whisper-large-v3-turbo` returned the
intended synthetic sentence in 1,273.694 ms. Local extraction persisted chest
pain and sweating as present, shortness of breath as explicitly negated, and all
linked observations with `SPEECH` provenance. Audio bytes were not retained.

## Dynamic queue verification

The 300-run `DynamicQueueService` benchmark, including SQLite projection/history
persistence and focused audit, measured mean 2.3651 ms, p50 2.3298 ms, and p95
2.7503 ms. The warmed 300-run `CardiacRiskTool` + `EmergencyTriageTool` +
`DynamicQueueService` local path measured mean 17.2662 ms, p50 17.1613 ms, and
p95 17.9381 ms. It excludes HTTP, LangGraph, SHAP, and Groq latency and remains
comfortably under the 500 ms target. Results are in
`priority/latency_benchmark.json`.

`priority/demo_dynamic_queue.py` creates four waiting encounters, runs their real
local LangGraph workflows with cloud reasoning explicitly unavailable, adds a
new worsening vital to one encounter, and reruns that workflow. JSON evidence is
written to `priority/dynamic_queue_demo.json`.

## Seed demo data

After applying migrations, run from `backend/`:

```bash
.venv/bin/python -m app.seed
```

The idempotent seed creates ten clearly synthetic active patients and runs
their deterministic local workflows with Groq deliberately unavailable.
`DEMO-001` is the returning primary case with one completed historical encounter,
one current chest-pain encounter, three supported labs, and two current vital
measurements that trigger a deterioration comparison. `DEMO-002` through
`DEMO-010` provide varied symptom-based cases across cardiac, respiratory,
infectious, metabolic, renal, hypertensive, and injury concerns. Cases supported
by the narrow triage subset enter the queue; the rest remain in pending intake.

## Configuration

Copy `.env.example` to `.env` only when overriding defaults. All backend settings
have defaults; Groq credentials are required only for the two online capabilities.
Supported variables:

- `NEUROBOTS_APP_NAME` — API/OpenAPI title.
- `NEUROBOTS_DATABASE_URL` — SQLAlchemy URL; default is local
  `backend/neurobots.db`. Cloud deployments use managed PostgreSQL, for example
  `postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require`.
- `DATABASE_URL` — provider-compatible fallback alias for the database URL.
  `postgres://` and `postgresql://` values are normalized to
  `postgresql+psycopg://`.
- `NEUROBOTS_AUTH_SECRET_KEY` — JWT signing secret for staff login; generate at
  least 32 random characters and never commit it. When empty, only the
  `development` environment uses a random process-local fallback, so tokens are
  invalidated by every backend restart. All other environments reject login.
- `NEUROBOTS_AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` — staff access-token lifetime;
  default `30`, accepted range 5–1440 minutes.
- `NEUROBOTS_ENVIRONMENT` — service environment label returned by `/health`.
- `NEUROBOTS_HEART_ATTACK_MODEL_PATH` — model artifact path; defaults to
  `backend/ml/artifacts/cardiac_risk_random_forest_v1.0.0.joblib`.
- `NEUROBOTS_CARDIAC_FEATURE_SCHEMA_PATH` — stable raw-to-internal feature schema;
  defaults to `backend/ml/feature_schema.json`.
- `GROQ_API_KEY` — Groq secret. Leave blank when cloud reasoning is unavailable;
  never commit or log a real value.
- `GROQ_MODEL` — optional model override. The documented default is
  `openai/gpt-oss-20b`.
- `GROQ_SPEECH_MODEL` — optional speech model override; default is
  `whisper-large-v3-turbo`.
- `NEUROBOTS_CLINICAL_CORPUS_PATH` — local RAG corpus path.
- `NEUROBOTS_CLINICAL_VECTOR_INDEX_PATH` — local hashing-index path.
- `NEUROBOTS_MEDICAL_KNOWLEDGE_GRAPH_PATH` — local KG JSON path.
- `NEUROBOTS_CLINICAL_REASONING_MAX_STEPS` — reasoning-step cap; default `6`.
- `NEUROBOTS_CLINICAL_REASONING_MAX_TOOL_CALLS` — tool-call cap; default `5`.
- `NEUROBOTS_CLINICAL_REASONING_TIMEOUT_SECONDS` — total reasoning budget;
  default `45`.
- `NEUROBOTS_DOCUMENT_UPLOAD_MAX_BYTES` — document limit; default `10485760`.
- `NEUROBOTS_OCR_TIMEOUT_SECONDS` — OCR command timeout; default `30`.
- `NEUROBOTS_OCR_MAX_PDF_PAGES` — PDF page cap; default `5`.
- `NEUROBOTS_TESSERACT_COMMAND` — Tesseract executable; default `tesseract`.
- `NEUROBOTS_PDFTOPPM_COMMAND` — Poppler executable; default `pdftoppm`.
- `NEUROBOTS_SPEECH_UPLOAD_MAX_BYTES` — audio limit; default `20971520`.
- `NEUROBOTS_SPEECH_TIMEOUT_SECONDS` — STT timeout; default `45`.
- `NEUROBOTS_CORS_ORIGINS` — JSON list of exact frontend origins.

Model choice was verified against Groq's official
[`openai/gpt-oss-20b` model page](https://console.groq.com/docs/model/openai/gpt-oss-20b),
[local tool-calling guide](https://console.groq.com/docs/tool-use/local-tool-calling),
and [Structured Outputs guide](https://console.groq.com/docs/structured-outputs).
The last guide documents that tool use and Structured Outputs require separate
requests, which the provider implementation follows.

No API key is required for tests or the deterministic fast path. Missing Groq
configuration produces a provider-unavailable reasoning result and the workflow
continues. Corpus, embeddings/index, graph, cardiac inference, triage, and SHAP
remain local and need no runtime internet. LangGraph 1.2.10 compiles under Python
3.13.12.

`.env`, virtual environments, SQLite databases, raw datasets, unapproved ML
artifacts, and frontend dependencies are excluded by the root `.gitignore`. The
verified cardiac `.joblib` is the sole artifact allow-listed for the hackathon
container.

## Vercel and managed PostgreSQL

The backend runtime includes `psycopg[binary]`. Use the repository root as the
Vercel project root; `vercel.json` declares the `frontend/` and `backend/`
services. Copy variable names from `vercel.env.example`, generating the JWT secret
with `openssl rand -hex 32`. Do not paste real values into tracked files.
The verified backend image is approximately 1.44 GB, so an older project that is
not automatically enrolled in Large Functions must set
`VERCEL_SUPPORT_LARGE_FUNCTIONS=1` before redeploying.

After Neon is connected and before every release, run from `backend/`:

```bash
export NEUROBOTS_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require'
scripts/migrate_postgres.sh
```

Create a staff account only when one is needed:

```bash
.venv/bin/python -m app.create_staff \
  --email doctor@nextcare.demo \
  --full-name "Dr. Demo" \
  --role DOCTOR
```

The migration script refuses non-PostgreSQL URLs. The account command prompts
twice, without echo, for an at-least-eight-character password. The convenience
`scripts/provision_postgres.sh` combines both for a brand-new database. There is
no startup migration or public account-creation path.

## Staff account provisioning

There is no registration API and application startup never creates an account.
After migrations, run `.venv/bin/python -m app.create_staff` with `--email`,
`--full-name`, and optional `--role DOCTOR|NURSE|ADMIN`. The command prompts for
the password twice without echoing it, requires at least 8 characters, hashes it
with Argon2, and rejects duplicate emails. Use only clearly synthetic credentials
for a shared hackathon demo database. Start both services and open
`http://127.0.0.1:5173`, then sign in with the provisioned email and password.

## Local OCR runtime

OCR uses the host `tesseract` and `pdftoppm` executables. The verified host has
Tesseract 5.5.3 and Poppler. English trained data is preferred; this host exposes
only `afr` plus `osd`, so the service uses the Afrikaans Latin-script model as a
documented fallback and records `lang=afr` with each result. Install Tesseract
English data for production-quality English OCR. No cloud OCR or runtime Python
OCR package is required.

Document defaults are 10 MiB maximum, five PDF pages, and a 30-second OCR
timeout. They are configurable with `NEUROBOTS_DOCUMENT_UPLOAD_MAX_BYTES`,
`NEUROBOTS_OCR_MAX_PDF_PAGES`, `NEUROBOTS_OCR_TIMEOUT_SECONDS`,
`NEUROBOTS_TESSERACT_COMMAND`, and `NEUROBOTS_PDFTOPPM_COMMAND`.

## Speech runtime

No offline STT model or runtime is installed. Explicit audio ingestion uses the
official Groq SDK and `whisper-large-v3-turbo`, English only. Supported formats
are WAV, MP3, MP4/M4A, OGG, WebM, and FLAC; uploads default to a 20 MiB limit and
a 45-second provider timeout. Audio bytes are discarded after the request; only
the transcript, hash, provider/model metadata, local symptom extraction, and
provenance are persisted. Missing credentials return
`SPEECH_PROVIDER_UNAVAILABLE` without affecting local workflow capabilities.

Configure the limit and timeout with `NEUROBOTS_SPEECH_UPLOAD_MAX_BYTES` and
`NEUROBOTS_SPEECH_TIMEOUT_SECONDS`.

Local frontend CORS defaults to `localhost` and `127.0.0.1` on ports 3000 and
5173. Override `NEUROBOTS_CORS_ORIGINS` with a JSON list for another environment;
do not use an unrestricted production origin.

`backend/.env.example` contains blank Groq placeholders and safe local paths. A
real ignored `backend/.env` may exist on a developer machine but is never a
repository prerequisite. No key or raw provider request should be printed,
logged, or written to project documentation.

## Fresh-clone model provisioning

`backend/data/raw/` and unapproved `backend/ml/artifacts/` files are ignored. The
verified hackathon `.joblib` is allow-listed and its SHA-256 is recorded. A clone
without that file can run the API, database, triage, queue, RAG/KG, and OCR, but
cardiac ML and SHAP remain unavailable. Place only the approved checksum-bound
dataset at `data/raw/Heart Attack.csv`, then run `.venv/bin/python ml/train_cardiac_model.py`.
Do not automatically download or substitute clinical data.
