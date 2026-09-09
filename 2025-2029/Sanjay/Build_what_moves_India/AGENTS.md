# Sahayi contributor notes

- Always read `.ai/PROJECT_CONTEXT.md` and `.ai/TASK_STATE.md`, then only task-relevant `.ai` documents. Follow `.ai/WORKFLOW.md` for Git and verification; update TASK_STATE after a completed phase.
- Release architecture: browser-local deterministic phrase + Naive Bayes intent matching; same-origin React/FastAPI; deterministic Procedure Packs/readiness/checklists; consent-gated optional GroqCloud; offline one-shot source monitoring; synthetic form/submission/status only.
- Backend: `.venv/bin/python -m pytest`; frontend: `cd frontend && npm run lint && npm run typecheck && npm test && npm run build`.
- Model/pack integrity: `.venv/bin/python -m tools.intent_model --check`, `.venv/bin/python -m sahayi_api.procedure_tool validate`, and `.venv/bin/python -m sahayi_api.procedure_tool check-schema`.
- Never persist PII. Do not add citizen inputs, sessions, cookies, browser storage, or telemetry without explicit approval.
- Never place secrets in frontend code or Git; use placeholders in `.env.example` only.
- Procedure facts must be deterministic and verified before they are shown to users.
- Do not describe translations as certified, model metrics as real-world accuracy, source monitoring as continuous, Groq configuration as Zero Data Retention, or demo journeys as real submission/status.
- Do not commit, push, merge, pull, or rebase without explicit user instruction.
- Preserve unrelated working-tree changes.
