from __future__ import annotations

from datetime import date, datetime
from time import perf_counter
from typing import Any


POLICY_NAME = "NEUROBOTS Prototype ESI Subset"
POLICY_VERSION = "prototype-esi-subset-1.0.0"
POLICY_CREATED_AT = "2026-08-07"

REFERENCE_SOURCES = [
    {
        "title": "Emergency Severity Index Handbook, Fifth Edition",
        "publisher": "Emergency Nurses Association",
        "url": "https://emscimprovement.center/documents/2177/Emergency_Severity_Index_Handbook.pdf",
    },
    {
        "title": "Emergency Severity Index (ESI): A Triage Tool for Emergency Departments",
        "publisher": "Agency for Healthcare Research and Quality",
        "url": "https://www.ahrq.gov/patient-safety/settings/hospital/resource/about.html",
    },
]

SUPPORTED_INPUTS = [
    "patient.date_of_birth",
    "encounter.started_at",
    "symptoms[].name",
    "symptoms[].present",
    "symptoms[].severity",
    "symptoms[].onset",
    "symptoms[].duration",
    "vitals.latest.heart_rate",
    "vitals.latest.spo2",
    "vitals.latest.respiratory_rate",
    "cardiac_risk.predicted_class (supporting only)",
    "cardiac_risk.probability (supporting only)",
    "cardiac_risk.model_version (supporting only)",
]

LIMITATIONS = [
    "Hackathon clinical decision-support prototype; not clinically validated.",
    "Does not replace clinician assessment or implement the complete ESI algorithm.",
    "Cannot identify ESI level 1 without immediate-intervention, airway, breathing, circulation, mental-status, and clinician-observation inputs.",
    "Cannot distinguish ESI levels 3, 4, and 5 without anticipated resource count and clinician assessment.",
    "Never converts cardiac-model probability directly into emergency severity or queue priority.",
]

ALWAYS_UNAVAILABLE_FULL_ESI_INPUTS = [
    "immediate_life_saving_intervention_need",
    "consciousness_level",
    "clinician_high_risk_assessment",
    "anticipated_resource_count",
]


def _age_on(date_of_birth: Any, at_time: Any) -> int | None:
    if not date_of_birth or not at_time:
        return None
    try:
        born = date.fromisoformat(str(date_of_birth))
        observed = datetime.fromisoformat(str(at_time).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None
    return observed.year - born.year - (
        (observed.month, observed.day) < (born.month, born.day)
    )


def _rule(
    rule_id: str,
    description: str,
    inputs_used: dict[str, Any],
    triggered: bool,
    effect: str,
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "version": "1.0.0",
        "description": description,
        "inputs_used": inputs_used,
        "triggered": triggered,
        "effect": effect,
    }


class EmergencyTriageTool:
    """Evaluate a narrow ESI-informed policy without HTTP or workflow dependencies."""

    policy_name = POLICY_NAME
    policy_version = POLICY_VERSION

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "policy_name": POLICY_NAME,
            "policy_version": POLICY_VERSION,
            "created_at": POLICY_CREATED_AT,
            "reference_sources": REFERENCE_SOURCES,
            "supported_inputs": SUPPORTED_INPUTS,
            "limitations": LIMITATIONS,
        }

    def assess(
        self,
        fused_context: dict[str, Any] | None,
        cardiac_risk: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        fused = fused_context or {}
        patient = fused.get("patient") or {}
        encounter = fused.get("encounter") or {}
        symptoms = [
            item
            for item in (fused.get("symptoms") or [])
            if item.get("present", True)
        ]
        latest_vitals = (fused.get("vitals") or {}).get("latest") or {}
        cardiac = cardiac_risk or {}

        age = _age_on(patient.get("date_of_birth"), encounter.get("started_at"))
        heart_rate = latest_vitals.get("heart_rate")
        respiratory_rate = latest_vitals.get("respiratory_rate")
        spo2 = latest_vitals.get("spo2")
        adult_vital_screen = bool(
            age is not None
            and age > 18
            and (
                (heart_rate is not None and heart_rate > 100)
                or (respiratory_rate is not None and respiratory_rate > 20)
                or (spo2 is not None and spo2 < 92)
            )
        )

        names = {str(item.get("name", "")).strip().casefold() for item in symptoms}
        chest_pain = "chest pain" in names
        shortness_of_breath = any(
            name in names for name in ("shortness of breath", "dyspnea")
        )
        sweating = any(name in names for name in ("sweating", "diaphoresis"))
        high_risk_symptom_cluster = chest_pain and (shortness_of_breath or sweating)
        severe_reported_distress = any(
            isinstance(item.get("severity"), (int, float))
            and item["severity"] >= 7
            for item in symptoms
        )
        cardiac_support = bool(
            cardiac.get("status") == "SUCCESS"
            and cardiac.get("predicted_class") == 1
            and isinstance(cardiac.get("probability"), (int, float))
            and cardiac["probability"] >= 0.8
        )

        missing_information = list(ALWAYS_UNAVAILABLE_FULL_ESI_INPUTS)
        if age is None:
            missing_information.append("adult_age_context")
        for field in ("heart_rate", "respiratory_rate", "spo2"):
            if latest_vitals.get(field) is None:
                missing_information.append(field)
        if not symptoms:
            missing_information.append("current_symptoms")
        if not any(item.get("severity") is not None for item in symptoms):
            missing_information.append("pain_or_distress_score")
        if symptoms and not any(item.get("onset") for item in symptoms):
            missing_information.append("symptom_onset")
        if symptoms and not any(item.get("duration") for item in symptoms):
            missing_information.append("symptom_duration")
        missing_information = list(dict.fromkeys(missing_information))

        rule_hits = [
            _rule(
                "TRIAGE-001",
                "Adult ESI-v5 high-risk vital-sign screen prompts escalation reassessment.",
                {
                    "age": age,
                    "heart_rate": heart_rate,
                    "respiratory_rate": respiratory_rate,
                    "spo2": spo2,
                    "thresholds": {"heart_rate_gt": 100, "respiratory_rate_gt": 20, "spo2_lt": 92},
                },
                adult_vital_screen,
                "PROVISIONAL_LEVEL_2_SIGNAL" if adult_vital_screen else "NO_EFFECT",
            ),
            _rule(
                "TRIAGE-002",
                "High-risk symptom cluster: current chest pain with dyspnea or sweating.",
                {
                    "chest_pain": chest_pain,
                    "shortness_of_breath": shortness_of_breath,
                    "sweating": sweating,
                },
                high_risk_symptom_cluster,
                "PROVISIONAL_LEVEL_2_SIGNAL" if high_risk_symptom_cluster else "NO_EFFECT",
            ),
            _rule(
                "TRIAGE-003",
                "Reported symptom severity of 7/10 or greater is a consideration, not an automatic level assignment.",
                {
                    "reported_severities": [item.get("severity") for item in symptoms],
                },
                severe_reported_distress,
                "SUPPORTING_SIGNAL_ONLY" if severe_reported_distress else "NO_EFFECT",
            ),
            _rule(
                "TRIAGE-004",
                "High cardiac-model output is recorded as supporting context only.",
                {
                    "status": cardiac.get("status"),
                    "predicted_class": cardiac.get("predicted_class"),
                    "probability": cardiac.get("probability"),
                    "model_version": cardiac.get("model_version"),
                    "threshold": 0.8,
                },
                cardiac_support,
                "SUPPORTING_SIGNAL_ONLY" if cardiac_support else "NO_EFFECT",
            ),
            _rule(
                "TRIAGE-005",
                "Missing full-ESI inputs require a provisional, limited assessment.",
                {"missing_information": missing_information},
                bool(missing_information),
                "MARK_PROVISIONAL" if missing_information else "NO_EFFECT",
            ),
        ]

        clinical_level_2_signal = adult_vital_screen or high_risk_symptom_cluster
        prototype_esi_level = 2 if clinical_level_2_signal else None
        severity_level = "PROTOTYPE_ESI_2" if prototype_esi_level == 2 else "UNDETERMINED"

        supported_field_states = {
            "age": age is not None,
            "symptoms": bool(symptoms),
            "pain_or_distress_score": any(item.get("severity") is not None for item in symptoms),
            "symptom_onset": any(item.get("onset") for item in symptoms),
            "symptom_duration": any(item.get("duration") for item in symptoms),
            "heart_rate": heart_rate is not None,
            "respiratory_rate": respiratory_rate is not None,
            "spo2": spo2 is not None,
            "cardiac_risk": cardiac.get("status") == "SUCCESS",
        }
        available_count = sum(supported_field_states.values())
        completeness = {
            "available_supported_inputs": [
                name for name, available in supported_field_states.items() if available
            ],
            "missing_supported_inputs": [
                name for name, available in supported_field_states.items() if not available
            ],
            "available_count": available_count,
            "supported_input_count": len(supported_field_states),
            "ratio": available_count / len(supported_field_states),
            "full_esi_inputs_complete": False,
        }
        confidence = {
            "status": (
                "PROVISIONAL_RULE_MATCH"
                if prototype_esi_level == 2
                else "INSUFFICIENT_FOR_LEVEL_ASSIGNMENT"
            ),
            "numeric_confidence": None,
            "reason": "No clinically validated confidence model is implemented.",
        }
        input_snapshot = {
            "patient": {
                "id": patient.get("id"),
                "date_of_birth": patient.get("date_of_birth"),
                "age_at_encounter": age,
            },
            "encounter": {
                "id": encounter.get("id"),
                "started_at": encounter.get("started_at"),
            },
            "symptoms": symptoms,
            "latest_vitals": latest_vitals,
            "cardiac_risk": {
                "status": cardiac.get("status"),
                "predicted_class": cardiac.get("predicted_class"),
                "probability": cardiac.get("probability"),
                "model_version": cardiac.get("model_version"),
            },
        }
        return {
            "status": "SUCCESS",
            "policy_name": POLICY_NAME,
            "policy_version": POLICY_VERSION,
            "severity_level": severity_level,
            "prototype_esi_level": prototype_esi_level,
            "esi": None,
            "assigned_priority": None,
            "provisional": True,
            "completeness": completeness,
            "confidence": confidence,
            "rule_hits": rule_hits,
            "triggered_rule_ids": [item["id"] for item in rule_hits if item["triggered"]],
            "missing_information": missing_information,
            "rationale": {
                "basis": (
                    "CLINICAL_RULE_MATCH"
                    if clinical_level_2_signal
                    else "INSUFFICIENT_INFORMATION_FOR_LEVEL"
                ),
                "cardiac_risk_used_for_level": False,
                "level_1_supported": False,
                "levels_3_to_5_supported": False,
            },
            "input_snapshot": input_snapshot,
            "evaluation_latency_ms": (perf_counter() - started) * 1000,
            "disclaimer": (
                "Hackathon clinical decision-support prototype only; not clinically "
                "validated for real-world emergency triage and does not replace clinician assessment."
            ),
        }
