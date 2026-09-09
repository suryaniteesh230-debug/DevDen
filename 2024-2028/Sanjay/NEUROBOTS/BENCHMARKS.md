# NextCare Benchmark Report

Last verified: 2026-08-08

All values below are measured repository outputs, not estimates. Component
benchmarks are warm local runs on the verification workstation.

## Local fast path

| Measurement | Runs | Mean (ms) | p50 (ms) | p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| `CardiacRiskTool` | 500 | 14.6396 | 14.5156 | 15.3315 |
| `EmergencyTriageTool` | 1,000 | 0.0106 | 0.0093 | 0.0157 |
| `DynamicQueueService` with SQLite projection/history/audit | 300 | 2.3651 | 2.3298 | 2.7503 |
| Cardiac + triage + dynamic queue | 300 | 17.2662 | 17.1613 | 17.9381 |

The sub-500 ms claim refers only to the warmed combined local
`CardiacRiskTool` + `EmergencyTriageTool` + `DynamicQueueService` measurement.
It excludes HTTP, LangGraph orchestration, SHAP, and Groq network latency. It is
not an end-to-end request-latency claim.

For reference, the separately measured cardiac + triage tool-only path (without
queue persistence) ran 500 times at mean 14.6359 ms, p50 14.4580 ms, and p95
15.5155 ms. The Triage/Risk Agent with SQLite risk persistence ran 50 times at
mean 15.4780 ms, p50 15.3523 ms, and p95 16.3324 ms.

Sources:

- `backend/ml/latency_benchmark.json`
- `backend/triage/latency_benchmark.json`
- `backend/priority/latency_benchmark.json`

## Local retrieval

| Measurement | Runs | Mean (ms) | p50 (ms) | p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| RAG retrieval | 1,000 | 0.3937 | 0.3749 | 0.5231 |
| Medical knowledge graph query | 1,000 | 0.1418 | 0.1339 | 0.1881 |

These are warm local component timings. RAG uses the 12-chunk
`acs-corpus-1.0.0` and 4,096-dimensional hashing index; KG uses the 17-node,
17-edge `acs-kg-1.0.0`. Source:
`backend/clinical_knowledge/latency_benchmark.json`.

## Clinical reasoning harness

The 200-run complete `ClinicalReasoningAgent` benchmark with a zero-latency
scripted provider measured mean 5.7264 ms, p50 5.3945 ms, and p95 6.1045 ms.
That measurement includes local RAG, KG, schema validation, and SQLite
persistence, but excludes Groq network latency.

No tracked reproducible Groq network benchmark exists. Historical live spot
checks are intentionally excluded from this benchmark report because provider
latency varies with network, model, tool turns, and service state. Provider
failures do not invalidate local measurements or local assessment channels, and
no cloud latency is combined with the sub-500 ms claim.
