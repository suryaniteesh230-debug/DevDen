from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agents.contracts import (
    AgentExecutionStatus,
    AgentOutput,
    CapabilityAvailability,
    ClinicalAgent,
    capability,
)
from app.agents.reasoning_tools import (
    ClinicalReasoningToolRegistry,
    ReasoningToolError,
    result_references,
)
from app.clinical_reasoning.payloads import build_phi_minimized_reasoning_payload
from app.clinical_reasoning.schemas import (
    REASONING_SCHEMA_VERSION,
    ClinicalReasoningOutput,
    ReasoningToolTrace,
)
from app.core.config import get_settings
from app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponseError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from app.llm.gemini_provider import get_gemini_provider
from app.services.clinical_reasoning import ClinicalReasoningPersistenceService
from app.workflows.clinical_state import ClinicalState


AGENT_VERSION = "clinical-reasoning-agent-1.0.0"
SYSTEM_PROMPT = """You are a clinical decision-support reasoning specialist for suspected acute coronary syndrome. You do not diagnose, prescribe, or issue treatment orders. Use only the five local tools supplied. Select tools dynamically according to the PHI-minimized current state; do not call every tool by default. Each tool call must include a concise purpose. Retrieved evidence and graph edges are local, curated, limited, and not comprehensive. Distinguish association from causation. Use LOW/MODERATE/HIGH qualitative support only; never invent a numeric disease probability. The deterministic cardiac-model probability may be acknowledged only as model output, never as diagnostic certainty. Important guideline-supported considerations require source or chunk references. Identify genuinely missing data. Return only the requested structured object and never reveal private chain-of-thought."""


RegistryFactory = Callable[[str, str], ClinicalReasoningToolRegistry]


class ClinicalReasoningAgent(ClinicalAgent):
    name = "clinical_reasoning"

    def __init__(
        self,
        session: Session,
        *,
        provider: LLMProvider | None = None,
        registry_factory: RegistryFactory | None = None,
        max_steps: int | None = None,
        max_tool_calls: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.session = session
        self.provider = provider or get_gemini_provider()
        self.registry_factory = registry_factory or (
            lambda patient_id, encounter_id: ClinicalReasoningToolRegistry(
                session,
                patient_id=patient_id,
                encounter_id=encounter_id,
            )
        )
        self.max_steps = max_steps or settings.clinical_reasoning_max_steps
        self.max_tool_calls = max_tool_calls or settings.clinical_reasoning_max_tool_calls
        self.timeout_seconds = timeout_seconds or settings.clinical_reasoning_timeout_seconds
        self.persistence = ClinicalReasoningPersistenceService(session)

    def _persist_failure(
        self,
        state: ClinicalState,
        *,
        status: str,
        termination_reason: str,
        reason: str,
        trace: list[dict[str, Any]],
        latency_ms: float,
        provider_latency_ms: float,
    ) -> dict[str, Any]:
        row = self.persistence.persist(
            encounter_id=state["encounter_id"],
            workflow_id=state["workflow_id"],
            agent_name=self.name,
            agent_version=AGENT_VERSION,
            provider=self.provider.provider_name,
            model=self.provider.model,
            schema_version=REASONING_SCHEMA_VERSION,
            summary=reason,
            structured_output={},
            retrieved_source_ids=[],
            knowledge_graph_evidence=[],
            tool_call_trace=trace,
            termination_reason=termination_reason,
            latency_ms=latency_ms,
        )
        return {
            "status": status,
            "reason": reason,
            "result_id": row.id,
            "provider": self.provider.provider_name,
            "model": self.provider.model,
            "agent_version": AGENT_VERSION,
            "schema_version": REASONING_SCHEMA_VERSION,
            "termination_reason": termination_reason,
            "tool_boundary": list(
                (
                    "get_patient_history",
                    "get_current_vitals",
                    "get_current_labs",
                    "retrieve_clinical_guidelines",
                    "query_medical_knowledge_graph",
                )
            ),
            "tool_calls": trace,
            "provider_latency_ms": round(provider_latency_ms, 3),
            "latency_ms": latency_ms,
            "created_at": row.created_at.isoformat(),
        }

    def run(self, state: ClinicalState) -> AgentOutput:
        timer = perf_counter()
        if not self.provider.available:
            latency = round((perf_counter() - timer) * 1000, 3)
            reason = "Gemini clinical reasoning is unavailable because GEMINI_API_KEY is not configured"
            value = self._persist_failure(
                state,
                status="PENDING_CAPABILITY",
                termination_reason="PROVIDER_UNAVAILABLE",
                reason=reason,
                trace=[],
                latency_ms=latency,
                provider_latency_ms=0,
            )
            return AgentOutput(
                status=AgentExecutionStatus.PENDING_CAPABILITY,
                summary=reason,
                updates={"clinical_reasoning": value},
                capabilities={
                    "gemini_reasoning": capability(
                        CapabilityAvailability.PENDING_CAPABILITY, reason
                    ),
                    "rag": capability(
                        CapabilityAvailability.AVAILABLE,
                        "The local retriever remains independent of cloud availability",
                    ),
                    "medical_knowledge_graph": capability(
                        CapabilityAvailability.AVAILABLE,
                        "The local source-backed graph remains independent of cloud availability",
                    ),
                },
            )

        registry = self.registry_factory(state["patient_id"], state["encounter_id"])
        payload = build_phi_minimized_reasoning_payload(state)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(payload, separators=(",", ":"), sort_keys=True),
            },
        ]
        trace: list[dict[str, Any]] = []
        seen_calls: set[str] = set()
        rag_results: list[dict[str, Any]] = []
        kg_results: list[dict[str, Any]] = []
        provider_latency_ms = 0.0
        termination_reason = "MAX_STEPS"
        structured: ClinicalReasoningOutput | None = None
        failure_reason: str | None = None

        try:
            for _reasoning_step in range(1, self.max_steps + 1):
                elapsed = perf_counter() - timer
                if elapsed >= self.timeout_seconds:
                    termination_reason = "TIMEOUT"
                    failure_reason = "Clinical reasoning exceeded its total time limit"
                    break
                turn = self.provider.generate_with_tools(
                    messages=messages,
                    tools=registry.definitions(),
                    output_schema=ClinicalReasoningOutput,
                    timeout_seconds=max(0.1, self.timeout_seconds - elapsed),
                )
                provider_latency_ms += turn.latency_ms
                if turn.model != self.provider.model:
                    raise LLMProviderError("Provider model changed during the encounter")
                messages.append(turn.assistant_message)
                if not turn.tool_calls:
                    if isinstance(turn.structured_output, ClinicalReasoningOutput):
                        # Provider-neutral test/local implementations may return
                        # a validated final object directly.
                        structured = turn.structured_output
                        termination_reason = "COMPLETE"
                    elif _reasoning_step >= self.max_steps:
                        termination_reason = "MAX_STEPS"
                        failure_reason = "No reasoning step remained for structured synthesis"
                    else:
                        synthesis_messages = [
                            *messages,
                            {
                                "role": "user",
                                "content": (
                                    "Using only the clinical state and tool evidence above, "
                                    "produce the final validated clinical decision-support object."
                                ),
                            },
                        ]
                        synthesis = self.provider.generate_structured(
                            messages=synthesis_messages,
                            output_schema=ClinicalReasoningOutput,
                            timeout_seconds=max(
                                0.1,
                                self.timeout_seconds - (perf_counter() - timer),
                            ),
                        )
                        provider_latency_ms += synthesis.latency_ms
                        if synthesis.model != self.provider.model:
                            raise LLMProviderError(
                                "Provider model changed during the encounter"
                            )
                        if not isinstance(
                            synthesis.structured_output, ClinicalReasoningOutput
                        ):
                            termination_reason = "INVALID_OUTPUT"
                            failure_reason = (
                                "Provider did not return a validated reasoning object"
                            )
                        else:
                            structured = synthesis.structured_output
                            termination_reason = "COMPLETE"
                    break

                stop_loop = False
                for call in turn.tool_calls:
                    purpose = str(call.arguments.get("purpose", "Obtain relevant evidence"))[:240]
                    signature_arguments = {
                        key: value for key, value in call.arguments.items() if key != "purpose"
                    }
                    signature = f"{call.name}:{json.dumps(signature_arguments, sort_keys=True)}"
                    if signature in seen_calls:
                        trace.append(
                            ReasoningToolTrace(
                                step=len(trace) + 1,
                                tool=call.name,
                                purpose=purpose,
                                status="DUPLICATE_BLOCKED",
                                result_references=[],
                                latency_ms=0,
                            ).model_dump(mode="json")
                        )
                        termination_reason = "DUPLICATE_TOOL_CALL"
                        failure_reason = "Repeated identical tool call was blocked"
                        stop_loop = True
                        break
                    if len(trace) >= self.max_tool_calls:
                        termination_reason = "MAX_TOOL_CALLS"
                        failure_reason = "Clinical reasoning reached the maximum tool-call limit"
                        stop_loop = True
                        break
                    seen_calls.add(signature)
                    tool_timer = perf_counter()
                    try:
                        tool_result = registry.execute(call.name, call.arguments)
                        status = str(tool_result.get("status", "SUCCESS"))
                    except ReasoningToolError:
                        tool_result = {"status": "REJECTED", "reason": "Tool call was rejected"}
                        status = "REJECTED"
                    except Exception:
                        # Local failures are visible by category only; database or
                        # infrastructure exception text is not sent to Gemini.
                        tool_result = {
                            "status": "FAILED",
                            "reason": f"Approved tool '{call.name}' failed locally",
                        }
                        status = "FAILED"
                    latency = round((perf_counter() - tool_timer) * 1000, 3)
                    refs = result_references(tool_result)
                    trace.append(
                        ReasoningToolTrace(
                            step=len(trace) + 1,
                            tool=call.name,
                            purpose=purpose,
                            status=status,
                            result_references=refs,
                            latency_ms=latency,
                        ).model_dump(mode="json")
                    )
                    if call.name == "retrieve_clinical_guidelines":
                        rag_results.extend(tool_result.get("results", []))
                    elif call.name == "query_medical_knowledge_graph":
                        kg_results.extend(tool_result.get("results", []))
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": json.dumps(tool_result, separators=(",", ":")),
                        }
                    )
                if stop_loop:
                    break
        except LLMProviderUnavailableError:
            termination_reason = "PROVIDER_UNAVAILABLE"
            failure_reason = "Gemini provider became unavailable"
        except LLMTimeoutError:
            termination_reason = "PROVIDER_TIMEOUT"
            failure_reason = "Gemini request timed out"
        except LLMRateLimitError as exception:
            termination_reason = "PROVIDER_RATE_LIMITED"
            failure_reason = str(exception)
        except LLMStructuredOutputError:
            termination_reason = "INVALID_OUTPUT"
            failure_reason = "Gemini structured output failed validation"
        except LLMResponseError:
            termination_reason = "INVALID_OUTPUT"
            failure_reason = "Gemini returned an invalid response"
        except LLMProviderError as exception:
            termination_reason = "PROVIDER_FAILURE"
            failure_reason = str(exception)

        latency_ms = round((perf_counter() - timer) * 1000, 3)
        if structured is None:
            reason = failure_reason or "Clinical reasoning stopped before structured synthesis"
            value = self._persist_failure(
                state,
                status="PARTIAL",
                termination_reason=termination_reason,
                reason=reason,
                trace=trace,
                latency_ms=latency_ms,
                provider_latency_ms=provider_latency_ms,
            )
            return AgentOutput(
                status=AgentExecutionStatus.PARTIAL,
                summary=f"Clinical reasoning ended safely: {termination_reason}",
                updates={"clinical_reasoning": value},
                warnings=[reason],
                capabilities=self._capabilities(registry, available=False, reason=reason),
            )

        actual_rag = [
            {
                "source_id": item["source_id"],
                "chunk_id": item["chunk_id"],
                "relevance": item["retrieval_score"],
            }
            for item in rag_results[:24]
        ]
        actual_kg = [
            {
                "edge_id": item["edge_id"],
                "source_concept": item["source_concept"],
                "relationship": item["relationship"],
                "target_concept": item["target_concept"],
                "source_id": item["provenance"]["source_id"],
                "relevance": item["relevance"],
            }
            for item in kg_results[:24]
        ]
        structured = ClinicalReasoningOutput.model_validate(
            {
                **structured.model_dump(mode="json"),
                "tool_calls": trace,
                "clinical_evidence": actual_rag,
                "knowledge_graph_evidence": actual_kg,
            }
        )
        structured_dump = structured.model_dump(mode="json")
        available_refs = set()
        for entry in trace:
            available_refs.update(entry["result_references"])
        cardiac = state.get("cardiac_risk") or {}
        triage = state.get("triage") or {}
        if cardiac.get("model_version"):
            available_refs.add(f"CARDIAC-MODEL:{cardiac['model_version']}")
        if triage.get("policy_version"):
            available_refs.add(f"TRIAGE:{triage['policy_version']}")
        retrieved_sources = [item["source_id"] for item in actual_rag]
        retrieved_sources.extend(item["source_id"] for item in actual_kg)
        available_refs.update(retrieved_sources)
        row = self.persistence.persist(
            encounter_id=state["encounter_id"],
            workflow_id=state["workflow_id"],
            agent_name=self.name,
            agent_version=AGENT_VERSION,
            provider=self.provider.provider_name,
            model=self.provider.model,
            schema_version=REASONING_SCHEMA_VERSION,
            summary=structured.summary,
            structured_output=structured_dump,
            retrieved_source_ids=retrieved_sources,
            knowledge_graph_evidence=actual_kg,
            tool_call_trace=trace,
            termination_reason=termination_reason,
            latency_ms=latency_ms,
        )
        missing = list(state.get("missing_information", []))
        missing.extend(
            f"clinical_reasoning:{item}"
            for item in structured.important_missing_information
        )
        value = {
            "status": "SUCCESS",
            "result_id": row.id,
            "provider": self.provider.provider_name,
            "model": self.provider.model,
            "agent_version": AGENT_VERSION,
            "schema_version": REASONING_SCHEMA_VERSION,
            "termination_reason": termination_reason,
            "provider_latency_ms": round(provider_latency_ms, 3),
            "latency_ms": latency_ms,
            "retrieved_source_ids": list(dict.fromkeys(retrieved_sources)),
            "available_evidence_refs": sorted(available_refs),
            "created_at": row.created_at.isoformat(),
            **structured_dump,
        }
        return AgentOutput(
            status=AgentExecutionStatus.SUCCESS,
            summary="Generated and persisted evidence-backed structured clinical reasoning",
            updates={
                "clinical_reasoning": value,
                "missing_information": list(dict.fromkeys(missing)),
            },
            capabilities=self._capabilities(registry, available=True, reason="Completed"),
        )

    def _capabilities(
        self,
        registry: ClinicalReasoningToolRegistry,
        *,
        available: bool,
        reason: str,
    ) -> dict[str, Any]:
        provider_status = (
            CapabilityAvailability.AVAILABLE
            if available
            else CapabilityAvailability.PARTIAL
        )
        return {
            "gemini_reasoning": capability(
                provider_status,
                reason,
                provider=self.provider.provider_name,
                model=self.provider.model,
            ),
            "rag": capability(
                CapabilityAvailability.AVAILABLE,
                "Local clinical retrieval is available",
                **registry.retriever.index_metadata,
            ),
            "medical_knowledge_graph": capability(
                CapabilityAvailability.AVAILABLE,
                "Local source-backed medical graph is available",
                **registry.knowledge_graph.metadata,
            ),
            "differential_reasoning": capability(provider_status, reason),
            "clinical_pathways": capability(
                provider_status,
                "Guideline-supported considerations only; no autonomous orders",
            ),
        }
