from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.workflows.clinical_state import ClinicalState


def _age_on(date_of_birth: str | date, reference: str | datetime | None) -> int | None:
    try:
        born = (
            date_of_birth
            if isinstance(date_of_birth, date)
            else date.fromisoformat(str(date_of_birth)[:10])
        )
        on_date = (
            reference.date()
            if isinstance(reference, datetime)
            else date.fromisoformat(str(reference)[:10])
        ) if reference else date.today()
    except (TypeError, ValueError):
        return None
    return on_date.year - born.year - ((on_date.month, on_date.day) < (born.month, born.day))


def _without_local_identifiers(item: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key
        not in {
            "id",
            "encounter_id",
            "patient_id",
            "external_patient_id",
            "first_name",
            "last_name",
            "phone_number",
            "date_of_birth",
            "created_at",
            "updated_at",
        }
        and (key != timestamp or value is not None)
    }


def build_phi_minimized_reasoning_payload(state: ClinicalState) -> dict[str, Any]:
    """Build the only initial clinical payload permitted to leave the edge.

    Names, contact details, external IDs, database IDs, exact date of birth, raw
    notes, and raw historical records are deliberately excluded. Local tools add
    only clinically relevant, provenance-aware observations if the model asks.
    """

    patient = state.get("patient") or {}
    encounter = state.get("encounter") or {}
    symptoms = [
        {
            key: value
            for key, value in symptom.items()
            if key in {"name", "severity", "duration", "onset", "present", "source"}
        }
        for symptom in state.get("normalized_symptoms", [])
    ]
    vitals = state.get("current_vitals") or {}
    labs = state.get("current_labs") or {}
    cardiac = state.get("cardiac_risk") or {}
    triage = state.get("triage") or {}
    return {
        "payload_policy": "PHI-minimized reasoning payload v1",
        "demographics": {
            "approximate_age_years": _age_on(
                patient.get("date_of_birth", ""), encounter.get("started_at")
            ),
            "gender": patient.get("gender"),
        },
        "normalized_symptoms": symptoms,
        "current_vitals": _without_local_identifiers(vitals, timestamp="measured_at"),
        "current_labs": {
            name: _without_local_identifiers(lab, timestamp="collected_at")
            for name, lab in labs.items()
        },
        "cardiac_model_output": {
            key: cardiac.get(key)
            for key in (
                "status",
                "predicted_class",
                "probability",
                "threshold",
                "model_name",
                "model_version",
                "missing_features",
            )
            if key in cardiac
        },
        "prototype_triage_output": {
            key: triage.get(key)
            for key in (
                "status",
                "severity_level",
                "provisional",
                "triggered_rule_ids",
                "missing_information",
                "policy_name",
                "policy_version",
            )
            if key in triage
        },
    }
