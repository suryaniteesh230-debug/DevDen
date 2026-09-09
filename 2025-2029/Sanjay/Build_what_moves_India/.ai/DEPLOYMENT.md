# Deployment

Sahayi is configured for one Render Docker Web Service at https://sahayi.onrender.com. The unified-conversation commit must not be deployed until its complete local gates pass and both tracked release branches point to that exact commit. The hosted experience is a hackathon prototype, not an official government service. It does not submit applications, receive OTPs or payments, authenticate citizens, or integrate with a government system.

## Architecture and runtime

`render.yaml` selects the exact `feat/sahayi-deployment` branch, the Docker runtime, the free plan, and `/api/v1/health` as the HTTP health check. Automatic service deploys are off. The repository's only scheduled automation is read-only Procedure Intelligence; it never builds, promotes, deploys, or changes Render. The owner must manually deploy only a commit that has passed the complete local release gates. Blueprint syncing is a separate Render setting and remains manual.

The multi-stage `Dockerfile` uses the project's verified Python 3.14.7 and Node 25.2.1 versions. The Node stage runs `npm ci` and the existing Vite build. The Python stage installs only the project's runtime dependencies. The final image contains the installed backend under `/app/src`, the compiled frontend under `/app/frontend/dist`, and active Procedure Packs under `/app/procedure-packs/packs`; this preserves the application's `__file__`-relative paths without depending on the process working directory. It runs as an unprivileged user and starts one Uvicorn process on `0.0.0.0`, using Render's `PORT` or local fallback `10000`.

The `.dockerignore` is an allowlist for only the Dockerfile, manifests, backend package and packaged monitoring fixture, frontend build inputs and OCR asset-copy tool, on-device model artifact, and Procedure Packs. The build verifies/copies pinned Tesseract worker/core and English/Hindi/Malayalam data into the compiled same-origin frontend; generated `frontend/public/ocr` and `dist` remain untracked. It excludes Git data, environment files, local virtual environments, dependency directories, caches, tests, documentation, datasets/evaluation reports, and local build outputs from the build context. No database, disk, server worker, cron job, hosted source monitor, or analytics is configured. The separate daily Actions job runs the bounded one-shot allowlisted comparison, uploads a review artifact, and never changes facts or deployment state. The Blueprint declares an unsynchronized `GROQ_API_KEY` secret prompt, the fixed Groq provider/model, and `SAHAYI_AGENT_ENABLED=false`, so deterministic deployment remains complete and AI remains unavailable until deliberately configured.

## Official Render documentation

Retrieved 2026-08-28:

- [Deploy a FastAPI App](https://render.com/docs/deploy-fastapi)
- [Web Services](https://render.com/docs/web-services)
- [Render Blueprints](https://render.com/docs/infrastructure-as-code)
- [Blueprint YAML Reference](https://render.com/docs/blueprint-spec)
- [Health Checks](https://render.com/docs/health-checks)
- [Deploying on Render](https://render.com/docs/deploys)
- [Deploy for Free](https://render.com/docs/free)
- [Rollbacks](https://render.com/docs/rollbacks)

## Candidate promotion and dashboard operation

1. Confirm the candidate branch commit, clean worktree, remote equality, `0/0` divergence, full local gates, secret/PII audit, and container/browser results.
2. In a separate explicitly authorized task, review how the verified candidate will advance `feat/sahayi-deployment`; do not silently change `render.yaml`, merge, or force-push. Keep `main` promotion separately authorized.
3. In Render, confirm the existing `sahayi` service still has no database, disk, worker, or cron job, Blueprint Auto Sync is **No**, and service Auto-Deploy is **Off**.
4. Leave `GROQ_API_KEY` unset and `SAHAYI_AGENT_ENABLED=false` for deterministic-only deployment unless optional cloud processing has received separate security, retention, budget, model-access, and product approval.
5. Use a manual deploy only after the service is pointed at the explicitly approved verified commit. Watch the build/startup log and `/api/v1/health`; then run every hosted check below before saying the public URL is updated.
6. The free service may spin down and need a cold start. Treat availability/plan changes as an operator decision, not a code claim.

To enable the optional agent later, the owner must create a restricted Groq project and key and place the key only in Render's secret manager. The selected `openai/gpt-oss-120b` name uses Groq's model namespace; it still authenticates only with `GROQ_API_KEY` against `https://api.groq.com/openai/v1`. In Groq Console, the organization owner must explicitly review Data Controls and decide whether to enable Zero Data Retention; Sahayi cannot do this in code, and usage metadata is still documented as collected. Set project spend/rate limits, keep provider/model on their sole allowlisted values, set `SAHAYI_AGENT_ENABLED=true`, and manually deploy a verified commit. Never put the key in Blueprint YAML, public config, frontend variables, logs, chat, or Git. The process-local limiter and budget reduce demo cost but are not distributed production abuse protection. A native-language review and a separately authorized live evaluation plan are still required before representing AI mode as production-ready.

Groq currently publishes indicative free-plan limits for `openai/gpt-oss-120b` of 30 RPM, 1,000 RPD, 8,000 TPM, and 200,000 TPD. Limits are external and may be too low for a public demo or change; operators must use Groq Console for the exact limits applied to their organization. HTTP 429 and all provider failures intentionally fall back to deterministic Sahayi guidance, never to a second automatic model.

## Post-deployment checks

Using https://sahayi.onrender.com, verify `/`, hashed initial/lazy OCR `/assets/`, self-hosted `/ocr/` assets, `/api/v1/health`, public config, catalogue, both procedure details, readiness, checklist, structural/populated preparation, synthetic form, conversation turns, demo submission/status, End session, and disabled-agent fallback. Confirm important API responses retain `Cache-Control: no-store`, the primary route has no service-card/module wall or second composer during a structured question, raw local intent causes no request, personal preparation values never enter a request, completed fields are skipped, local edits update the sheet, the exact watermark prints, the Aadhaar fee remains unresolved, Kerala displays no canonical pension amount or approval, private/unsupported fields remain blank, and clearing/trust/source limitations remain accurate. Repeat 360/390/768/1280 English/Hindi/Malayalam graphical checks and use only a synthetic local file for the OCR/manual-fallback smoke; confirm no bytes, OCR transcript, or suggested value enters a backend request. If AI is enabled, make only the minimum consented synthetic call and verify deterministic reconstruction/fallback without unsupported claims.

## Rollback

In the service's **Events** page, find the most recent known-good successful deploy, choose **Rollback**, review the target, and confirm **Rollback to this deploy**. Dashboard rollback disables service auto-deploys; keep them off, repeat the post-deployment checks, and only deploy a newer verified branch commit after resolving the issue. Free services retain rollback access only to the two most recent previous deploys.
