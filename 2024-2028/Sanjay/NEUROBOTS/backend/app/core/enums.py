from enum import StrEnum


class ObservationSource(StrEnum):
    MANUAL = "MANUAL"
    SIMULATOR = "SIMULATOR"
    OCR = "OCR"
    SPEECH = "SPEECH"
    EHR = "EHR"
    WEARABLE = "WEARABLE"


class EncounterStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class QueueStatus(StrEnum):
    WAITING = "WAITING"
    IN_ASSESSMENT = "IN_ASSESSMENT"
    CALLED = "CALLED"
    COMPLETED = "COMPLETED"
    REMOVED = "REMOVED"


class PriorityBand(StrEnum):
    CRITICAL = "CRITICAL"
    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    ROUTINE = "ROUTINE"


class StaffRole(StrEnum):
    DOCTOR = "DOCTOR"
    NURSE = "NURSE"
    ADMIN = "ADMIN"
