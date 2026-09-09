# NextCare Implemented Backend API Contract

Last updated: 2026-08-08

Base URL for local development: `http://127.0.0.1:8000`. JSON endpoints use
snake_case. Errors use:

```json
{"error":{"code":"STABLE_CODE","detail":"Human-readable detail","issues":[]}}
```

`issues` is present only for request-validation errors. The frontend must not
fail the whole assessment when `clinical_reasoning` is unavailable.

Every `/api` endpoint below requires `Authorization: Bearer <access_token>`
unless explicitly identified as public. Missing, invalid, expired, or disabled-
account credentials return 401. The health endpoint and staff login are public.

## Medical-staff authentication

- `POST /api/auth/login` — public; accepts `{"email":"...","password":"..."}`
  and returns a short-lived bearer token plus the safe staff projection. Invalid,
  nonexistent, and disabled accounts all return generic `Invalid credentials`.
- `GET /api/auth/me` — protected; returns `id`, `email`, `full_name`, `role`,
  `is_active`, and `created_at` for the current staff member.

There is no signup endpoint. The token response and current-user response never
contain `password_hash`.

## System

- `GET /health` — service status and environment.

## Patients and encounters

- `POST /api/patients` — register a patient.
- `GET /api/patients?name=&external_patient_id=&limit=` — search patients.
- `GET /api/patients/{patient_id}` — retrieve a patient.
- `GET /api/patients/{patient_id}/history` — patient plus detailed encounters.
- `POST /api/patients/{patient_id}/encounters` — create an encounter.
- `GET /api/encounters/{encounter_id}` — encounter with observations.
- `PATCH /api/encounters/{encounter_id}` — update encounter/status.
- `POST|GET /api/encounters/{encounter_id}/symptoms` — append/list symptoms.
- `POST|GET /api/encounters/{encounter_id}/vitals` — append/list repeated vitals.
- `POST|GET /api/encounters/{encounter_id}/labs` — append/list generic labs.

Observation source values are `MANUAL`, `SIMULATOR`, `OCR`, `SPEECH`, `EHR`,
and `WEARABLE`; the final UI should submit manual form entries as `MANUAL`.

## Workflow and persisted assessment

`POST /api/encounters/{encounter_id}/workflow` runs the Supervisor-directed
workflow. It returns the complete ClinicalState for diagnostics and immediate
workflow feedback. The frontend should subsequently read the cleaner persisted
projection from `GET /api/encounters/{encounter_id}/assessment`.

The latest-assessment response contains patient, detailed encounter, latest
cardiac risk, latest provisional triage, latest SHAP explanation, latest clinical
reasoning attempt, current operational priority, and persisted OCR/speech inputs.
Any assessment channel can be null when it has never produced a result.

`GET /api/encounters/{encounter_id}/assessment-history` adds all append-only risk
predictions, triage assessments, explanations, reasoning results, and priority
calculations. It is intended for review, not for queue polling.

Cardiac risk, emergency triage, clinical reasoning, and operational priority are
independent UI concepts. `priority_band` is not ESI. `prototype_esi_level` can
only represent the provisional implemented subset. Clinical reasoning with
`PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT`, `INVALID_OUTPUT`, or
`PROVIDER_FAILURE` must render as unavailable while local cardiac, triage, SHAP,
and priority results remain visible.

## Queue

`GET /api/queue` returns `WAITING` entries ordered by score descending, earlier
waiting time, entry creation, then UUID. `?status=CALLED|IN_ASSESSMENT|COMPLETED|REMOVED`
filters another status. Rows include IDs, rank, score/band, minimal
`patient_display` (name, age, chief complaint), waiting duration, separate triage
and cardiac context, deterioration, provisional flag, reason codes, policy
metadata, and last reassessment.

`GET /api/queue/{queue_entry_id}` adds rule trace and calculation count.
`PATCH /api/queue/{queue_entry_id}` accepts only
`{"queue_status":"WAITING|CALLED|IN_ASSESSMENT|COMPLETED|REMOVED"}`. Terminal
`COMPLETED`/`REMOVED` entries cannot be reopened; invalid transitions return 409
`INVALID_QUEUE_TRANSITION`. Recalculation occurs only by rerunning the workflow.

## Clinical document OCR

`POST /api/encounters/{encounter_id}/documents` accepts raw PNG, JPEG, TIFF,
WebP, or PDF bytes. Send `Content-Type` and `X-Filename`. The 201 response includes
document ID, sanitized filename, SHA-256/size, source `OCR`, OCR text,
engine/version/language, confidence, allow-listed extracted labs, explicit
manual/OCR conflicts, created lab IDs, page count, and timestamps. Uploads are
limited to 10 MiB and PDFs to five pages. Bytes are not retained.

`GET /api/encounters/{encounter_id}/documents` lists results;
`GET /api/documents/{document_id}` returns one.

## Speech-to-clinical-text

`POST /api/encounters/{encounter_id}/speech` accepts raw WAV, MP3, MP4/M4A, OGG,
WebM, or FLAC bytes with `Content-Type` and `X-Filename`. The 201 response includes
transcription ID, hash/size, source `SPEECH`, transcript, provider/model/language,
confidence availability, deterministic extracted symptoms, conflicts, symptom
IDs, latency, and timestamps. Explicit negations are stored with `present=false`.
Audio is limited to 20 MiB and is not retained.

`GET /api/encounters/{encounter_id}/speech` lists results;
`GET /api/speech/{transcription_id}` returns one. Missing Groq configuration
returns 503 `SPEECH_PROVIDER_UNAVAILABLE` and does not affect other endpoints.

## OpenAPI and CORS

`GET /openapi.json` is the machine-readable contract. Local CORS permits ports
3000 and 5173 on `localhost` and `127.0.0.1`; production must configure an
explicit deployed origin. In a same-origin Vercel build, use
`VITE_API_BASE_URL=/`; the client normalizes this to relative `/api/...` requests
and the root manifest rewrites them to the backend service. The simulator and compatibility workflow aliases stay
implemented for existing tests/demos but are intentionally hidden from OpenAPI.

The frontend consumes this contract through one maintained TypeScript client
(`frontend/src/lib/api.ts`). No OpenAPI type-generation script is configured, so
OpenAPI plus backend contract tests remain the source of truth during changes.

All results are clinical decision-support prototype outputs, not autonomous
diagnoses. The cardiac model, triage subset, queue policy, OCR parser, speech
extractor, and clinical reasoning are not clinically validated.
