from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from time import perf_counter
from typing import Any

from app.workflows.clinical_state import CapabilityStatus, ClinicalState


class AgentExecutionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"
    PENDING_CAPABILITY = "PENDING_CAPABILITY"
    FAILED = "FAILED"


class CapabilityAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    PENDING_CAPABILITY = "PENDING_CAPABILITY"
    UNAVAILABLE = "UNAVAILABLE"


def capability(
    status: CapabilityAvailability, reason: str, **details: Any
) -> CapabilityStatus:
    value = CapabilityStatus(status=status.value, reason=reason)
    if details:
        value["details"] = details
    return value


@dataclass(slots=True)
class AgentOutput:
    status: AgentExecutionStatus
    summary: str
    updates: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    capabilities: dict[str, CapabilityStatus] = field(default_factory=dict)


class ClinicalAgent:
    name = "clinical_agent"
    critical = False
    records_completion = True

    def run(self, state: ClinicalState) -> AgentOutput:
        raise NotImplementedError

    def __call__(self, state: ClinicalState) -> dict[str, Any]:
        started = datetime.now(timezone.utc)
        timer = perf_counter()
        try:
            output = self.run(state)
        except Exception as exception:  # Agents convert failures into inspectable state.
            output = AgentOutput(
                status=AgentExecutionStatus.FAILED,
                summary=f"{self.name} failed safely",
                errors=[f"{type(exception).__name__}: {exception}"],
                updates={
                    "workflow_halted": self.critical,
                    **({"workflow_status": "FAILED"} if self.critical else {}),
                },
            )

        completed = datetime.now(timezone.utc)
        trace = {
            "agent": self.name,
            "status": output.status.value,
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
            "duration_ms": round((perf_counter() - timer) * 1000, 3),
            "summary": output.summary,
            "warnings": output.warnings,
            "errors": output.errors,
        }
        if output.capabilities:
            trace["capability_status"] = output.capabilities

        updates = dict(output.updates)
        updates["warnings"] = [*state.get("warnings", []), *output.warnings]
        updates["errors"] = [*state.get("errors", []), *output.errors]
        updates["capability_status"] = {
            **state.get("capability_status", {}),
            **output.capabilities,
        }
        updates["agent_trace"] = [*state.get("agent_trace", []), trace]
        if self.records_completion:
            updates["completed_agents"] = list(
                dict.fromkeys([*state.get("completed_agents", []), self.name])
            )
        return updates
