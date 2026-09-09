from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Explanation, RiskPrediction
from app.ml.artifact import load_cardiac_artifact
from app.ml.cardiac_risk import CardiacRiskTool
from app.ml.dataset import audit_dataset, load_feature_schema
from app.ml.explanation import ShapExplanationTool
from tests.conftest import ApiClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASET_PATH = BACKEND_DIR / "data" / "raw" / "Heart Attack.csv"
SCHEMA_PATH = BACKEND_DIR / "ml" / "feature_schema.json"


def _create_encounter(client: ApiClient, patient_id: str) -> dict:
    response = client.post(
        f"/api/patients/{patient_id}/encounters",
        json={
            "encounter_type": "emergency",
            "chief_complaint": "Suspected myocardial infarction",
            "started_at": "2026-08-07T08:00:00Z",
        },
    )
    assert response.status_code == 201
    return response.json()


def _add_complete_features(client: ApiClient, encounter_id: str) -> tuple[dict, dict]:
    for name in ("chest pain", "shortness of breath", "sweating"):
        assert client.post(
            f"/api/encounters/{encounter_id}/symptoms", json={"name": name}
        ).status_code == 201
    old_vitals = client.post(
        f"/api/encounters/{encounter_id}/vitals",
        json={
            "heart_rate": 80,
            "systolic_bp": 130,
            "diastolic_bp": 75,
            "measured_at": "2026-08-07T08:01:00Z",
            "source": "MANUAL",
        },
    ).json()
    latest_vitals = client.post(
        f"/api/encounters/{encounter_id}/vitals",
        json={
            "heart_rate": 108,
            "systolic_bp": 148,
            "diastolic_bp": 90,
            "measured_at": "2026-08-07T08:05:00Z",
            "source": "SIMULATOR",
        },
    ).json()
    for lab in (
        {"test_name": "blood sugar", "value": 146, "unit": "mg/dL"},
        {"test_name": "CK-MB", "value": 8.4, "unit": "ng/mL"},
        {"test_name": "troponin", "value": 0.18, "unit": "ng/mL"},
    ):
        assert client.post(
            f"/api/encounters/{encounter_id}/labs", json=lab
        ).status_code == 201
    return old_vitals, latest_vitals


def test_dataset_validation_and_feature_schema_mapping() -> None:
    audit = audit_dataset(DATASET_PATH, SCHEMA_PATH)
    schema = load_feature_schema(SCHEMA_PATH)

    assert audit["row_count"] == 1319
    assert audit["columns"] == [
        "age",
        "gender",
        "impluse",
        "pressurehight",
        "pressurelow",
        "glucose",
        "kcm",
        "troponin",
        "class",
    ]
    assert audit["target_values"] == ["negative", "positive"]
    assert audit["class_distribution"] == {"negative": 509, "positive": 810}
    assert set(audit["missing_values"].values()) == {0}
    assert audit["duplicate_rows"] == 0
    assert audit["invalid_row_count"] == 11
    mapping = {
        feature["raw_column"]: feature["internal_name"]
        for feature in schema["features"]
    }
    assert mapping == {
        "age": "age",
        "gender": "gender",
        "impluse": "heart_rate",
        "pressurehight": "systolic_bp",
        "pressurelow": "diastolic_bp",
        "glucose": "blood_sugar",
        "kcm": "ck_mb",
        "troponin": "troponin",
    }


def test_versioned_model_artifact_loads() -> None:
    artifact = load_cardiac_artifact(get_settings().heart_attack_model_path)

    assert artifact["metadata"]["model_name"] == "RandomForestClassifier"
    assert artifact["metadata"]["model_version"] == "cardiac-risk-rf-1.0.0"
    assert artifact["metadata"]["classification_threshold"] == 0.5
    assert artifact["metadata"]["clinical_validation"] == "NOT_CLINICALLY_VALIDATED"


def test_cardiac_risk_tool_predicts_and_reports_incomplete_input() -> None:
    complete = {
        "age": 64,
        "gender": 1,
        "heart_rate": 70,
        "systolic_bp": 120,
        "diastolic_bp": 55,
        "blood_sugar": 270,
        "ck_mb": 13.87,
        "troponin": 0.122,
    }
    tool = CardiacRiskTool()
    result = tool.predict(complete)

    assert result["status"] == "SUCCESS"
    assert result["predicted_class"] in {0, 1}
    assert 0 <= result["probability"] <= 1
    assert result["model_version"] == "cardiac-risk-rf-1.0.0"
    assert result["input_features"] == complete

    incomplete = tool.predict({**complete, "troponin": None, "ck_mb": None})
    assert incomplete["status"] == "INCOMPLETE_INPUT"
    assert incomplete["missing_features"] == ["ck_mb", "troponin"]
    assert "probability" not in incomplete

    invalid = tool.predict({**complete, "systolic_bp": 70, "diastolic_bp": 90})
    assert invalid["status"] == "INVALID_INPUT"
    assert invalid["invalid_features"] == ["systolic_bp", "diastolic_bp"]
    assert "probability" not in invalid


def test_shap_tool_returns_ranked_model_feature_contributions() -> None:
    features = {
        "age": 64,
        "gender": 1,
        "heart_rate": 70,
        "systolic_bp": 120,
        "diastolic_bp": 55,
        "blood_sugar": 270,
        "ck_mb": 13.87,
        "troponin": 0.122,
    }
    risk = CardiacRiskTool().predict(features)
    explanation = ShapExplanationTool().explain(features)

    assert explanation["status"] == "SUCCESS"
    assert explanation["method"] == "TreeSHAP"
    assert len(explanation["feature_contributions"]) == 8
    assert [item["rank"] for item in explanation["feature_contributions"]] == list(
        range(1, 9)
    )
    assert explanation["feature_contributions"][0]["magnitude"] >= explanation[
        "feature_contributions"
    ][-1]["magnitude"]
    shap_sum = explanation["base_value"] + sum(
        item["shap_value"] for item in explanation["feature_contributions"]
    )
    assert abs(shap_sum - risk["probability"]) < 1e-9


def test_workflow_builds_latest_features_persists_prediction_and_xai(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    old_vitals, latest_vitals = _add_complete_features(client, encounter["id"])

    response = client.post(f"/api/encounters/{encounter['id']}/workflow")
    assert response.status_code == 200
    result = response.json()
    risk = result["cardiac_risk"]

    assert risk["status"] == "SUCCESS"
    assert risk["input_features"] == {
        "age": 48,
        "gender": 0.0,
        "heart_rate": 108.0,
        "systolic_bp": 148.0,
        "diastolic_bp": 90.0,
        "blood_sugar": 146.0,
        "ck_mb": 8.4,
        "troponin": 0.18,
    }
    assert risk["feature_source_snapshot"]["vitals_id"] == latest_vitals["id"]
    assert risk["feature_source_snapshot"]["vitals_id"] != old_vitals["id"]
    assert result["triage"]["status"] == "SUCCESS"
    assert result["triage"]["policy_version"] == "prototype-esi-subset-1.0.0"
    assert result["triage"]["prototype_esi_level"] == 2
    assert result["triage"]["esi"] is None
    trace_status = {entry["agent"]: entry["status"] for entry in result["agent_trace"]}
    assert trace_status["triage_risk"] == "SUCCESS"
    assert trace_status["xai"] == "PARTIAL"
    assert len(result["explanation"]["feature_contributions"]) == 8
    assert result["explanation"]["model_contributions"]["feature_contributions"]
    assert result["explanation"]["triage_rule_trace"]["rules"]
    assert result["explanation"]["prediction_id"] == risk["prediction_id"]

    db_session.expire_all()
    prediction = db_session.get(RiskPrediction, risk["prediction_id"])
    explanation = db_session.get(Explanation, result["explanation"]["explanation_id"])
    assert prediction is not None
    assert prediction.input_feature_snapshot == risk["input_features"]
    assert explanation is not None
    assert explanation.prediction_id == prediction.id
    assert len(explanation.feature_contributions) == 8


def test_multiple_workflow_predictions_append_history(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    _add_complete_features(client, encounter["id"])

    first = client.post(f"/api/encounters/{encounter['id']}/workflow").json()
    second = client.post(f"/api/encounters/{encounter['id']}/workflow").json()
    db_session.expire_all()
    predictions = list(
        db_session.scalars(
            select(RiskPrediction).where(RiskPrediction.encounter_id == encounter["id"])
        ).all()
    )
    explanations = list(db_session.scalars(select(Explanation)).all())

    assert first["cardiac_risk"]["prediction_id"] != second["cardiac_risk"][
        "prediction_id"
    ]
    assert len(predictions) == 2
    assert len(explanations) == 2
    assert {item.prediction_id for item in explanations} == {
        item.id for item in predictions
    }


def test_incomplete_workflow_never_persists_or_fabricates_prediction(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    assert client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={"heart_rate": 90, "systolic_bp": 130, "diastolic_bp": 80},
    ).status_code == 201
    assert client.post(
        f"/api/encounters/{encounter['id']}/labs",
        json={"test_name": "blood sugar", "value": 120},
    ).status_code == 201

    result = client.post(f"/api/encounters/{encounter['id']}/workflow").json()

    assert result["cardiac_risk"]["status"] == "INCOMPLETE_INPUT"
    assert result["cardiac_risk"]["predicted_class"] is None
    assert result["cardiac_risk"]["probability"] is None
    assert result["cardiac_risk"]["missing_features"] == ["ck_mb", "troponin"]
    assert "cardiac_model_feature:ck_mb" in result["missing_information"]
    assert result["explanation"]["feature_contributions"] is None
    db_session.expire_all()
    assert list(db_session.scalars(select(RiskPrediction)).all()) == []
    assert list(db_session.scalars(select(Explanation)).all()) == []
