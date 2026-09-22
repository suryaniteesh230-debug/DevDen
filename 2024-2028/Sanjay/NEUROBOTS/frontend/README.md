# NextCare Clinical Dashboard

The frontend is the real React 19/TanStack Start interface for the NextCare
FastAPI backend. It preserves the teammate dashboard design while using persisted
backend data; there is no mock-data or offline fallback path.

## What the dashboard supports

- Polling the server-ranked waiting queue and updating operational queue status.
- Searching/registering patients and reviewing encounter history.
- Creating encounters and appending manual symptoms, vitals, and labs.
- Uploading bounded clinical documents for local OCR and lab extraction.
- Recording or uploading audio for optional Gemini transcription and local symptom
  extraction.
- Running the Supervisor workflow and reviewing four distinct outputs: cardiac
  model risk, provisional triage, operational priority, and clinical reasoning.
- Reviewing SHAP model contributions and separate triage, priority, and evidence
  traces without presenting them as one confidence score.

Unsupported imaging diagnosis, prescription intelligence, EHR import, wearable
streaming, and fabricated fallbacks are intentionally absent.

The raw cardiac dataset and trained artifact are intentionally Git-ignored. In a
fresh clone, provision/train the backend model as described in the root README
before expecting cardiac risk and SHAP output; the UI renders their absence as an
unavailable capability.

## Run locally

Start the backend on `http://127.0.0.1:8000`, then:

```bash
ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci --ignore-scripts
npm run dev -- --host 127.0.0.1 --port 5173
```

Set `VITE_API_BASE_URL` if the backend uses another origin. Copy `.env.example`
to `.env.local` for a local override.

## Verify

```bash
npm run lint -- --quiet
npm run typecheck
npm run build
```

## Key files

- `src/lib/api.ts` — centralized fetch client and backend boundary types.
- `src/components/TriageDashboard.jsx` — queue, persisted assessment, and tab
  orchestration.
- `src/components/ClinicalIntakePanel.jsx` — patient/encounter/manual intake and
  workflow execution.
- `src/components/DocumentUploadCard.jsx` — OCR ingestion.
- `src/components/SpeechInputCard.jsx` — browser recording/audio ingestion.
- `src/components/AssessmentOverview.jsx` — separated decision-support results.

The UI polls `GET /api/queue` every five seconds and refreshes the persisted
`GET /api/encounters/{id}/assessment` projection after mutations. Provider
failure is rendered as unavailable while deterministic local results remain.

This remains a non-clinically-validated decision-support prototype. Clinician
review is required.

## Known limitations

- Full ESI is not implemented; the displayed subset is always provisional.
- Gemini reasoning and speech require configured network access. Their failure does
  not remove provisioned local cardiac, triage, SHAP, or priority output.
- OCR quality depends on installed Tesseract language data; original uploads are
  intentionally not retained.
- Queue recalculation is explicit on workflow runs rather than event-driven.
- There is currently no component/browser automation suite; the repository uses
  static checks, backend integration tests, a live contract verifier, and a
  headless-browser hydration smoke check.
