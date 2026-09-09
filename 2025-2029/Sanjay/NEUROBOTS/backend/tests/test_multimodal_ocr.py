from __future__ import annotations

from app.api.routes.multimodal import get_ocr_service
from app.core.enums import ObservationSource
from app.db.models import LabResult
from app.main import app
from app.multimodal.ocr import OCRResult, OCRService, TesseractOCRService
from app.multimodal.parser import ClinicalDocumentParser
from app.services.document_ingestion import DocumentIngestionService
from tests.conftest import ApiClient


class ScriptedOCRService(OCRService):
    def __init__(self, text: str) -> None:
        self.text = text

    def extract(self, content: bytes, content_type: str) -> OCRResult:
        assert content
        return OCRResult(
            text=self.text,
            confidence=0.94,
            engine="scripted-test-ocr",
            engine_version="1.0;lang=eng",
            page_count=1,
        )


def test_clinical_document_parser_only_extracts_allowlisted_numeric_labs() -> None:
    parsed = ClinicalDocumentParser().parse(
        """
        Printed laboratory report
        Troponin I: 0.18 ng/mL   high
        CK-MB 8.4 ng/mL
        Blood glucose = 146 mg/dL
        Impression: possible cardiac event
        Aspirin 81 mg daily
        """
    )

    assert [(item.test_name, item.value, item.unit) for item in parsed] == [
        ("troponin", 0.18, "ng/mL"),
        ("CK-MB", 8.4, "ng/mL"),
        ("blood_sugar", 146.0, "mg/dL"),
    ]


def test_document_ingestion_preserves_manual_conflict_and_ocr_provenance(
    db_session, patient_payload
) -> None:
    from app.schemas.clinical import EncounterCreate, PatientCreate
    from app.services.encounters import EncounterService
    from app.services.patients import PatientService

    patient = PatientService(db_session).create(PatientCreate(**patient_payload))
    encounter = EncounterService(db_session).create(
        patient.id,
        EncounterCreate(encounter_type="emergency", chief_complaint="Chest pain"),
    )
    db_session.add(
        LabResult(
            encounter_id=encounter.id,
            test_name="troponin",
            value=0.12,
            unit="ng/mL",
            source=ObservationSource.MANUAL,
        )
    )
    db_session.commit()

    document = DocumentIngestionService(
        db_session,
        ocr_service=ScriptedOCRService("Troponin I: 0.18 ng/mL\nCK-MB: 8.4 ng/mL"),
    ).ingest(
        encounter_id=encounter.id,
        content=b"scripted image",
        content_type="image/png",
        filename="../../unsafe lab report.png",
    )

    labs = DocumentIngestionService(db_session).observations.list_labs(encounter.id)
    assert document.safe_filename == "unsafe_lab_report.png"
    assert [lab.source for lab in labs] == [ObservationSource.MANUAL, ObservationSource.OCR, ObservationSource.OCR]
    assert document.conflicts == [
        {
            "field_type": "LAB_RESULT",
            "test_name": "troponin",
            "existing_observation_id": labs[0].id,
            "existing_source": "MANUAL",
            "existing_value": 0.12,
            "existing_unit": "ng/mL",
            "ocr_value": 0.18,
            "ocr_unit": "ng/mL",
            "resolution": "PRESERVED_BOTH_REVIEW_REQUIRED",
        }
    ]
    assert labs[1].reference_metadata["document_id"] == document.id
    assert labs[1].reference_metadata["parser_version"] == "clinical-document-parser-1.0.0"


def test_document_api_upload_list_get_and_workflow_multimodal_state(
    client: ApiClient, encounter: dict
) -> None:
    async def scripted_service() -> OCRService:
        return ScriptedOCRService(
            "Troponin I: 0.18 ng/mL\nBlood glucose: 146 mg/dL"
        )

    app.dependency_overrides[get_ocr_service] = scripted_service
    try:
        manual = client.post(
            f"/api/encounters/{encounter['id']}/labs",
            json={"test_name": "troponin", "value": 0.12, "unit": "ng/mL"},
        )
        assert manual.status_code == 201
        response = client.post(
            f"/api/encounters/{encounter['id']}/documents",
            content=b"fake-png-for-scripted-service",
            headers={"Content-Type": "image/png", "X-Filename": "../lab report.png"},
        )
        assert response.status_code == 201
        document = response.json()
        assert document["safe_filename"] == "lab_report.png"
        assert document["source"] == "OCR"
        assert document["ocr_engine"] == "scripted-test-ocr"
        assert len(document["lab_result_ids"]) == 2
        assert document["conflicts"][0]["resolution"] == "PRESERVED_BOTH_REVIEW_REQUIRED"

        listed = client.get(f"/api/encounters/{encounter['id']}/documents")
        fetched = client.get(f"/api/documents/{document['id']}")
        assert [item["id"] for item in listed.json()] == [document["id"]]
        assert fetched.json()["ocr_text"].startswith("Troponin")

        workflow = client.post(f"/api/encounters/{encounter['id']}/workflow").json()
        assert workflow["ocr_text"].startswith("Troponin")
        assert workflow["document_results"][0]["document_id"] == document["id"]
        assert workflow["current_labs"]["troponin"]["id"] == manual.json()["id"]
        assert workflow["fused_context"]["multimodal_conflicts"]
        assert workflow["capability_status"]["ocr_extraction"]["status"] == "AVAILABLE"
    finally:
        app.dependency_overrides.pop(get_ocr_service, None)


def test_tesseract_adapter_rejects_mime_signature_mismatch() -> None:
    try:
        TesseractOCRService().extract(b"not-a-png", "image/png")
    except Exception as exception:
        assert getattr(exception, "code", None) == "DOCUMENT_SIGNATURE_MISMATCH"
        assert getattr(exception, "status_code", None) == 415
    else:
        raise AssertionError("signature mismatch was accepted")
