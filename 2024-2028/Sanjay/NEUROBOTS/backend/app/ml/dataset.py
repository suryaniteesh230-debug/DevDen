from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np


def load_feature_schema(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as source:
        return json.load(source)


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        return list(reader.fieldnames or []), list(reader)


def _invalid_reasons(
    internal_row: dict[str, float], schema: dict[str, Any]
) -> list[str]:
    reasons: list[str] = []
    by_name = {item["internal_name"]: item for item in schema["features"]}
    for name, value in internal_row.items():
        feature = by_name[name]
        if "valid_values" in feature and value not in feature["valid_values"]:
            reasons.append(f"{name}:invalid_value")
        bounds = feature.get("valid_range", {})
        if "minimum" in bounds and value < bounds["minimum"]:
            reasons.append(f"{name}:below_minimum")
        if "exclusive_minimum" in bounds and value <= bounds["exclusive_minimum"]:
            reasons.append(f"{name}:below_exclusive_minimum")
        if "maximum" in bounds and value > bounds["maximum"]:
            reasons.append(f"{name}:above_maximum")
    if internal_row["diastolic_bp"] > internal_row["systolic_bp"]:
        reasons.append("diastolic_bp:above_systolic_bp")
    return reasons


def audit_dataset(dataset_path: str | Path, schema_path: str | Path) -> dict[str, Any]:
    dataset_path = Path(dataset_path)
    schema = load_feature_schema(schema_path)
    columns, rows = _read_rows(dataset_path)
    expected_columns = [item["raw_column"] for item in schema["features"]] + [
        schema["dataset"]["target_column"]
    ]
    if columns != expected_columns:
        raise ValueError(f"Dataset columns {columns!r} do not match schema {expected_columns!r}")

    checksum = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    if checksum != schema["dataset"]["sha256"]:
        raise ValueError("Dataset checksum does not match the approved feature schema")

    missing = {column: sum(not row[column].strip() for row in rows) for column in columns}
    duplicate_count = len(rows) - len(
        {tuple(row[column] for column in columns) for row in rows}
    )
    target = schema["dataset"]["target_column"]
    target_distribution = dict(Counter(row[target] for row in rows))
    invalid_rows: list[dict[str, Any]] = []
    numeric_summaries: dict[str, dict[str, Any]] = {}
    for feature in schema["features"]:
        raw_name = feature["raw_column"]
        values = [float(row[raw_name]) for row in rows if row[raw_name].strip()]
        numeric_summaries[raw_name] = {
            "inferred_type": (
                "integer" if values and all(value.is_integer() for value in values) else "float"
            ),
            "minimum": min(values),
            "maximum": max(values),
            "unique_count": len(set(values)),
        }
    for index, row in enumerate(rows, start=2):
        if any(not row[column].strip() for column in expected_columns):
            invalid_rows.append({"csv_line": index, "reasons": ["missing_value"]})
            continue
        internal = {
            item["internal_name"]: float(row[item["raw_column"]])
            for item in schema["features"]
        }
        reasons = _invalid_reasons(internal, schema)
        if row[target] not in schema["dataset"]["target_encoding"]:
            reasons.append("target:invalid_value")
        if reasons:
            invalid_rows.append({"csv_line": index, "reasons": reasons})

    return {
        "dataset_filename": dataset_path.name,
        "dataset_identifier": schema["dataset"]["identifier"],
        "sha256": checksum,
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": columns,
        "data_types": {
            **{name: detail["inferred_type"] for name, detail in numeric_summaries.items()},
            target: "categorical",
        },
        "target_column": target,
        "target_values": sorted(target_distribution),
        "class_distribution": target_distribution,
        "missing_values": missing,
        "duplicate_rows": duplicate_count,
        "numeric_summaries": numeric_summaries,
        "invalid_rows": invalid_rows,
        "invalid_row_count": len(invalid_rows),
        "valid_row_count": len(rows) - len(invalid_rows),
        "potential_leakage": {
            "explicit_fields": [],
            "clinical_caveat": (
                "Troponin and CK-MB are contemporaneous diagnostic biomarkers; "
                "high discrimination is not evidence of prospective screening validity."
            ),
        },
    }


def prepare_training_arrays(
    dataset_path: str | Path, schema_path: str | Path
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    dataset_path = Path(dataset_path)
    schema = load_feature_schema(schema_path)
    audit = audit_dataset(dataset_path, schema_path)
    columns, rows = _read_rows(dataset_path)
    unique_rows = list(dict.fromkeys(tuple(row[column] for column in columns) for row in rows))
    features: list[list[float]] = []
    targets: list[int] = []
    excluded = Counter()
    target_name = schema["dataset"]["target_column"]
    for values in unique_rows:
        row = dict(zip(columns, values, strict=True))
        if any(not row[column].strip() for column in columns):
            excluded["missing_value"] += 1
            continue
        internal = {
            item["internal_name"]: float(row[item["raw_column"]])
            for item in schema["features"]
        }
        reasons = _invalid_reasons(internal, schema)
        if reasons:
            excluded.update(reasons)
            continue
        features.append([internal[name] for name in schema["feature_order"]])
        targets.append(schema["dataset"]["target_encoding"][row[target_name]])
    preparation = {
        **audit,
        "rows_after_duplicate_policy": len(unique_rows),
        "rows_used_for_training_split": len(features),
        "excluded_reason_counts": dict(excluded),
        "prepared_class_distribution": dict(Counter(targets)),
    }
    return np.asarray(features, dtype=float), np.asarray(targets, dtype=int), preparation
