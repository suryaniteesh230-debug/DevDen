# NextCare: Complete Local Run Walkthrough

This guide starts the complete NextCare project locally: the FastAPI backend,
SQLite database, optional cardiac-risk model, optional Gemini features, and the
React dashboard.

> [!CAUTION]
> NextCare is a hackathon clinical decision-support prototype. It is not a
> medical device and must not be used in place of professional medical care.

## 1. Open a terminal in the repository

All paths below assume the terminal starts in the repository root—the directory
that contains `backend/`, `frontend/`, and this file.

```bash
cd /path/to/NextCare
```

## 2. Check the prerequisites

Required:

- Python `3.12` or `3.13` (Python `3.14` is not supported)
- [`uv`](https://docs.astral.sh/uv/) for the Python environment
- Node.js `^20.19.0` or `>=22.12.0`
- npm

Check the installed versions:

```bash
python3 --version
uv --version
node --version
npm --version
```

OCR uploads additionally require Tesseract, English language data, and Poppler.
On Ubuntu/Debian, install them with:

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-eng poppler-utils
```

Confirm that the OCR commands are available:

```bash
tesseract --version
tesseract --list-langs
pdftoppm -v
```

The browser microphone feature also requires a current browser with
`MediaRecorder` support and microphone permission.

## 3. Install and configure the backend

From the repository root:

```bash
cd backend
uv sync --extra dev --locked
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

The final command should report `20260808_0007 (head)`. SQLite is used, so no
separate database server is needed. By default, the database is created at
`backend/neurobots.db`.

### Optional: enable Gemini reasoning and speech transcription

The local application runs without Gemini. To enable the online clinical-reasoning
and speech features, open `backend/.env` and set:

```dotenv
GEMINI_API_KEY=your_Gemini_api_key
GEMINI_MODEL=gemini-3.6-flash
GEMINI_SPEECH_MODEL=gemini-3.6-flash
```

Do not commit `backend/.env`. Gemini features require internet access. If the key
is left blank, those features are shown as unavailable while the local workflow
continues to work.

## 4. Provision the cardiac-risk model

The raw clinical dataset and generated model are intentionally excluded from
Git. Without the model, the backend and deterministic triage still run, but
cardiac probability and SHAP explanations are unavailable.

To enable them:

1. Obtain the approved `Heart Attack.csv` dataset described in the root
   `README.md` and `backend/ml/feature_schema.json`.
2. Put it at exactly:
   `backend/data/raw/Heart Attack.csv`.
3. While still inside `backend/`, verify that its SHA-256 is
   `f090acd9aa6ed0df3abd55832a82bf932dcf71987175f68617dd57fb074f4665`:

```bash
sha256sum "data/raw/Heart Attack.csv"
```

4. Train and validate the model:

```bash
.venv/bin/python ml/train_cardiac_model.py
```

The command should create:

```text
backend/ml/artifacts/cardiac_risk_random_forest_v1.0.0.joblib
```

Do not substitute an unverified dataset or commit the raw data/model artifact.

## 5. Add the synthetic demo patients

Still inside `backend/`, run the idempotent development seed:

```bash
.venv/bin/python -m app.seed
```

This creates ten synthetic patients (`DEMO-001` through `DEMO-010`), their
encounters, observations, and assessments. Cases supported by the prototype's
narrow triage rules enter the ranked queue; the others remain in pending intake.
It is safe to run the seed again; it repairs marked demo records to the canonical
sample data without changing non-demo patients.

## 6. Install and configure the frontend

Return to the repository root, enter `frontend/`, install the locked dependency
versions, and create the local environment file:

```bash
cd ../frontend
ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci --ignore-scripts
cp .env.example .env.local
```

The default frontend setting is:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

No change is necessary when using the ports in this walkthrough.

## 7. Start the backend

Open a new terminal at the repository root and run:

```bash
cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Keep this terminal running. Confirm the backend in a browser or another
terminal:

```bash
curl http://127.0.0.1:8000/health
```

The response should contain `"status":"ok"`.

## 8. Start the frontend

Open another terminal at the repository root and run:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Keep this terminal running, then open:

- Dashboard: <http://127.0.0.1:5173>
- Backend health: <http://127.0.0.1:8000/health>
- Interactive API documentation: <http://127.0.0.1:8000/docs>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>

## 9. Exercise the complete application

In the dashboard:

1. Select one of the seeded patients from the queue, or search for `DEMO-001`.
2. Review or add symptoms, vitals, and lab results.
3. Optionally upload a printed clinical document to exercise local OCR.
4. If Gemini is configured, optionally record or upload audio for transcription.
5. Run the clinical workflow.
6. Review the separate cardiac-risk, provisional-triage, clinical-reasoning,
   operational-priority, and explainability results.

The queue refreshes from the backend every five seconds. Clinical results and
queue order come from persisted backend data rather than frontend mock data.

### Suggested five-minute judge demonstration

Click **Judge demo** in the dashboard header for an interactive guide that jumps
to each live proof point. The strongest end-to-end sequence is:

1. Select `DEMO-001` and establish that cardiac risk, prototype triage, clinical
   reasoning, and operational priority are four independent channels—not one
   opaque score.
2. Open **Inputs**, add a second vital reading that worsens one of the supported
   trends, then rerun the workflow. Show that the same queue entry is
   recalculated and may move while prior assessment snapshots remain preserved.
3. Open **Reasoning** and interact with a SHAP bar, a deterministic rule row, an
   evidence reference, and a controlled tool call. This demonstrates several
   types of explainability rather than presenting model output as clinical
   causation.
4. Upload a synthetic report or record synthetic speech. Show the source label,
   extracted observations, explicit negation, and preserved source conflicts.
5. If Gemini is intentionally unavailable, show that reasoning reports the provider
   failure while the local cardiac, triage, safety, queue, and explanation path
   remains usable. This is an edge-resilience feature, not a broken demo.

Claims that are directly supported by the implementation:

- **Edge-first resilience:** the deterministic fast path does not depend on a
  cloud LLM.
- **No score collapse:** model probability, provisional ESI subset, qualitative
  reasoning, and operational priority retain different contracts.
- **Dynamic reassessment:** repeated vitals can change deterioration state and
  queue order without overwriting history.
- **Provenance-aware multimodal intake:** manual, OCR, and speech observations
  remain attributable; conflicts are visible and manual entries retain
  precedence in the current projection.
- **Layered explainability:** SHAP, policy rules, retrieved evidence, knowledge
  graph edges, and controlled tool traces answer different audit questions.
- **Privacy-aware reasoning boundary:** the initial cloud reasoning payload omits
  names, phone numbers, IDs, exact birth dates, and raw clinician notes.

Avoid claiming clinical validation, production medical-device status, complete
ESI coverage, or diagnostic causation. The defensible improvement is safer,
more auditable decision support under explicit prototype constraints.

## 10. Verify the installation

Run the backend checks from a third terminal:

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m compileall -q app migrations scripts ml triage priority clinical_knowledge
```

Run the frontend checks:

```bash
cd ../frontend
npm run lint -- --quiet
npm run typecheck
npm run build
```

With the backend on port `8000`, the frontend on port `5173`, and the model
provisioned, the end-to-end verifier can also be run from `backend/`:

```bash
cd ../backend
.venv/bin/python scripts/verify_vertical_slice.py
```

> [!IMPORTANT]
> The vertical-slice verifier creates synthetic records and changes the
> configured development database. Do not run it against a production database.

## 11. Stop the project

Press `Ctrl+C` once in the frontend terminal and once in the backend terminal.
The SQLite data remains in `backend/neurobots.db` for the next run.

## Subsequent runs

After the first setup, only two commands are needed in separate terminals.

Backend:

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

## Common startup problems

- **Python reports an unsupported version:** install Python 3.12 or 3.13, then
  make `uv` use it with `uv python pin 3.13` before running `uv sync` again.
- **Cardiac model is unavailable:** verify that the `.joblib` file exists at the
  exact artifact path in step 4 and restart the backend.
- **Gemini features are unavailable:** verify `GEMINI_API_KEY` in `backend/.env`,
  internet connectivity, and then restart the backend.
- **OCR is unavailable:** verify `tesseract`, the English language pack, and
  `pdftoppm` using the commands in step 2.
- **The dashboard cannot reach the API:** make sure the backend is running on
  port `8000` and `frontend/.env.local` points to
  `http://127.0.0.1:8000`.
- **Port `8000` or `5173` is already in use:** stop the process occupying the
  port, or change the port and update both `VITE_API_BASE_URL` and the backend
  CORS origin configuration accordingly.
