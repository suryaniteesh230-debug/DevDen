# NextCare Deployment Notes

Last updated: 2026-08-08

The backend requires Python 3.12–3.13 and supports SQLite for local development
or PostgreSQL through psycopg for cloud deployment. Local OCR additionally expects
`tesseract` and `pdftoppm` on `PATH`; install English Tesseract trained data for
normal English clinical documents. The current verified workstation falls back
to the installed Afrikaans Latin-script pack and records that limitation per
result.

Uploads are processed in private temporary directories and removed immediately.
The database retains metadata, hashes, OCR text, extracted observations, and
provenance, but not original document bytes. Ensure the OS temporary directory
has enough space for rendering up to five bounded PDF pages.

Speech ingestion is the one multimodal feature that is not offline on this host.
It needs outbound Groq access and `GROQ_API_KEY`; `GROQ_SPEECH_MODEL` defaults to
`whisper-large-v3-turbo`. Do not enable it where sending clinical audio to the
configured provider is not approved. The rest of the deterministic assessment
path remains available when speech transcription is disabled or unavailable.

From a fresh clone, install the locked backend environment and apply migrations
before starting the API. The approved raw dataset remains Git-ignored. The single
verified 444,973-byte cardiac artifact is intentionally allow-listed for the
hackathon container and checksum-verified during the image build.
Then run the frontend against the explicit backend origin:

```bash
cd backend
uv sync --extra dev --locked
cp .env.example .env
# Set NEUROBOTS_AUTH_SECRET_KEY in .env to a generated 32+ character secret.
.venv/bin/alembic upgrade head
.venv/bin/python -m app.create_staff --email doctor@nextcare.demo --full-name "Dr. Demo" --role DOCTOR
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

cd ../frontend
ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci --ignore-scripts
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run build
npm run preview -- --host 127.0.0.1 --port 5173
```

The repository also provides a Vercel Services cloud-kiosk layout in
`vercel.json`: the Vite service serves the existing UI, `/api/*` is rewritten to
the FastAPI container, and the backend container installs Poppler and English
Tesseract data. The backend has a 300-second function duration in the manifest.
Memory is selected in the Vercel project settings because it is plan-dependent.
The locally built image is approximately 1.44 GB and requires Vercel's Large
Functions path; new projects are enrolled automatically, while older eligible
projects can set `VERCEL_SUPPORT_LARGE_FUNCTIONS=1`.
The container never applies database migrations during startup. The TanStack
Start frontend includes Nitro and produces Vercel Build Output when `VERCEL=1`.

`NEUROBOTS_AUTH_SECRET_KEY` is mandatory outside `development` and must be unique
per deployment; never commit it. Development can use a random process-local
fallback, which invalidates all tokens whenever the backend restarts and is not
suitable for multiple workers. Staff accounts are provisioned explicitly after
migrations. The command prompts twice without echoing the password and never
creates users during application startup.

For the same-origin Vercel deployment, set `VITE_API_BASE_URL=/` and
`NEUROBOTS_CORS_ORIGINS=[]`, and route the container's explicit `PORT=8000`.
Configure managed PostgreSQL in
`NEUROBOTS_DATABASE_URL`; `DATABASE_URL` is accepted as a provider-compatible
alias, and ordinary `postgresql://` URLs are normalized to the psycopg dialect.
Run migrations explicitly from a trusted workstation with
`backend/scripts/migrate_postgres.sh`; use `provision_postgres.sh` to combine the
initial migration and first synthetic staff account. See
`VERCEL_DEPLOYMENT.md` for the round-two release and optional final-round kiosk
procedure.

The cloud-kiosk design requires working internet connectivity. It does not add an
offline database, browser-stored credentials, regulatory certification,
fine-grained RBAC, refresh tokens, token revocation, or encryption-at-rest policy.
Uploaded document/audio bytes still cannot be recovered because they are
intentionally not retained.

For a judge/development database only, `.venv/bin/python -m app.seed` creates the
idempotent ten-patient synthetic dataset without calling Groq. Do not seed a
production or real-patient database.
