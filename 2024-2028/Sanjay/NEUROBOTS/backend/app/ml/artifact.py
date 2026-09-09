from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib


@lru_cache(maxsize=4)
def _load_artifact(path: str, modified_ns: int) -> dict[str, Any]:
    del modified_ns
    artifact = joblib.load(path)
    required = {"pipeline", "metadata", "feature_schema"}
    if not isinstance(artifact, dict) or not required <= artifact.keys():
        raise ValueError("Cardiac model artifact has an incompatible structure")
    return artifact


def load_cardiac_artifact(path: str | Path) -> dict[str, Any]:
    artifact_path = Path(path)
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Cardiac model artifact was not found: {artifact_path}")
    return _load_artifact(str(artifact_path.resolve()), artifact_path.stat().st_mtime_ns)
