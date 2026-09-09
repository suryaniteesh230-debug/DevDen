"""Run the two-pass Phase 1 reassessment demo through the FastAPI endpoint."""

import asyncio
import json
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import RiskPrediction, TriageAssessment
from app.db.session import build_engine, get_db
from app.main import app


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _assessment_view(result: dict) -> dict:
    return {
        "workflow_id": result["workflow_id"],
        "cardiac_risk": {
            key: result["cardiac_risk"].get(key)
            for key in (
                "prediction_id",
                "probability",
                "predicted_class",
                "model_name",
                "model_version",
            )
        },
        "model_contributions": {
            "method": result["explanation"].get("method"),
            "top_contributors": result["explanation"].get("top_contributors"),
        },
        "triage": {
            key: result["triage"].get(key)
            for key in (
                "assessment_id",
                "severity_level",
                "prototype_esi_level",
                "policy_name",
                "policy_version",
                "provisional",
                "rule_hits",
                "missing_information",
                "input_snapshot",
                "disclaimer",
            )
        },
        "priority": result["priority"],
        "agent_trace": result["agent_trace"],
    }


async def demo() -> dict:
    with tempfile.TemporaryDirectory(prefix="neurobots-triage-demo-") as directory:
        engine = build_engine(f"sqlite:///{Path(directory) / 'demo.db'}")
        SessionFactory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )
        Base.metadata.create_all(engine)

        async def override_get_db() -> AsyncGenerator[Session, None]:
            with SessionFactory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://demo"
            ) as client:
                patient = (
                    await client.post(
                        "/api/patients",
                        json={
                            "external_patient_id": "TRIAGE-DEMO-001",
                            "first_name": "Demo",
                            "last_name": "Patient",
                            "date_of_birth": "1978-04-18",
                            "gender": "female",
                        },
                    )
                ).json()
                encounter = (
                    await client.post(
                        f"/api/patients/{patient['id']}/encounters",
                        json={
                            "encounter_type": "emergency",
                            "chief_complaint": "Suspected heart attack",
                            "started_at": "2026-08-07T08:00:00Z",
                        },
                    )
                ).json()
                for symptom in (
                    {
                        "name": "chest pain",
                        "severity": 8,
                        "duration": "30 minutes",
                        "onset": "2026-08-07T07:30:00Z",
                    },
                    {"name": "shortness of breath", "severity": 7},
                    {"name": "sweating", "severity": 6},
                ):
                    response = await client.post(
                        f"/api/encounters/{encounter['id']}/symptoms", json=symptom
                    )
                    response.raise_for_status()
                for lab in (
                    {"test_name": "blood sugar", "value": 146, "unit": "mg/dL"},
                    {"test_name": "CK-MB", "value": 8.4, "unit": "ng/mL"},
                    {"test_name": "troponin", "value": 0.18, "unit": "ng/mL"},
                ):
                    response = await client.post(
                        f"/api/encounters/{encounter['id']}/labs", json=lab
                    )
                    response.raise_for_status()

                first_vitals = (
                    await client.post(
                        f"/api/encounters/{encounter['id']}/vitals",
                        json={
                            "heart_rate": 108,
                            "systolic_bp": 148,
                            "diastolic_bp": 90,
                            "spo2": 95,
                            "respiratory_rate": 22,
                            "temperature": 37.1,
                            "measured_at": "2026-08-07T08:05:00Z",
                            "source": "SIMULATOR",
                        },
                    )
                ).json()
                first_response = await client.post(
                    f"/api/encounters/{encounter['id']}/workflow"
                )
                first_response.raise_for_status()
                first = first_response.json()

                second_vitals = (
                    await client.post(
                        f"/api/encounters/{encounter['id']}/vitals",
                        json={
                            "heart_rate": 104,
                            "systolic_bp": 142,
                            "diastolic_bp": 86,
                            "spo2": 96,
                            "respiratory_rate": 20,
                            "temperature": 37.0,
                            "measured_at": "2026-08-07T08:10:00Z",
                            "source": "SIMULATOR",
                        },
                    )
                ).json()
                second_response = await client.post(
                    f"/api/encounters/{encounter['id']}/workflow"
                )
                second_response.raise_for_status()
                second = second_response.json()

            with SessionFactory() as session:
                predictions = list(
                    session.scalars(
                        select(RiskPrediction)
                        .where(RiskPrediction.encounter_id == encounter["id"])
                        .order_by(RiskPrediction.created_at, RiskPrediction.id)
                    ).all()
                )
                assessments = list(
                    session.scalars(
                        select(TriageAssessment)
                        .where(TriageAssessment.encounter_id == encounter["id"])
                        .order_by(TriageAssessment.created_at, TriageAssessment.id)
                    ).all()
                )
                history = {
                    "risk_prediction_ids": [item.id for item in predictions],
                    "triage_assessments": [
                        {
                            "id": item.id,
                            "severity_level": item.severity_level,
                            "policy_version": item.policy_version,
                            "provisional": item.provisional,
                            "vitals_id": item.input_snapshot["latest_vitals"]["id"],
                        }
                        for item in assessments
                    ],
                }
        finally:
            app.dependency_overrides.clear()
            engine.dispose()

    return {
        "endpoint": f"POST /api/encounters/{encounter['id']}/workflow",
        "first_vitals_id": first_vitals["id"],
        "second_vitals_id": second_vitals["id"],
        "first_assessment": _assessment_view(first),
        "second_assessment": _assessment_view(second),
        "severity_changed": (
            first["triage"]["severity_level"] != second["triage"]["severity_level"]
        ),
        "persisted_history": history,
    }


if __name__ == "__main__":
    result = asyncio.run(demo())
    output_path = BACKEND_DIR / "triage" / "reassessment_demo.json"
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
