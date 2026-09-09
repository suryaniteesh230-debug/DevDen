# NextCare round-two judge deployment

This runbook deploys the existing UI and FastAPI backend as one same-origin Vercel
Services project for the second-round submission. Judges receive one HTTPS URL,
sign in with a synthetic staff account, and reach the existing dashboard. Physical
kiosk setup is optional final-round preparation and is kept in the last section.

## 1. Create the Vercel project and Neon database

1. Import this repository into Vercel, select the repository root (`.`) as the
   root directory, and select the **Services** framework preset. `vercel.json`
   defines the `frontend/` and `backend/` services.
2. In the Vercel Marketplace, connect a Neon Postgres database to the project.
3. Copy the provider connection URL into `NEUROBOTS_DATABASE_URL`. Prefer the
   pooled application URL when Neon supplies both pooled and direct URLs. The URL
   must require TLS, for example:

   ```text
   postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require
   ```

Do not commit the URL. Local SQLite remains the default only for development and
tests. Vercel production will fail fast if `NEUROBOTS_DATABASE_URL` still points
at SQLite, so set the hosted Postgres URL before the first deploy.

## 2. Configure Vercel variables

Add these variables to both Production and Preview. Use a separate Neon branch or
database URL for Preview when available. Generate a separate authentication secret
for each trust boundary with `openssl rand -hex 32`.

```text
VITE_API_BASE_URL=/
PORT=8000
NEUROBOTS_ENVIRONMENT=production
NEUROBOTS_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require
NEUROBOTS_AUTH_SECRET_KEY=<output from openssl rand -hex 32>
NEUROBOTS_AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=480
NEUROBOTS_CORS_ORIGINS=[]
VERCEL_SUPPORT_LARGE_FUNCTIONS=1
GEMINI_API_KEY=<optional>
GEMINI_MODEL=gemini-3.6-flash
GEMINI_MAX_RETRIES=2
GEMINI_MAX_OUTPUT_TOKENS=4096
GEMINI_THINKING_BUDGET=0
GEMINI_SPEECH_MODEL=gemini-3.6-flash
```

`vercel.env.example` is a safe name-only template. Never put production values in
that file or in `.env` files committed to Git. The production backend refuses to
issue login tokens when the authentication secret is missing.

Use the Vercel environment panel rather than a checked-in `.env` file for the
real deployment values. The backend container does not run migrations during
startup, so the database must already exist and be reachable.

## 3. Apply migrations and create staff

Do this explicitly from a trusted workstation before the release. It is
intentionally absent from the container startup command.

Run migrations before every release:

```bash
cd backend
uv sync --extra dev --locked
export NEUROBOTS_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require'
scripts/migrate_postgres.sh
```

For the first deployment, create a synthetic judge account separately:

```bash
.venv/bin/python -m app.create_staff \
  --email doctor@nextcare.demo \
  --full-name "Dr. Demo" \
  --role DOCTOR
```

The account command prompts twice without echo for an at-least-eight-character
password. It does not print or store plaintext. `scripts/provision_postgres.sh`
combines both steps for a brand-new database. Use only synthetic accounts and data
for the hackathon.

Populate the judge database only with the repository's synthetic cases:

```bash
.venv/bin/python -m app.seed
```

Securely give the judges the synthetic staff email and password; do not put the
password in source code, browser storage, screenshots, or this runbook.

## 4. Deploy and verify

Deploy only after migrations succeed. The locally verified backend image is about
1.44 GB because it includes the scientific Python and OCR stack. It therefore
uses Vercel Large Functions; new projects are enrolled automatically, while
`VERCEL_SUPPORT_LARGE_FUNCTIONS=1` opts in older eligible projects. The image
installs Tesseract English data and Poppler, contains the verified 444,973-byte
cardiac model, and rejects an artifact checksum mismatch during build. It does not
retrain the model.

If the backend starts with a SQLite URL in production, the application will stop
with a clear configuration error. That is intentional and means the deployment
still needs the hosted Postgres env var, not a code fix.

The backend function duration is set to 300 seconds in `vercel.json`. In Vercel's
Functions settings, confirm Fluid Compute is enabled and start the demo backend at
2 GB memory. Raise it to 4 GB if the first real workflow shows an out-of-memory
event; the dashboard setting and available maximum depend on the selected plan.

After deployment, verify:

```bash
curl -fsS https://YOUR_DOMAIN/health
curl -i https://YOUR_DOMAIN/api/auth/me
```

The health request should succeed without authentication. The current-user
request should return `401` without a bearer token. Open the deployed root, sign
in with the provisioned staff account, and verify that the existing dashboard and
queue load.

## 5. Optional final-round kiosk setup

Create a restricted operating-system account with no administrative access. Do
not save or hard-code a staff password in the browser. From the repository, launch
Chrome or Chromium with:

```bash
NEXTCARE_KIOSK_URL='https://YOUR_DOMAIN' scripts/launch-kiosk.sh
```

The script requires HTTPS and applies `--kiosk`, `--no-first-run`, and
`--disable-session-crashed-bubble`.

## Limitations

This is a hackathon deployment with no offline failover. Keep the hosted database
synthetic. This design does not establish HIPAA, GDPR, or other regulatory
compliance. A genuinely offline kiosk should package the frontend, backend,
SQLite, OCR tools, and model on the kiosk itself (for example through the existing
Electron direction) instead of using Vercel.
