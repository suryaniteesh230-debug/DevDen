import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from tools import intent_model


def test_dataset_is_balanced_synthetic_and_has_no_normalized_split_leakage():
    rows, digest = intent_model.load_dataset()
    assert len(rows) == 81
    assert len(digest) == 64
    assert all(row["synthetic"] is True for row in rows)
    assert all(
        row["locale"] == "en" or row["provenance"].endswith("native_review_required")
        for row in rows
    )
    normalized = [(intent_model.normalize(row["text"]), row["split"]) for row in rows]
    assert len({text for text, _ in normalized}) == len(rows)


def test_trainer_is_byte_deterministic_and_artifacts_have_expected_digests():
    first = intent_model.build_outputs()
    second = intent_model.build_outputs()
    assert first == second
    artifact, digest_file, report = first
    digest = hashlib.sha256(artifact).hexdigest()
    assert digest_file.decode() == f"{digest}  intent-model.v1.json\n"
    model = json.loads(artifact)
    evaluation = json.loads(report)
    assert model["dataset_digest"] == hashlib.sha256(intent_model.DATASET_PATH.read_bytes()).hexdigest()
    assert evaluation["model_digest"] == digest
    assert len(artifact) <= 500 * 1024
    frontend_contract = (intent_model.ROOT / "frontend/src/localIntent.ts").read_text()
    assert re.search(rf"EXPECTED_MODEL_DIGEST = '{digest}'", frontend_contract)
    assert re.search(rf"EXPECTED_DATASET_DIGEST = '{model['dataset_digest']}'", frontend_contract)


def test_trainer_rejects_invalid_label_and_split_leakage():
    rows, _ = intent_model.load_dataset()
    invalid = copy.deepcopy(rows)
    invalid[0]["label"] = "not_allowed"
    with pytest.raises(intent_model.ModelError, match="invalid locale, label, or split"):
        intent_model.validate_dataset(invalid)
    leaked = copy.deepcopy(rows)
    leaked[0]["text"] = leaked[-1]["text"] + "!!!"
    with pytest.raises(intent_model.ModelError, match="normalized split leakage"):
        intent_model.validate_dataset(leaked)


def test_trainer_rejects_malformed_unicode_and_unbounded_vocabulary():
    rows, _ = intent_model.load_dataset()
    malformed = copy.deepcopy(rows)
    malformed[0]["text"] = "bad\ud800text"
    with pytest.raises(intent_model.ModelError, match="malformed Unicode"):
        intent_model.validate_dataset(malformed)
    original = intent_model.MAX_VOCABULARY
    try:
        intent_model.MAX_VOCABULARY = 0
        with pytest.raises(intent_model.ModelError, match="vocabulary"):
            intent_model.train(rows, "a" * 64)
    finally:
        intent_model.MAX_VOCABULARY = original


def test_normalization_vectors_and_held_out_evaluation_contract():
    artifact, _, report_bytes = intent_model.build_outputs()
    model = json.loads(artifact)
    for vector in model["normalization_vectors"]:
        assert intent_model.normalize(vector["input"]) == vector["output"]
    report = json.loads(report_bytes)
    assert report["evaluation_split"] == "test"
    assert report["test_examples"] == 18
    assert 0 <= report["unsupported_false_positive_rate"] <= 1
    assert set(report["held_out_case_coverage"]) == {
        "clear_aadhaar", "clear_kerala_pension", "unsupported_service", "ambiguous", "transliteration",
        "misspelling", "mixed_script", "emoji_and_control", "repeated_characters", "prompt_injection",
        "very_short", "very_long_bounded",
    }
    assert set(report["per_language"]) == set(intent_model.LOCALES)
    assert report["limitations"].startswith("Metrics describe a small, synthetic")


def test_check_mode_detects_regeneration_drift(tmp_path: Path):
    expected = ((tmp_path / "artifact.json", b"expected"),)
    expected[0][0].write_bytes(b"drift")
    with pytest.raises(intent_model.ModelError, match="generated artifact drift"):
        intent_model.check_outputs(expected)
