from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.clinical_agents import (
    ClinicalNlpAgent,
    ClinicalReasoningAgent,
    DataFusionAgent,
    IntakeAgent,
    MultimodalAgent,
    PatientResolutionAgent,
    PriorityAgent,
    SafetyAgent,
    TriageRiskAgent,
    XaiAgent,
)
from app.agents.supervisor import SupervisorAction, SupervisorAgent
from app.workflows.clinical_state import ClinicalState


def route_supervisor_decision(state: ClinicalState) -> str:
    """Translate the Supervisor's state decision into a graph branch."""

    return state.get("next_action") or SupervisorAction.FINISH.value


def build_clinical_graph(
    session: Session,
    *,
    supervisor: SupervisorAgent | None = None,
    clinical_reasoning_agent: ClinicalReasoningAgent | None = None,
) -> Any:
    """Compile the Supervisor-routed Phase 1 clinical assessment graph."""

    builder = StateGraph(ClinicalState)
    builder.add_node("intake", IntakeAgent(session))
    builder.add_node("supervisor", supervisor or SupervisorAgent())
    builder.add_node("patient_resolution", PatientResolutionAgent(session))
    builder.add_node("multimodal", MultimodalAgent(session))
    builder.add_node("clinical_nlp", ClinicalNlpAgent())
    builder.add_node("data_fusion", DataFusionAgent())
    builder.add_node("triage_risk", TriageRiskAgent(session))
    builder.add_node(
        "clinical_reasoning", clinical_reasoning_agent or ClinicalReasoningAgent(session)
    )
    builder.add_node("priority", PriorityAgent(session))
    builder.add_node("safety", SafetyAgent())
    builder.add_node("xai", XaiAgent(session))

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_supervisor_decision,
        {
            SupervisorAction.PATIENT_RESOLUTION.value: "patient_resolution",
            SupervisorAction.MULTIMODAL.value: "multimodal",
            SupervisorAction.CLINICAL_NLP.value: "clinical_nlp",
            SupervisorAction.DATA_FUSION.value: "data_fusion",
            SupervisorAction.TRIAGE_RISK.value: "triage_risk",
            SupervisorAction.CLINICAL_REASONING.value: "clinical_reasoning",
            SupervisorAction.SAFETY.value: "safety",
            SupervisorAction.XAI.value: "xai",
            SupervisorAction.PRIORITY.value: "priority",
            SupervisorAction.FINISH.value: END,
        },
    )
    for specialist in (
        "patient_resolution",
        "multimodal",
        "clinical_nlp",
        "data_fusion",
        "triage_risk",
        "clinical_reasoning",
        "safety",
        "xai",
        "priority",
    ):
        builder.add_edge(specialist, "supervisor")
    return builder.compile()
