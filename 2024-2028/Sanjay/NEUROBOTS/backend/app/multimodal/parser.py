from __future__ import annotations

import re
from dataclasses import dataclass


PARSER_NAME = "NEUROBOTS clinical document parser"
PARSER_VERSION = "clinical-document-parser-1.0.0"


@dataclass(frozen=True, slots=True)
class ParsedLab:
    test_name: str
    value: float
    unit: str | None
    source_text: str
    extraction_confidence: float

    def as_dict(self) -> dict[str, object]:
        return {
            "field_type": "LAB_RESULT",
            "test_name": self.test_name,
            "value": self.value,
            "unit": self.unit,
            "source_text": self.source_text,
            "extraction_confidence": self.extraction_confidence,
        }


class ClinicalDocumentParser:
    """Conservative deterministic parser for explicitly supported printed lab names."""

    parser_name = PARSER_NAME
    parser_version = PARSER_VERSION
    _aliases = {
        "troponin": ("troponin", "troponin i", "troponin t", "hs troponin", "hs-troponin"),
        "CK-MB": ("ck-mb", "ck mb", "ckmb"),
        "blood_sugar": ("blood sugar", "blood glucose", "glucose"),
        "creatinine": ("creatinine",),
        "potassium": ("potassium",),
        "haemoglobin": ("haemoglobin", "hemoglobin", "hgb"),
        "WBC": ("white blood cell", "white cell count", "wbc"),
    }
    _value_pattern = re.compile(
        r"(?:[:=]\s*|\s+)(?P<value>[+-]?(?:\d+(?:\.\d+)?|\.\d+))"
        r"(?:\s*(?P<unit>[a-zA-Zµμ%/\^0-9.\-]+))?",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> list[ParsedLab]:
        parsed: list[ParsedLab] = []
        seen: set[tuple[str, float, str | None]] = set()
        aliases = sorted(
            (
                (alias, canonical)
                for canonical, values in self._aliases.items()
                for alias in values
            ),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )
        for raw_line in text.splitlines():
            line = " ".join(raw_line.strip().split())
            if not line:
                continue
            folded = line.casefold()
            for alias, canonical in aliases:
                match = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", folded)
                if not match:
                    continue
                value_match = self._value_pattern.search(line, match.end())
                if not value_match:
                    continue
                value = float(value_match.group("value"))
                unit = value_match.group("unit")
                key = (canonical, value, unit.casefold() if unit else None)
                if key not in seen:
                    seen.add(key)
                    parsed.append(
                        ParsedLab(
                            test_name=canonical,
                            value=value,
                            unit=unit,
                            source_text=line[:500],
                            extraction_confidence=0.9 if unit else 0.8,
                        )
                    )
                break
        return parsed
