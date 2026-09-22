"""Train, validate, and evaluate Sahayi's dependency-free local intent model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "intent-model/data/intent_dataset.v1.jsonl"
ARTIFACT_PATH = ROOT / "intent-model/artifacts/intent-model.v1.json"
DIGEST_PATH = ROOT / "intent-model/artifacts/intent-model.v1.sha256"
REPORT_PATH = ROOT / "intent-model/artifacts/evaluation.v1.json"

LABELS = ("aadhaar_address_update", "kerala_old_age_pension", "unsupported_other")
LOCALES = ("en", "hi", "ml")
SPLITS = ("train", "validation", "test")
PROVENANCE = ("sahayi_authored_synthetic", "sahayi_machine_assisted_native_review_required")
NORMALIZATION_VERSION = "nfkc-lower-ln-space-v1"
MODEL_TYPE = "character_ngram_multinomial_naive_bayes"
MODEL_VERSION = "1.0.0"
SCHEMA_VERSION = 1
MIN_NGRAM = 2
MAX_NGRAM = 5
MAX_QUERY_LENGTH = 500
MAX_VOCABULARY = 6000
MAX_FEATURE_COUNT = 4
ALPHA = 1.0
EXPECTED_FIELDS = {"id", "locale", "text", "label", "split", "synthetic", "provenance"}
STOP_WORDS = {
    "a", "an", "and", "are", "for", "i", "in", "is", "it", "my", "of", "or", "the", "to", "want", "with",
    "का", "की", "के", "को", "में", "मुझे", "है", "करना", "चाहिए",
    "ഒരു", "എന്റെ", "എനിക്ക്", "ആണ്", "വേണം", "ചെയ്യണം",
}


class ModelError(ValueError):
    """A deterministic dataset or artifact validation failure."""


def normalize(text: str) -> str:
    """Match frontend NFKC/lowercase/letter-number-space normalization."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    characters = [character if character.isspace() or unicodedata.category(character)[:1] in {"L", "N"} else " " for character in normalized]
    return " ".join("".join(characters).split())


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_dataset(path: Path = DATASET_PATH) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ModelError("dataset is not valid UTF-8") from error
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            raise ModelError(f"blank dataset line {line_number}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ModelError(f"invalid JSON on dataset line {line_number}") from error
        if not isinstance(row, dict):
            raise ModelError(f"dataset line {line_number} must be an object")
        rows.append(row)
    validate_dataset(rows)
    return rows, sha256(raw)


def validate_dataset(rows: list[dict[str, Any]]) -> None:
    if not 27 <= len(rows) <= 2000:
        raise ModelError("dataset row count is outside the reviewed bound")
    ids: set[str] = set()
    normalized_rows: dict[str, tuple[str, str]] = {}
    counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        if set(row) != EXPECTED_FIELDS:
            raise ModelError(f"row has unexpected fields: {row.get('id', '<unknown>')}")
        identifier = row.get("id")
        text = row.get("text")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9-]{8,64}", identifier):
            raise ModelError("invalid stable row ID")
        if identifier in ids:
            raise ModelError(f"duplicate row ID: {identifier}")
        ids.add(identifier)
        if row.get("locale") not in LOCALES or row.get("label") not in LABELS or row.get("split") not in SPLITS:
            raise ModelError(f"invalid locale, label, or split: {identifier}")
        if row.get("synthetic") is not True or row.get("provenance") not in PROVENANCE:
            raise ModelError(f"invalid synthetic provenance: {identifier}")
        expected_provenance = PROVENANCE[0] if row["locale"] == "en" else PROVENANCE[1]
        if row["provenance"] != expected_provenance:
            raise ModelError(f"native-language review marker missing: {identifier}")
        if not isinstance(text, str) or not 1 <= len(text) <= MAX_QUERY_LENGTH:
            raise ModelError(f"text length is outside bounds: {identifier}")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in text):
            raise ModelError(f"malformed Unicode surrogate: {identifier}")
        if re.search(r"(?<!\d)(?:\d[ -]?){10,12}(?!\d)", text):
            raise ModelError(f"identifier-shaped digits are forbidden: {identifier}")
        normalized = normalize(text)
        if not normalized:
            raise ModelError(f"text normalizes to empty: {identifier}")
        previous = normalized_rows.get(normalized)
        if previous:
            previous_id, previous_split = previous
            if previous_split != row["split"]:
                raise ModelError(f"normalized split leakage: {previous_id} and {identifier}")
            raise ModelError(f"normalized duplicate: {previous_id} and {identifier}")
        normalized_rows[normalized] = (identifier, row["split"])
        counts[(row["locale"], row["label"], row["split"])] += 1
    for locale in LOCALES:
        for label in LABELS:
            for split in SPLITS:
                if counts[(locale, label, split)] < 2:
                    raise ModelError(f"insufficient {locale}/{label}/{split} coverage")
    for split in SPLITS:
        group_counts = [counts[(locale, label, split)] for locale in LOCALES for label in LABELS]
        if max(group_counts) - min(group_counts) > 1:
            raise ModelError(f"unbalanced {split} split")


def feature_counts(text: str, vocabulary: dict[str, int] | None = None) -> Counter[str] | Counter[int]:
    normalized = normalize(text)
    if not normalized or len(text) > MAX_QUERY_LENGTH:
        return Counter()
    bounded = f"^{normalized}$"
    raw: Counter[str] = Counter()
    for size in range(MIN_NGRAM, MAX_NGRAM + 1):
        for offset in range(max(0, len(bounded) - size + 1)):
            raw[bounded[offset : offset + size]] += 1
    for feature in raw:
        raw[feature] = min(raw[feature], MAX_FEATURE_COUNT)
    if vocabulary is None:
        return raw
    indexed: Counter[int] = Counter()
    for feature, count in raw.items():
        index = vocabulary.get(feature)
        if index is not None:
            indexed[index] = count
    return indexed


def train(rows: list[dict[str, Any]], dataset_digest: str) -> dict[str, Any]:
    train_rows = [row for row in rows if row["split"] == "train"]
    document_frequency: Counter[str] = Counter()
    for row in train_rows:
        document_frequency.update(feature_counts(row["text"]).keys())
    ranked = sorted(document_frequency, key=lambda feature: (-document_frequency[feature], feature))[:MAX_VOCABULARY]
    vocabulary = sorted(ranked)
    if not vocabulary or len(vocabulary) > MAX_VOCABULARY:
        raise ModelError("vocabulary is empty or unbounded")
    vocabulary_index = {feature: index for index, feature in enumerate(vocabulary)}
    label_documents = Counter(row["label"] for row in train_rows)
    label_features = {label: Counter() for label in LABELS}
    for row in train_rows:
        label_features[row["label"]].update(feature_counts(row["text"], vocabulary_index))
    class_log_priors = {label: round(math.log(label_documents[label] / len(train_rows)), 10) for label in LABELS}
    feature_log_probabilities: dict[str, list[float]] = {}
    for label in LABELS:
        total = sum(label_features[label].values())
        denominator = total + ALPHA * len(vocabulary)
        feature_log_probabilities[label] = [round(math.log((label_features[label][index] + ALPHA) / denominator), 10) for index in range(len(vocabulary))]
    base = {
        "schema_version": SCHEMA_VERSION,
        "model_type": MODEL_TYPE,
        "model_version": MODEL_VERSION,
        "generation_timestamp_policy": "omitted_for_byte_reproducibility",
        "dataset_digest": dataset_digest,
        "normalization_version": NORMALIZATION_VERSION,
        "labels": list(LABELS),
        "allowed_service_ids": {
            "aadhaar_address_update": "uidai-aadhaar-address-update",
            "kerala_old_age_pension": "kerala-ign-oap",
            "unsupported_other": None,
        },
        "input": {"max_code_points": MAX_QUERY_LENGTH},
        "features": {
            "minimum_ngram": MIN_NGRAM,
            "maximum_ngram": MAX_NGRAM,
            "maximum_feature_count": MAX_FEATURE_COUNT,
            "maximum_vocabulary": MAX_VOCABULARY,
            "vocabulary": vocabulary,
        },
        "training": {"alpha": ALPHA, "split": "train", "class_document_counts": {label: label_documents[label] for label in LABELS}},
        "class_log_priors": class_log_priors,
        "feature_log_probabilities": feature_log_probabilities,
        "normalization_vectors": [
            {"input": "  UPDATE\u00a0Aadhaar—ADDRESS! ", "output": "update aadhaar address"},
            {"input": "आधार… पता\nबदलना", "output": "आध र पत बदलन"},
            {"input": "ആധാർ\tവിലാസം🙂", "output": "ആധ ർ വ ല സ"},
            {"input": "ＡＡＤＨＡＡＲ １２", "output": "aadhaar 12"},
        ],
    }
    provisional = {**base, "thresholds": {"minimum_confidence": 0.0, "minimum_margin": 0.0, "tuned_on": "validation"}}
    confidence, margin = tune_thresholds(provisional, [row for row in rows if row["split"] == "validation"])
    model = {**base, "thresholds": {"minimum_confidence": confidence, "minimum_margin": margin, "tuned_on": "validation"}}
    validate_model(model, dataset_digest)
    return model


def raw_prediction(model: dict[str, Any], text: str) -> tuple[str | None, float, float]:
    if not text or len(text) > model["input"]["max_code_points"]:
        return None, 0.0, 0.0
    vocabulary = {feature: index for index, feature in enumerate(model["features"]["vocabulary"])}
    counts = feature_counts(text, vocabulary)
    if not counts:
        return None, 0.0, 0.0
    scores = {}
    for label in model["labels"]:
        scores[label] = model["class_log_priors"][label] + sum(count * model["feature_log_probabilities"][label][index] for index, count in counts.items())
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    maximum = ordered[0][1]
    exponentials = {label: math.exp(score - maximum) for label, score in ordered}
    total = sum(exponentials.values())
    probabilities = {label: value / total for label, value in exponentials.items()}
    confidence = probabilities[ordered[0][0]]
    margin = confidence - probabilities[ordered[1][0]]
    return ordered[0][0], confidence, margin


def predict(model: dict[str, Any], text: str) -> tuple[str | None, float, float]:
    label, confidence, margin = raw_prediction(model, text)
    thresholds = model["thresholds"]
    if label is None or confidence < thresholds["minimum_confidence"] or margin < thresholds["minimum_margin"]:
        return None, confidence, margin
    return label, confidence, margin


def tune_thresholds(model: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[float, float]:
    best: tuple[tuple[float, ...], float, float] | None = None
    for confidence in (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85):
        for margin in (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4):
            predicted = []
            for row in rows:
                label, row_confidence, row_margin = raw_prediction(model, row["text"])
                predicted.append(label if row_confidence >= confidence and row_margin >= margin else None)
            correct = sum(actual["label"] == guess for actual, guess in zip(rows, predicted, strict=True))
            supported_false_positive = sum(actual["label"] == "unsupported_other" and guess in LABELS[:2] for actual, guess in zip(rows, predicted, strict=True))
            accepted = sum(guess is not None for guess in predicted)
            objective = (-supported_false_positive, correct / len(rows), accepted / len(rows), confidence, margin)
            if best is None or objective > best[0]:
                best = (objective, confidence, margin)
    if best is None:
        raise ModelError("threshold tuning failed")
    return best[1], best[2]


def validate_model(model: dict[str, Any], dataset_digest: str) -> None:
    if model.get("schema_version") != SCHEMA_VERSION or model.get("model_type") != MODEL_TYPE or model.get("model_version") != MODEL_VERSION:
        raise ModelError("model schema, type, or version mismatch")
    if model.get("dataset_digest") != dataset_digest or model.get("normalization_version") != NORMALIZATION_VERSION:
        raise ModelError("dataset digest or normalization version mismatch")
    if model.get("labels") != list(LABELS):
        raise ModelError("model labels are not the allowlist")
    if model.get("allowed_service_ids") != {"aadhaar_address_update": "uidai-aadhaar-address-update", "kerala_old_age_pension": "kerala-ign-oap", "unsupported_other": None}:
        raise ModelError("model service allowlist mismatch")
    vocabulary = model.get("features", {}).get("vocabulary")
    if not isinstance(vocabulary, list) or vocabulary != sorted(set(vocabulary)) or not 1 <= len(vocabulary) <= MAX_VOCABULARY:
        raise ModelError("invalid vocabulary")
    thresholds = model.get("thresholds", {})
    if thresholds.get("tuned_on") != "validation" or not 0.5 <= thresholds.get("minimum_confidence", -1) <= 0.95 or not 0.0 <= thresholds.get("minimum_margin", -1) <= 0.9:
        raise ModelError("invalid thresholds")
    numeric_values: list[float] = list(model.get("class_log_priors", {}).values())
    for label in LABELS:
        weights = model.get("feature_log_probabilities", {}).get(label)
        if not isinstance(weights, list) or len(weights) != len(vocabulary):
            raise ModelError(f"invalid weight vector: {label}")
        numeric_values.extend(weights)
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in numeric_values):
        raise ModelError("model contains a non-finite number")
    for vector in model.get("normalization_vectors", []):
        if normalize(vector["input"]) != vector["output"]:
            raise ModelError("normalization vector drift")


def metrics(rows: list[dict[str, Any]], predictions: list[str | None]) -> dict[str, Any]:
    matrix = {actual: {predicted: 0 for predicted in (*LABELS, "abstain")} for actual in LABELS}
    for row, prediction in zip(rows, predictions, strict=True):
        matrix[row["label"]][prediction or "abstain"] += 1
    per_class = {}
    for label in LABELS:
        true_positive = matrix[label][label]
        false_positive = sum(matrix[actual][label] for actual in LABELS if actual != label)
        false_negative = sum(matrix[label][predicted] for predicted in (*LABELS, "abstain") if predicted != label)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": round(precision, 6), "recall": round(recall, 6), "f1": round(f1, 6), "support": sum(matrix[label].values())}
    accepted = [index for index, prediction in enumerate(predictions) if prediction is not None]
    correct = sum(row["label"] == prediction for row, prediction in zip(rows, predictions, strict=True))
    return {
        "accuracy": round(correct / len(rows), 6),
        "macro_precision": round(sum(item["precision"] for item in per_class.values()) / len(LABELS), 6),
        "macro_recall": round(sum(item["recall"] for item in per_class.values()) / len(LABELS), 6),
        "macro_f1": round(sum(item["f1"] for item in per_class.values()) / len(LABELS), 6),
        "per_class": per_class,
        "confusion_matrix": matrix,
        "abstention_coverage": round(1 - len(accepted) / len(rows), 6),
        "accepted_prediction_accuracy": round(sum(rows[index]["label"] == predictions[index] for index in accepted) / len(accepted), 6) if accepted else 0.0,
    }


def deterministic_match(text: str, locale: str) -> str | None:
    """Port the current TypeScript pack-phrase matcher for agreement reporting."""
    pack_paths = (
        ROOT / "procedure-packs/packs/uidai-aadhaar-address-update/1.5.0/pack.json",
        ROOT / "procedure-packs/packs/kerala-ign-oap/1.3.0/pack.json",
    )
    procedures = []
    for label, path in zip(LABELS[:2], pack_paths, strict=True):
        pack = json.loads(path.read_text(encoding="utf-8"))
        phrases = pack["intent_phrases"] if locale == "en" else pack["localization"]["translations"][locale]["intent_phrases"]
        procedures.append((label, phrases))
    query = normalize(text)
    query_tokens = set(meaningful_tokens(text))
    if not query or not query_tokens:
        return None
    frequency: Counter[str] = Counter()
    for _, phrases in procedures:
        for phrase in phrases:
            frequency.update(set(meaningful_tokens(phrase)))
    candidates = []
    for label, phrases in procedures:
        best = 0
        for phrase in phrases:
            normalized_phrase = normalize(phrase)
            phrase_tokens = list(dict.fromkeys(meaningful_tokens(phrase)))
            if not normalized_phrase or not phrase_tokens:
                continue
            matched = [token for token in phrase_tokens if token in query_tokens]
            total_weight = sum(1 + math.log((len(procedures) + 1) / (frequency[token] + 1)) for token in phrase_tokens)
            matched_weight = sum(1 + math.log((len(procedures) + 1) / (frequency[token] + 1)) for token in matched)
            score = round((matched_weight / total_weight) * 400) if total_weight else 0
            if query == normalized_phrase:
                score += 1000
            elif normalized_phrase in query:
                score += 700
            elif len(matched) == len(phrase_tokens):
                score += 300
            best = max(best, score)
        candidates.append((label, best))
    candidates.sort(key=lambda item: (-item[1], item[0]))
    if candidates[0][1] < 260 or candidates[0][1] - candidates[1][1] < 70:
        return None
    return candidates[0][0]


def meaningful_tokens(text: str) -> list[str]:
    return [token for token in normalize(text).split(" ") if len(token) > 1 and token not in STOP_WORDS]


def evaluation_report(model: dict[str, Any], rows: list[dict[str, Any]], model_digest: str) -> dict[str, Any]:
    test_rows = [row for row in rows if row["split"] == "test"]
    held_out_case_coverage = {
        "clear_aadhaar": ["en-aad-te-001", "hi-aad-te-001", "ml-aad-te-001"],
        "clear_kerala_pension": ["en-pen-te-002", "hi-pen-te-001", "ml-pen-te-001"],
        "unsupported_service": ["hi-uns-te-001", "ml-uns-te-001"],
        "ambiguous": ["en-uns-te-001"],
        "transliteration": ["en-pen-te-001", "hi-pen-te-002"],
        "misspelling": ["en-aad-te-001", "en-pen-te-001", "hi-aad-te-001"],
        "mixed_script": ["hi-aad-te-002", "ml-aad-te-002", "ml-pen-te-002"],
        "emoji_and_control": ["en-uns-te-002", "ml-aad-te-001"],
        "repeated_characters": ["hi-uns-te-001"],
        "prompt_injection": ["en-aad-te-002", "hi-uns-te-002", "ml-uns-te-002"],
        "very_short": ["en-uns-te-002"],
        "very_long_bounded": ["en-aad-te-002"],
    }
    test_ids = {row["id"] for row in test_rows}
    if any(identifier not in test_ids for identifiers in held_out_case_coverage.values() for identifier in identifiers):
        raise ModelError("held-out evaluation case coverage references a non-test row")
    predictions = [predict(model, row["text"])[0] for row in test_rows]
    report = metrics(test_rows, predictions)
    report["per_language"] = {}
    for locale in LOCALES:
        indices = [index for index, row in enumerate(test_rows) if row["locale"] == locale]
        report["per_language"][locale] = metrics([test_rows[index] for index in indices], [predictions[index] for index in indices])
    deterministic = [deterministic_match(row["text"], row["locale"]) for row in test_rows]
    comparable = [index for index, label in enumerate(deterministic) if label is not None]
    report["deterministic_ml_agreement_rate"] = round(sum(predictions[index] == deterministic[index] for index in comparable) / len(comparable), 6) if comparable else 0.0
    unsupported_indices = [index for index, row in enumerate(test_rows) if row["label"] == "unsupported_other"]
    report["unsupported_false_positive_rate"] = round(sum(predictions[index] in LABELS[:2] for index in unsupported_indices) / len(unsupported_indices), 6)
    report.update({
        "schema_version": 1,
        "evaluation_split": "test",
        "test_examples": len(test_rows),
        "held_out_case_coverage": held_out_case_coverage,
        "model_digest": model_digest,
        "dataset_digest": model["dataset_digest"],
        "limitations": "Metrics describe a small, synthetic, fixed held-out set and are not evidence of real-world accuracy. Hindi and Malayalam require native-speaker review.",
    })
    return report


def build_outputs() -> tuple[bytes, bytes, bytes]:
    rows, dataset_digest = load_dataset()
    model = train(rows, dataset_digest)
    artifact = canonical_bytes(model)
    if len(artifact) > 500 * 1024:
        raise ModelError(f"artifact exceeds 500 KiB: {len(artifact)} bytes")
    model_digest = sha256(artifact)
    digest = f"{model_digest}  {ARTIFACT_PATH.name}\n".encode()
    report = canonical_bytes(evaluation_report(model, rows, model_digest))
    return artifact, digest, report


def write_outputs(outputs: Iterable[tuple[Path, bytes]]) -> None:
    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def check_outputs(outputs: Iterable[tuple[Path, bytes]]) -> None:
    failures = []
    for path, expected in outputs:
        if not path.exists() or path.read_bytes() != expected:
            try:
                failures.append(str(path.relative_to(ROOT)))
            except ValueError:
                failures.append(str(path))
    if failures:
        raise ModelError(f"generated artifact drift: {', '.join(failures)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write byte-reproducible model, digest, and report")
    mode.add_argument("--check", action="store_true", help="fail if tracked generated outputs drift")
    mode.add_argument("--evaluate", action="store_true", help="print the deterministic held-out evaluation report")
    arguments = parser.parse_args(argv)
    try:
        artifact, digest, report = build_outputs()
        outputs = ((ARTIFACT_PATH, artifact), (DIGEST_PATH, digest), (REPORT_PATH, report))
        if arguments.write:
            write_outputs(outputs)
            print(f"wrote model {digest.decode().split()[0]} ({len(artifact)} bytes)")
        elif arguments.check:
            check_outputs(outputs)
            print(f"model artifacts are current ({len(artifact)} bytes)")
        else:
            sys.stdout.buffer.write(report)
    except (OSError, ModelError) as error:
        print(f"intent model error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
