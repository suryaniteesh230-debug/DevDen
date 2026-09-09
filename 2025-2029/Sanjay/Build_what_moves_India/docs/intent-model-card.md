# Sahayi local intent model card

## Purpose and boundary

Sahayi Intent MNB 1.0.0 is a compact, non-generative classifier used only to propose one of two supported procedure services or to return unsupported/abstain. It never decides eligibility, facts, fees, readiness, or official outcomes. Procedure Packs and deterministic readiness rules remain authoritative, and every proposed service requires the citizen to confirm before it opens.

The model is a character 2–5-gram Multinomial Naive Bayes classifier with Laplace smoothing. Training uses Python's standard library. Browser inference is synchronous TypeScript with no ML runtime or production dependency. A 500-code-point input bound, 3,308-entry sorted vocabulary, and per-feature count cap of four bound work. Validation-selected thresholds are 0.85 minimum posterior confidence and 0.40 minimum top-two margin.

This classifier was chosen over a browser LLM because it is deterministic, interpretable, 167,430 bytes uncompressed, dependency-free, immediately available offline, and incapable of generating procedure claims. It requires no WebGPU, WASM, model/runtime download, or network request.

## Labels and languages

The fixed labels are:

- `aadhaar_address_update` → allowlisted service `uidai-aadhaar-address-update`
- `kerala_old_age_pension` → allowlisted service `kerala-ign-oap`
- `unsupported_other` → no service

The owned dataset covers English, Hindi, and Malayalam, including native scripts, common transliterations, misspellings, mixed scripts, short and conversational wording, unsupported services, ambiguity, prompt-like instructions, emoji/control characters, repeated characters, and bounded long input. Support is intentionally limited to these labels and locales.

## Dataset provenance and review

`intent_dataset.v1.jsonl` contains 81 wholly synthetic Sahayi-authored examples: 27 per locale and 27 per label. Its fixed split is 45 train, 18 validation, and 18 final test examples, balanced by locale and label within each split. Rows carry stable IDs, locale, text, label, split, `synthetic: true`, and a bounded provenance marker. No scraped query, citizen data, identifier-shaped value, or translation API output is included. Validation rejects malformed UTF-8/Unicode surrogates, invalid labels, missing provenance, duplicate normalized text, cross-split normalized leakage, imbalance, excessive text, and unbounded vocabulary.

Hindi and Malayalam text is marked `sahayi_machine_assisted_native_review_required`. It is prototype data and requires native-speaker review before production use. Split review avoids copied translations and punctuation-only variants across splits, but semantic leakage detection ultimately needs human review.

Dataset SHA-256: `14e56d1561584e6bfec420957d393740a9f3f6de53cbf6b965ad4a0084c58e62`.

## Reproducibility and integrity

The trainer applies NFKC, Unicode lowercase, keeps only Unicode letters/numbers/whitespace, collapses whitespace, extracts bounded character n-grams, trains only on `train`, and tunes thresholds only on `validation`. The final `test` split is evaluation-only. Sorted canonical JSON omits wall-clock data and is byte-identical for identical input. The artifact records its schema/model/normalization versions, dataset digest, allowlisted labels/services, vocabulary, priors, weights, thresholds, training counts, bounds, and timestamp-omission policy.

Model SHA-256: `fd8966853576dc1233a82908f93ce80a56d87537d0f0a82ef94d25a97adf54b4`.

Regenerate with `python -m tools.intent_model --write`, verify drift with `python -m tools.intent_model --check`, and print the held-out report with `python -m tools.intent_model --evaluate`. Adding a service requires a reviewed label/service mapping, balanced synthetic examples in all locales and splits, native review, retraining, held-out evaluation, digest updates, frontend contract tests, and the normal full release gates.

## Held-out synthetic evaluation

The fixed 18-example test report records:

| Metric | Value |
| --- | ---: |
| Accuracy | 0.833333 |
| Macro precision / recall / F1 | 0.952381 / 0.833333 / 0.863248 |
| Abstention rate | 0.111111 |
| Accepted-prediction accuracy | 0.937500 |
| Deterministic/ML agreement when comparable | 1.000000 |
| Unsupported false-positive rate | 0.166667 |

Confusion matrix rows are actual labels and columns are Aadhaar / pension / unsupported / abstain:

- Aadhaar address update: `6 / 0 / 0 / 0`
- Kerala old-age pension: `0 / 6 / 0 / 0`
- unsupported/other: `1 / 0 / 3 / 2`

Per-language accuracy is English 0.666667, Hindi 0.833333, and Malayalam 1.000000 on only six synthetic examples each. These numbers do not establish real-world accuracy. In particular, the deliberately ambiguous English case exposes a supported-service false positive. Confirmation, deterministic disagreement handling, unsupported behavior, and catalogue fallback are safety controls, not substitutes for broader representative data and external/native review.

## Ensemble, privacy, and failure behavior

The browser blocks obvious identifier patterns before either matcher runs. It then runs the existing pack-phrase matcher and this classifier. Agreement proposes the common service; ML-only or deterministic-only confidence proposes with confirmation; disagreement shows ambiguity; unsupported never claims a supported service; both abstaining retains the no-match flow. Only allowlisted active-catalogue service IDs can be proposed. Invalid/missing model schema, digest contract, weights, thresholds, finite-number checks, normalization vectors, or allowlist silently disables ML and preserves deterministic matching.

Raw input and inference results remain only in React memory. Inference performs no fetch, logging, telemetry, cookie, local/session storage, IndexedDB, Cache API, service-worker, runtime model download, or external call. Start Over, End session, inactivity expiry, successful confirmation, and language changes clear query/inference state. The optional consent-gated GroqCloud flow is a separate screen and boundary; “matched on this device” is shown only for the local finder action.
