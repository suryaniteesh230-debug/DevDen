"""Exercise the live registration-to-dashboard contract against running servers."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


API_BASE = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"


def request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{API_BASE}{path}",
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed ({error.code}): {detail}") from error


def main() -> int:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    health = request_json("GET", "/health")
    patient = request_json(
        "POST",
        "/api/patients",
        {
            "external_patient_id": f"E2E-{suffix}",
            "first_name": "Vertical",
            "last_name": "Slice",
            "date_of_birth": "1970-01-01",
            "gender": "male",
        },
    )
    encounter = request_json(
        "POST",
        f"/api/patients/{patient['id']}/encounters",
        {"encounter_type": "emergency", "chief_complaint": "Chest pain and dyspnea"},
    )
    encounter_id = encounter["id"]

    for symptom in ("chest pain", "shortness of breath"):
        request_json(
            "POST",
            f"/api/encounters/{encounter_id}/symptoms",
            {"name": symptom, "severity": 8, "duration": "30 minutes", "source": "MANUAL"},
        )
    request_json(
        "POST",
        f"/api/encounters/{encounter_id}/vitals",
        {
            "heart_rate": 122,
            "systolic_bp": 158,
            "diastolic_bp": 92,
            "spo2": 93,
            "respiratory_rate": 26,
            "temperature": 37.1,
            "source": "MANUAL",
        },
    )
    for test_name, value, unit in (
        ("blood_sugar", 168, "mg/dL"),
        ("ck_mb", 8.2, "ng/mL"),
        ("troponin", 0.8, "ng/mL"),
    ):
        request_json(
            "POST",
            f"/api/encounters/{encounter_id}/labs",
            {"test_name": test_name, "value": value, "unit": unit, "source": "MANUAL"},
        )

    workflow = request_json("POST", f"/api/encounters/{encounter_id}/workflow")
    initial_assessment = request_json("GET", f"/api/encounters/{encounter_id}/assessment")
    initial_queue = request_json("GET", "/api/queue")
    initial_queue_entry = next(
        (item for item in initial_queue if item["encounter_id"] == encounter_id), None
    )

    request_json(
        "POST",
        f"/api/encounters/{encounter_id}/vitals",
        {
            "heart_rate": 150,
            "systolic_bp": 120,
            "diastolic_bp": 78,
            "spo2": 88,
            "respiratory_rate": 36,
            "temperature": 37.3,
            "source": "MANUAL",
        },
    )
    reassessment = request_json("POST", f"/api/encounters/{encounter_id}/workflow")
    assessment = request_json("GET", f"/api/encounters/{encounter_id}/assessment")
    queue = request_json("GET", "/api/queue")
    history = request_json("GET", f"/api/encounters/{encounter_id}/assessment-history")
    with urlopen(FRONTEND_URL, timeout=15) as response:
        frontend_html = response.read().decode("utf-8", errors="replace")

    queue_entry = next((item for item in queue if item["encounter_id"] == encounter_id), None)
    assert health["status"] == "ok"
    assert workflow["workflow_status"] == "COMPLETED"
    assert reassessment["workflow_status"] == "COMPLETED"
    assert initial_assessment["cardiac_risk"] is not None
    assert assessment["cardiac_risk"] is not None
    assert assessment["triage"] is not None
    assert assessment["priority"] is not None
    assert assessment["explanation"]["feature_contributions"]
    assert assessment["clinical_reasoning"] is not None
    assert initial_queue_entry is not None
    assert queue_entry is not None
    assert queue_entry["id"] == initial_queue_entry["id"]
    assert queue_entry["deterioration_status"] == "DETECTED"
    assert len(history["risk_predictions"]) == 2
    assert len(history["triage_assessments"]) == 2
    assert len(history["priority_calculations"]) == 2
    assert "NextCare" in frontend_html

    called = request_json(
        "PATCH", f"/api/queue/{queue_entry['id']}", {"queue_status": "CALLED"}
    )
    in_assessment = request_json(
        "PATCH", f"/api/queue/{queue_entry['id']}", {"queue_status": "IN_ASSESSMENT"}
    )
    refreshed_assessment = request_json(
        "GET", f"/api/encounters/{encounter_id}/assessment"
    )
    assert called["queue_status"] == "CALLED"
    assert in_assessment["queue_status"] == "IN_ASSESSMENT"
    assert refreshed_assessment["priority"]["queue_status"] == "IN_ASSESSMENT"

    print(
        json.dumps(
            {
                "patient_id": patient["id"],
                "encounter_id": encounter_id,
                "workflow_status": workflow["workflow_status"],
                "cardiac_status": assessment["cardiac_risk"]["status"],
                "triage_status": assessment["triage"]["status"],
                "reasoning_status": assessment["clinical_reasoning"]["status"],
                "priority_band": queue_entry["priority_band"],
                "queue_rank": queue_entry["rank"],
                "deterioration_status": queue_entry["deterioration_status"],
                "assessment_runs": len(history["triage_assessments"]),
                "queue_transition": "WAITING -> CALLED -> IN_ASSESSMENT",
                "frontend_served": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
