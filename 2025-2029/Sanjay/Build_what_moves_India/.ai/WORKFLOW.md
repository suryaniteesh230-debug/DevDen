# Workflow

1. Read `AGENTS.md`.
2. Read `.ai/PROJECT_CONTEXT.md` and `.ai/TASK_STATE.md`.
3. Read only the additional relevant `.ai` file.
4. Inspect relevant source with targeted search.
5. Implement one bounded phase.
6. Run focused tests, then the smallest complete release gates; parallelize independent checks and do not repeat a successful expensive gate unless a later change can affect it.
7. Update TASK_STATE and affected context docs.
8. Inspect the diff and scan for secrets.
9. Commit and push the feature branch only when gates pass.
10. Promote a completed milestone only with explicit final release instruction.

## Release promotion

- Development occurs on feature branches; do not make development commits directly on `main`.
- A submission candidate is created from an exact clean, fetched, synchronized feature-chain commit only after branch, ancestry, upstream, and protected-branch checks pass.
- Run backend/frontend tests, lint/typecheck/build, offline agent evaluation, model regeneration/integrity, Procedure Pack/schema validation, dependency audits, secret/PII/privacy scans, documentation checks, one no-cache container build, runtime API/cache checks, and established browser smoke coverage before the candidate commit.
- Only the named release branch may be pushed during candidate preparation. Re-fetch afterward and require local/remote hash equality, divergence `0/0`, and a clean worktree.
- Deployment and promotion are separate explicit operations. Do not advance `main`, `feat/sahayi-deployment`, or Render merely because the release branch passes local gates.
- Never force-push, rewrite history, or push an unverified commit to a protected/deployment branch.

Do not restate all project context in prompts. Prefer targeted diffs and concise reports. Add dependencies only for demonstrated need. Stop on unexpected worktree or remote state; never force-push or discard unrelated changes.
