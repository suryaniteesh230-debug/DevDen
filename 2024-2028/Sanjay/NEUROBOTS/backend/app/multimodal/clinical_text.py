from __future__ import annotations

import re
from dataclasses import dataclass


EXTRACTOR_NAME = "NEUROBOTS deterministic clinical text extractor"
EXTRACTOR_VERSION = "clinical-text-extractor-1.0.0"


@dataclass(frozen=True, slots=True)
class ExtractedSymptom:
    name: str
    present: bool
    matched_text: str
    negation: str | None
    extraction_confidence: float

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "present": self.present,
            "matched_text": self.matched_text,
            "negation": self.negation,
            "extraction_confidence": self.extraction_confidence,
        }


class ClinicalTextExtractor:
    extractor_name = EXTRACTOR_NAME
    extractor_version = EXTRACTOR_VERSION
    _concepts = {
        "chest pain": ("chest pain", "chest pressure", "chest discomfort"),
        "shortness of breath": ("shortness of breath", "breathlessness", "dyspnea", "dyspnoea"),
        "sweating": ("sweating", "diaphoresis", "clammy"),
        "nausea": ("nausea", "nauseated"),
        "vomiting": ("vomiting", "vomited", "emesis"),
        "dizziness": ("dizziness", "dizzy", "lightheaded", "light-headed"),
        "palpitations": ("palpitations", "racing heart"),
    }
    _negation = re.compile(
        r"\b(no|not|denies|denied|without|negative for|does not report|did not report)\b",
        re.IGNORECASE,
    )

    def extract(self, text: str) -> list[ExtractedSymptom]:
        findings: list[ExtractedSymptom] = []
        folded = text.casefold()
        for canonical, aliases in self._concepts.items():
            matches = [
                match
                for alias in aliases
                if (match := re.search(rf"\b{re.escape(alias)}\b", folded))
            ]
            if not matches:
                continue
            match = min(matches, key=lambda item: item.start())
            prefix = folded[max(0, match.start() - 55) : match.start()]
            boundary = max(prefix.rfind("."), prefix.rfind(";"), prefix.rfind(","))
            local_prefix = prefix[boundary + 1 :]
            negations = list(self._negation.finditer(local_prefix))
            negation = negations[-1].group(0) if negations else None
            findings.append(
                ExtractedSymptom(
                    name=canonical,
                    present=negation is None,
                    matched_text=text[match.start() : match.end()],
                    negation=negation,
                    extraction_confidence=0.92 if negation is None else 0.9,
                )
            )
        return findings
