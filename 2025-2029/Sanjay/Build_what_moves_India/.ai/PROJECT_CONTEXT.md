# Sahayi project context

Sahayi addresses the citizen problem of not knowing which department, scheme, channel, or sequence applies to a need. The final hackathon release candidate is a publicly demonstrable, privacy-first multilingual preparation conversation: it starts from the person's need, proposes one of two supported services locally, requires confirmation, asks only the next deterministic readiness or preparation question, fills a browser-memory preparation record, updates the checklist automatically, and hands off to a verified official channel.

The implemented release supports UIDAI Aadhaar address update and Kerala Indira Gandhi National Old Age Pension in English, Hindi, and Malayalam. English is canonical. Hindi/Malayalam UI, Procedure Pack text, and synthetic intent examples are machine-assisted prototypes pending native-speaker and legal review.

Architecture boundaries:

- Browser-local inference combines deterministic pack phrases with a bundled character 2–5-gram Multinomial Naive Bayes classifier; raw finder text is not sent online.
- One typed bounded LangGraph composes intent confirmation, verified procedure routing, deterministic readiness, structural completed-field/document evidence, parallel checklist/preparation-definition generation, and official handoff through a strict stateless conversation-turn API. Personal preparation values stay only in React memory; it has no checkpointer, store, database, tracing, or server thread.
- FastAPI serves the React build and stateless deterministic Procedure Pack, readiness, checklist, synthetic worksheet, conversation-turn, and demo status APIs from one same-origin container.
- Optional GroqCloud guidance is separately disclosed, consent-gated, unavailable without server configuration, and limited to strict local tools; AI never supplies authoritative facts or outcomes.
- Procedure Intelligence is an offline-first, one-shot, human-reviewed source comparison CLI, optionally invoked by a read-only daily GitHub Actions workflow; it is not hosted citizen functionality or automatic fact activation.
- Browser-dependent voice input/read-aloud is explicit, memory-only, and always paired with complete text/touch fallback; recognition may use browser/vendor processing.
- Optional Tesseract.js/PDF.js printed-text assistance is explicit, lazy, checksum-verified, same-origin, and browser-local. Raw files/OCR never cross the API; a citizen may confirm only an allowlisted unverified clue.
- Citizen workflow state is memory-only and cleared by End Session/inactivity. No citizen database, cookies, browser storage, analytics, or telemetry exists.

The public demo is https://sahayi.onrender.com. Release candidates move linearly through `feat/sahayi-langgraph-orchestration`, `test/sahayi-final`, and `feat/sahayi-deployment`; `main` advances only after the exact hosted commit passes.

Non-goals and limitations: government affiliation/endorsement, legal eligibility decisions, real forms/submission/status, OTP/payment, DigiLocker, certified voice/pronunciation or complete accessibility, production readiness, certified translation, automatic fact activation, verified real-world model accuracy, universal external-provider non-retention, or a Zero Data Retention claim. The UIDAI fee conflict remains unresolved and source-linked; the Kerala pension amount is omitted. Procedure facts must remain deterministic and verified before display.
