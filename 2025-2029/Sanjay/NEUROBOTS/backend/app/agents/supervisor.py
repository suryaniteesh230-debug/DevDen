from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.agents.contracts import AgentExecutionStatus, AgentOutput, ClinicalAgent
from app.workflows.clinical_state import ClinicalState


class SupervisorAction(StrEnum):
    PATIENT_RESOLUTION = "PATIENT_RESOLUTION"
    MULTIMODAL = "MULTIMODAL"
    CLINICAL_NLP = "CLINICAL_NLP"
    DATA_FUSION = "DATA_FUSION"
    TRIAGE_RISK = "TRIAGE_RISK"
    CLINICAL_REASONING = "CLINICAL_REASONING"
    SAFETY = "SAFETY"
    XAI = "XAI"
    PRIORITY = "PRIORITY"
    FINISH = "FINISH"


@dataclass(frozen=True, slots=True)
class SupervisorDecision:
    action: SupervisorAction
    reason: str
    workflow_status: str = "RUNNING"
    warning: str | None = None
    error: str | None = None


class DeterministicSupervisorPolicy:
    """State-based policy that can later be augmented or replaced by an LLM."""

    max_decisions = 12
    _specialist_order = (
        ("patient_resolution", SupervisorAction.PATIENT_RESOLUTION),
        ("multimodal", SupervisorAction.MULTIMODAL),
        ("clinical_nlp", SupervisorAction.CLINICAL_NLP),
        ("data_fusion", SupervisorAction.DATA_FUSION),
        ("triage_risk", SupervisorAction.TRIAGE_RISK),
        ("clinical_reasoning", SupervisorAction.CLINICAL_REASONING),
        ("priority", SupervisorAction.PRIORITY),
        ("safety", SupervisorAction.SAFETY),
        ("xai", SupervisorAction.XAI),
    )

    def decide(self, state: ClinicalState) -> SupervisorDecision:
        if state.get("workflow_halted"):
            return SupervisorDecision(
                SupervisorAction.FINISH,
                "A critical upstream failure halted the workflow",
                workflow_status="FAILED",
            )

        decision_count = sum(
            entry.get("agent") == "supervisor" for entry in state.get("agent_trace", [])
        )
        if decision_count >= self.max_decisions:
            message = (
                f"Supervisor routing limit of {self.max_decisions} decisions was reached"
            )
            return SupervisorDecision(
                SupervisorAction.FINISH,
                message,
                workflow_status="FAILED",
                error=message,
            )

        completed = set(state.get("completed_agents", []))
        for agent_name, action in self._specialist_order:
            if agent_name not in completed:
                return SupervisorDecision(
                    action,
                    f"{agent_name} has not yet completed an execution attempt",
                )

        failed_agents = [
            entry.get("agent")
            for entry in state.get("agent_trace", [])
            if entry.get("status") == AgentExecutionStatus.FAILED.value
            and entry.get("agent") != "supervisor"
        ]
        status = "COMPLETED_WITH_WARNINGS" if failed_agents else "COMPLETED"
        warning = (
            f"Workflow completed with isolated failures: {', '.join(failed_agents)}"
            if failed_agents
            else None
        )
        return SupervisorDecision(
            SupervisorAction.FINISH,
            "All specialist agents have completed an execution attempt",
            workflow_status=status,
            warning=warning,
        )


class SupervisorAgent(ClinicalAgent):
    name = "supervisor"
    records_completion = False

    def __init__(self, policy: DeterministicSupervisorPolicy | None = None) -> None:
        self.policy = policy or DeterministicSupervisorPolicy()

    def run(self, state: ClinicalState) -> AgentOutput:
        decision = self.policy.decide(state)
        warnings = [decision.warning] if decision.warning else []
        errors = [decision.error] if decision.error else []
        return AgentOutput(
            status=(
                AgentExecutionStatus.FAILED
                if decision.workflow_status == "FAILED"
                else AgentExecutionStatus.SUCCESS
            ),
            summary=f"Selected {decision.action.value}: {decision.reason}",
            updates={
                "next_action": decision.action.value,
                "workflow_status": decision.workflow_status,
                "workflow_halted": decision.workflow_status == "FAILED",
            },
            warnings=warnings,
            errors=errors,
        )
