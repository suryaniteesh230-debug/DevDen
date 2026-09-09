from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Explanation, RiskPrediction
from app.repositories.clinical import ExplanationRepository, RiskPredictionRepository


class RiskAssessmentPersistenceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.predictions = RiskPredictionRepository(session)
        self.explanations = ExplanationRepository(session)

    def persist_prediction(
        self, encounter_id: str, result: dict[str, Any]
    ) -> RiskPrediction:
        prediction = self.predictions.add(
            RiskPrediction(
                encounter_id=encounter_id,
                model_name=result["model_name"],
                model_version=result["model_version"],
                predicted_class=result["predicted_class"],
                probability=result["probability"],
                threshold=result["threshold"],
                input_feature_snapshot=result["input_features"],
                inference_latency_ms=result["inference_latency_ms"],
            )
        )
        self.session.commit()
        self.session.refresh(prediction)
        return prediction

    def persist_explanation(
        self, prediction_id: str, result: dict[str, Any]
    ) -> Explanation:
        explanation = self.explanations.add(
            Explanation(
                prediction_id=prediction_id,
                explanation_method=result["method"],
                explainer_version=result["explainer_version"],
                model_version=result["model_version"],
                feature_contributions=result["feature_contributions"],
            )
        )
        self.session.commit()
        self.session.refresh(explanation)
        return explanation
