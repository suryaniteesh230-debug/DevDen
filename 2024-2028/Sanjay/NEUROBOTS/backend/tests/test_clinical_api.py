from tests.conftest import ApiClient


def create_encounter(client: ApiClient, patient_id: str, complaint: str) -> dict:
    response = client.post(
        f"/api/patients/{patient_id}/encounters",
        json={"encounter_type": "emergency", "chief_complaint": complaint},
    )
    assert response.status_code == 201
    return response.json()


def test_health_endpoint(client: ApiClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "neurobots-clinical-api"


def test_patient_can_be_created_found_and_retrieved(
    client: ApiClient, patient_payload: dict
) -> None:
    created = client.post("/api/patients", json=patient_payload)
    assert created.status_code == 201
    patient = created.json()

    by_external_id = client.get(
        "/api/patients", params={"external_patient_id": "HOSP-1001"}
    )
    by_name = client.get("/api/patients", params={"name": "mira patel"})
    by_id = client.get(f"/api/patients/{patient['id']}")

    assert [item["id"] for item in by_external_id.json()] == [patient["id"]]
    assert [item["id"] for item in by_name.json()] == [patient["id"]]
    assert by_id.json()["external_patient_id"] == "HOSP-1001"


def test_multiple_encounters_belong_to_one_patient(client: ApiClient, patient: dict) -> None:
    first = create_encounter(client, patient["id"], "Previous chest discomfort")
    second = create_encounter(client, patient["id"], "New chest pain")

    history = client.get(f"/api/patients/{patient['id']}/history")

    assert history.status_code == 200
    encounter_ids = {item["id"] for item in history.json()["encounters"]}
    assert encounter_ids == {first["id"], second["id"]}
    assert all(item["patient_id"] == patient["id"] for item in history.json()["encounters"])


def test_symptoms_vitals_and_generic_labs_are_stored(
    client: ApiClient, encounter: dict
) -> None:
    symptom = client.post(
        f"/api/encounters/{encounter['id']}/symptoms",
        json={"name": "chest pain", "severity": 8, "duration": "30 minutes"},
    )
    first_vitals = client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={
            "heart_rate": 104,
            "systolic_bp": 148,
            "diastolic_bp": 92,
            "spo2": 95,
            "respiratory_rate": 22,
            "temperature": 37.1,
        },
    )
    second_vitals = client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={"heart_rate": 98, "spo2": 96, "source": "WEARABLE"},
    )
    troponin = client.post(
        f"/api/encounters/{encounter['id']}/labs",
        json={"test_name": "troponin", "value": 0.12, "unit": "ng/mL"},
    )
    custom_lab = client.post(
        f"/api/encounters/{encounter['id']}/labs",
        json={
            "test_name": "future-test-type",
            "value": 42,
            "reference_metadata": {"reference_range": "10-50"},
        },
    )

    assert symptom.status_code == 201
    assert first_vitals.status_code == 201
    assert second_vitals.status_code == 201
    assert troponin.status_code == 201
    assert custom_lab.status_code == 201
    assert len(client.get(f"/api/encounters/{encounter['id']}/symptoms").json()) == 1
    assert len(client.get(f"/api/encounters/{encounter['id']}/vitals").json()) == 2
    assert len(client.get(f"/api/encounters/{encounter['id']}/labs").json()) == 2


def test_simulator_uses_shared_vitals_path_and_provenance(
    client: ApiClient, encounter: dict
) -> None:
    manual = client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={"heart_rate": 90, "source": "MANUAL"},
    )
    simulated = client.post(f"/api/encounters/{encounter['id']}/simulate-vitals")
    readings = client.get(f"/api/encounters/{encounter['id']}/vitals").json()

    assert manual.status_code == 201
    assert simulated.status_code == 201
    assert simulated.json()["source"] == "SIMULATOR"
    assert {reading["source"] for reading in readings} == {"MANUAL", "SIMULATOR"}


def test_invalid_vital_input_is_rejected(client: ApiClient, encounter: dict) -> None:
    negative_heart_rate = client.post(
        f"/api/encounters/{encounter['id']}/vitals", json={"heart_rate": -1}
    )
    invalid_spo2 = client.post(
        f"/api/encounters/{encounter['id']}/vitals", json={"spo2": 101}
    )
    no_measurements = client.post(
        f"/api/encounters/{encounter['id']}/vitals", json={"source": "MANUAL"}
    )

    assert negative_heart_rate.status_code == 422
    assert invalid_spo2.status_code == 422
    assert no_measurements.status_code == 422


def test_required_checkpoint_workflow_and_patient_history(
    client: ApiClient, patient: dict
) -> None:
    historical = create_encounter(client, patient["id"], "Prior historical visit")
    client.patch(f"/api/encounters/{historical['id']}", json={"status": "COMPLETED"})
    current = create_encounter(client, patient["id"], "Suspected heart attack")

    for symptom_name in ("chest pain", "shortness of breath", "sweating"):
        response = client.post(
            f"/api/encounters/{current['id']}/symptoms",
            json={"name": symptom_name, "source": "MANUAL"},
        )
        assert response.status_code == 201

    manual_vitals = client.post(
        f"/api/encounters/{current['id']}/vitals",
        json={
            "heart_rate": 112,
            "systolic_bp": 152,
            "diastolic_bp": 94,
            "spo2": 94,
            "respiratory_rate": 24,
            "temperature": 37,
            "source": "MANUAL",
        },
    )
    for lab in (
        {"test_name": "troponin", "value": 0.18, "unit": "ng/mL"},
        {"test_name": "CK-MB", "value": 8.4, "unit": "ng/mL"},
        {"test_name": "blood_sugar", "value": 146, "unit": "mg/dL"},
    ):
        assert client.post(f"/api/encounters/{current['id']}/labs", json=lab).status_code == 201
    simulated_vitals = client.post(f"/api/encounters/{current['id']}/simulate-vitals")
    history = client.get(f"/api/patients/{patient['id']}/history")

    assert manual_vitals.status_code == 201
    assert simulated_vitals.status_code == 201
    assert history.status_code == 200
    history_body = history.json()
    assert history_body["patient"]["id"] == patient["id"]
    assert {item["id"] for item in history_body["encounters"]} == {
        historical["id"],
        current["id"],
    }
    current_history = next(
        item for item in history_body["encounters"] if item["id"] == current["id"]
    )
    assert len(current_history["symptoms"]) == 3
    assert len(current_history["vital_signs"]) == 2
    assert len(current_history["lab_results"]) == 3
    assert {reading["source"] for reading in current_history["vital_signs"]} == {
        "MANUAL",
        "SIMULATOR",
    }
