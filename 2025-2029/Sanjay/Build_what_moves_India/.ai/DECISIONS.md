# Decision ledger

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-08-28 | React, TypeScript, and Vite frontend | Small typed kiosk UI foundation. |
| 2026-08-28 | FastAPI and Pydantic backend | Typed, minimal versioned API. |
| 2026-08-28 | Same-origin production delivery | Limits browser cross-origin exposure. |
| 2026-08-28 | In-memory citizen workflow state | No persistent citizen data. |
| 2026-08-28 | No database for citizen data | Privacy-first MVP boundary. |
| 2026-08-28 | Deterministic eligibility and procedure facts | Facts must be verified and reproducible. |
| 2026-08-28 | Cloud AI optional and disabled by default | Explanation must not decide outcomes. |
| 2026-08-28 | Public hackathon deployment with synthetic-data guidance | Demonstrate safely without real citizen data. |
| 2026-08-28 | Push feature branches only after verification | Preserve a verified checkpoint. |
| 2026-08-28 | Protect main from direct feature work | Keep release integration explicit. |
| 2026-08-28 | JSON Procedure Pack v1 validated by strict Pydantic models | Deterministic contracts and tooling without another parser dependency. |
| 2026-08-28 | Every important procedure fact carries official-source provenance | Unsupported or dangling facts fail validation before reaching citizens. |
| 2026-08-28 | One active version per service; draft and superseded versions are never served | Version selection is explicit and fails closed. |
| 2026-08-28 | Canonical SHA-256 pack digest, with cryptographic signing deferred | Provide reproducible traceability now without introducing private-key operations in the MVP. |
| 2026-08-28 | Procedure trust becomes stale after its review deadline | Expired verification remains visible but is never silently presented as current. |
| 2026-08-28 | Represent conflicting official-source claims explicitly | Preserve each authoritative claim and its provenance instead of selecting a value without evidence. |
| 2026-08-28 | Never silently resolve conflicting authoritative claims | Direct citizens to confirm on the official service when Sahayi cannot establish one canonical fact. |
| 2026-08-28 | Keep review freshness and factual conflict as separate states | Current unaffected guidance can remain available while a specific unresolved fact receives attention. |
| 2026-08-28 | Use “readiness check” rather than eligibility terminology | Outcomes are personalised procedural guidance and never an official decision or approval. |
| 2026-08-28 | Encode readiness rules as a strict bounded JSON AST | Deterministic operators, load-time validation, and evaluation budgets avoid executable expressions and unbounded work. |
| 2026-08-28 | Keep readiness evaluation stateless | Each request carries a bounded answer map; no session, database, answer logging, or external call is required. |
| 2026-08-28 | Permit only non-sensitive structured readiness questions | Boolean, enumerated choice, and bounded integer answers preserve the no-PII boundary; free text and identifiers are excluded. |
| 2026-08-28 | Permit pack-labelled sensitive closed-choice readiness questions | Income, pension, and tax categories can provide useful preliminary guidance without exact values or identifiers; they require a privacy explanation and an optional withheld choice, remain memory/request only, and are never logged. |
| 2026-08-28 | Keep subjective and intrusive Kerala pension criteria outside automated screening | Respectful source-cited local-body review items preserve the official conditions without asking about or inferring personal circumstances. |
| 2026-08-28 | Omit Kerala pension amount pending a resolving official order | The reviewed Sevana criteria page presents inconsistent current-table, history, and special-amount material; no amount is needed for safe procedure guidance. |
| 2026-08-28 | Keep natural-language service matching entirely in the browser | Raw citizen text never leaves component memory: no API, URL, logging, telemetry, cookie, or browser persistence is used. |
| 2026-08-28 | Use deterministic locale-specific scoring over pack-authored intent phrases | NFKC Unicode normalisation, containment, weighted token overlap, threshold, and candidate margin are reproducible and support English, Hindi, Malayalam, and useful transliterations without model calls or service-specific code. |
| 2026-08-28 | Require confirmation after every suggested service | A match is guidance for navigation, not an automatic selection or service decision. |
| 2026-08-28 | Locally warn on obvious identifier patterns before matching | Aadhaar-like, phone-like, and email patterns are blocked without retaining their value; this limited detector is not a guarantee of complete PII removal. |
| 2026-08-28 | Support exactly English, Hindi, and Malayalam with English canonical | Keeps the locale contract bounded and backward-compatible while stable facts, IDs, rules, URLs, and provenance remain language-neutral. |
| 2026-08-28 | Treat Hindi and Malayalam as machine-assisted prototype translations requiring native/legal review | Complete official translated equivalents were unavailable for every field; only validated canonical English content is translated and linked official wording prevails. |
| 2026-08-28 | Keep translations static in validated packs and a typed UI catalogue | No runtime translation API, third-party policy translation, external font, storage, or network translation dependency enters the privacy/trust boundary. |
| 2026-08-28 | Normalize relevant Unicode decimal digits before local identifier blocking | ASCII, Devanagari, and Malayalam identifier-shaped input receives the same browser-only protection without transmitting the value. |
| 2026-08-28 | Use a small explicit provider tool loop with a fixed model | Tool ordering can be agentic while strict local functions, validated output, no retry, and hard budgets retain control. |
| 2026-08-28 | Keep AI optional, consent-gated, and disabled by default | Deterministic guidance must work without a key and cloud processing must be separately disclosed. |
| 2026-08-28 | Reconstruct every factual card and action server-side | Model prose guides; validated pack IDs and local tool results remain the sole source for facts, sources, fees, outcomes, URLs, and actions. |
| 2026-08-28 | Use process-local abuse controls only as prototype safeguards | An ephemeral salted client hash, stale cleanup, semaphore, rate window, and request budget limit cost without claiming distributed production protection. |
| 2026-08-28 | Permit synthetic form preparation only | Bundled DEMO personas and blank private fields demonstrate preparation without citizen free text, official form filling, files, submission, or retention. |
| 2026-08-29 | Keep source monitoring a one-shot offline-first administrative CLI | Hosted code must not continuously scrape; exact allowlists, bounded retrieval and human review support safe change detection without autonomous fact mutation. |
| 2026-08-29 | Leave reviewed monitoring baselines empty when no authorized live retrieval occurred | Do not fabricate fingerprints; report `review_required` until an authorized human establishes each baseline. |
| 2026-08-29 | Model demo submission/status as a strict stateless synthetic contract | Demonstrate a journey without government contact, arbitrary input, real references, implied acceptance, submission, approval or tracking. |
| 2026-08-29 | Use one shared session-clear operation for explicit end and inactivity | Abort requests and clear every in-memory citizen state consistently, while making no claim beyond Sahayi's retention boundary. |
| 2026-08-29 | Add a dependency-free character n-gram Multinomial Naive Bayes intent classifier | A 167 KiB deterministic trained artifact improves native-script, transliteration and spelling coverage without a browser LLM, runtime dependency, model download, generation, or network call. |
| 2026-08-29 | Ensemble local ML with the existing pack-phrase matcher behind PII and confirmation gates | Agreement and one-sided confidence may propose only allowlisted catalogue services; disagreement, unsupported, abstention and artifact failure fail safely without changing procedure facts or readiness decisions. |
| 2026-08-29 | Train only on owned synthetic examples and reserve validation/test roles | Fixed balanced splits, canonical generation, digests, native-review markers, validation-only threshold tuning and candid synthetic metrics make limitations and retraining drift reviewable. |
| 2026-08-29 | Prepare the submission as a dedicated release branch from the complete linear feature chain | Keeps candidate review and verification isolated while `main`, the deployment branch, and the public service remain unchanged until separate authorization. |
| 2026-08-29 | Initially select GroqCloud with exact `llama-3.3-70b-versatile` and no automatic substitute (superseded below after its documented retirement) | Historical migration context: one allowlisted provider/model keeps runtime behavior reviewable. |
| 2026-08-29 | Use Groq's OpenAI-compatible Responses endpoint through a small provider adapter (superseded below after the production HTTP 400) | Retained the pinned client while fixing provider, base URL, key, model, and availability in application-controlled configuration. |
| 2026-08-29 | Validate final JSON locally instead of requesting provider Structured Outputs | Groq documents tool use and Structured Outputs as incompatible; exact Pydantic validation fails closed without weakening the seven-tool boundary. |
| 2026-08-29 | Treat Groq Zero Data Retention as an owner-controlled external setting | Code cannot enable or guarantee the Groq Console setting, and Groq still documents usage-metadata collection. |
| 2026-08-29 | Replace the retired runtime model with sole allowlisted `openai/gpt-oss-120b` | Groq lists it as an official replacement and on the free plan; the non-preview model page documents local tool use, JSON/JSON Schema modes, and multilingual capability. Provider failure still returns deterministic Sahayi guidance, never another model. |
| 2026-09-01 | Replace only the Groq transport with Chat Completions local-tool calls | Groq rejected the initial Responses request before tool execution; documented nested functions plus local schema, argument, result, and final-output validation preserve the application-controlled boundary. |

## Official HTTPX documentation basis

Retrieved 2026-08-29 from the official HTTPX site:

- [Timeouts](https://www.python-httpx.org/advanced/timeouts/)
- [QuickStart: streaming responses](https://www.python-httpx.org/quickstart/)
- [Clients and redirect configuration](https://www.python-httpx.org/advanced/clients/)
- [Transports, retries, and MockTransport](https://www.python-httpx.org/advanced/transports/)

These references support explicit timeout configuration, streamed bounded reads, disabled automatic redirects/manual validation, an explicit zero-retry transport, and offline transport mocks.

## Official Groq documentation basis

Retrieved 2026-08-29 for the model correction, using only the official Groq Console documentation requested for this decision:

- [Model deprecations](https://console.groq.com/docs/deprecations)
- [`openai/gpt-oss-120b` model](https://console.groq.com/docs/model/openai/gpt-oss-120b)
- [Rate limits](https://console.groq.com/docs/rate-limits)
- [Responses API](https://console.groq.com/docs/responses-api)
- [Chat Completions](https://console.groq.com/docs/text-chat)
- [Tool use overview](https://console.groq.com/docs/tool-use/overview)

The deprecations page records the free/developer-tier retirement of `llama-3.3-70b-versatile` on 2026-08-16 and names `openai/gpt-oss-120b` as an official replacement. That retired identifier is retained here only as historical migration documentation, never as active configuration. The selected model page presents the model without a preview label and documents Tool Use, JSON Object Mode, JSON Schema Mode, and multilingual use across 81+ languages. Its `openai/` prefix is Groq's model namespace. Sahayi now calls the Chat Completions interface with `GROQ_API_KEY`; the older Responses link remains only as historical context for the superseded transport. The tool overview distinguishes local calls from built-in and MCP/remote tools; Sahayi keeps only its exact seven local functions and server-side Pydantic validation. The rate-limit page currently lists the model on the free plan at 30 RPM, 1,000 RPD, 8,000 TPM, and 200,000 TPD. Those limits are indicative; the exact organization limits must be checked in Groq Console. No live or billable provider request was made during the original decision review.
