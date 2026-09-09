from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from sahayi_api.config import get_settings
from sahayi_api.agent import AgentRuntime, AssistantTurnRequest, AssistantTurnResponse, run_assistant_turn
from sahayi_api.assistance import (
    ChecklistRequest,
    PersonalizedChecklist,
    SyntheticFormAssistance,
    SyntheticFormRequest,
    build_personalized_checklist,
    prepare_synthetic_form_assistance,
)
from sahayi_api.procedures import (
    PackLoadError,
    ProcedureDetail,
    ProcedureListResponse,
    SupportedLocale,
    default_pack_root,
    detail_procedure,
    load_procedure_registry,
    summarize_procedure,
    translation_info,
)
from sahayi_api.readiness import (
    ReadinessEvaluationRequest,
    ReadinessEvaluationResponse,
    ReadinessInputError,
    evaluate_readiness,
)
from sahayi_api.orchestration import ConversationTurnRequest, ConversationTurnResponse, run_conversation_turn
from sahayi_api.simulation import (
    DemoJourneyResponse,
    DemoStatusRequest,
    DemoSubmissionRequest,
    get_demo_status,
    start_demo_submission,
)

settings = get_settings()
agent_runtime = AgentRuntime(settings)
app = FastAPI(title="Sahayi API", docs_url=None, redoc_url=None, openapi_url=None)

try:
    procedure_registry = load_procedure_registry(default_pack_root())
except PackLoadError:
    procedure_registry = None


@app.middleware("http")
async def privacy_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def exact_development_cors(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method == "OPTIONS" and request.url.path.startswith("/api/v1/"):
        if origin != settings.dev_frontend_origin:
            return JSONResponse({"error": "Request not allowed"}, status_code=403)
        return JSONResponse({}, headers={"Access-Control-Allow-Origin": settings.dev_frontend_origin, "Access-Control-Allow-Methods": "GET, POST", "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin"})
    response = await call_next(request)
    if origin == settings.dev_frontend_origin and request.url.path.startswith("/api/v1/"):
        response.headers["Access-Control-Allow-Origin"] = settings.dev_frontend_origin
        response.headers["Vary"] = "Origin"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse({"error": "Request not found" if exc.status_code == 404 else "Request failed"}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse({"error": "Invalid request"}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse({"error": "Internal server error"}, status_code=500)


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/public-config")
async def public_config() -> dict[str, str | bool | int]:
    warning = min(settings.kiosk_warning_seconds, settings.kiosk_inactivity_seconds - 10)
    return {
        "application_name": "Sahayi",
        "kiosk_mode": True,
        "agent_available": agent_runtime.available,
        "agent_provider": settings.agent_provider,
        "agent_model": settings.agent_model,
        "inactivity_timeout_seconds": settings.kiosk_inactivity_seconds,
        "inactivity_warning_seconds": warning,
    }


@app.get("/api/v1/procedures", response_model=ProcedureListResponse)
async def procedures(locale: SupportedLocale = "en") -> ProcedureListResponse | JSONResponse:
    if procedure_registry is None:
        return JSONResponse({"error": "Procedure guidance is unavailable"}, status_code=503)
    loaded_items = [loaded for _, loaded in sorted(procedure_registry.items())]
    summaries = [summarize_procedure(loaded, locale=locale) for loaded in loaded_items]
    return ProcedureListResponse(locale=locale, translation=translation_info(loaded_items[0].pack, locale), procedures=summaries)


@app.get("/api/v1/procedures/{service_id}", response_model=ProcedureDetail)
async def procedure_detail(service_id: str, locale: SupportedLocale = "en") -> ProcedureDetail | JSONResponse:
    if procedure_registry is None:
        return JSONResponse({"error": "Procedure guidance is unavailable"}, status_code=503)
    loaded = procedure_registry.get(service_id)
    if loaded is None:
        return JSONResponse({"error": "Procedure not found"}, status_code=404)
    return detail_procedure(loaded, locale=locale)


@app.post("/api/v1/procedures/{service_id}/readiness/evaluate", response_model=ReadinessEvaluationResponse)
async def readiness_evaluate(
    service_id: str,
    request: ReadinessEvaluationRequest,
    locale: SupportedLocale = "en",
) -> ReadinessEvaluationResponse | JSONResponse:
    if procedure_registry is None:
        return JSONResponse({"error": "Procedure guidance is unavailable"}, status_code=503)
    loaded = procedure_registry.get(service_id)
    if loaded is None:
        return JSONResponse({"error": "Procedure not found"}, status_code=404)
    try:
        return evaluate_readiness(loaded, request.answers, locale=locale)
    except ReadinessInputError:
        return JSONResponse({"error": "Invalid readiness answers"}, status_code=422)


@app.post("/api/v1/procedures/{service_id}/checklist", response_model=PersonalizedChecklist)
async def personalized_checklist(
    service_id: str,
    request: ChecklistRequest,
    locale: SupportedLocale = "en",
) -> PersonalizedChecklist | JSONResponse:
    if procedure_registry is None:
        return JSONResponse({"error": "Procedure guidance is unavailable"}, status_code=503)
    loaded = procedure_registry.get(service_id)
    if loaded is None:
        return JSONResponse({"error": "Procedure not found"}, status_code=404)
    try:
        return build_personalized_checklist(loaded, request.answers, locale=locale)
    except ReadinessInputError:
        return JSONResponse({"error": "Invalid readiness answers"}, status_code=422)


@app.post("/api/v1/procedures/{service_id}/synthetic-form-assistance", response_model=SyntheticFormAssistance)
async def synthetic_form_assistance(
    service_id: str,
    request: SyntheticFormRequest,
    locale: SupportedLocale = "en",
) -> SyntheticFormAssistance | JSONResponse:
    if procedure_registry is None:
        return JSONResponse({"error": "Procedure guidance is unavailable"}, status_code=503)
    loaded = procedure_registry.get(service_id)
    if loaded is None:
        return JSONResponse({"error": "Procedure not found"}, status_code=404)
    try:
        return prepare_synthetic_form_assistance(loaded, request.persona_id, locale=locale)
    except ValueError:
        return JSONResponse({"error": "Invalid synthetic form request"}, status_code=422)


@app.post("/api/v1/procedures/{service_id}/demo-submission", response_model=DemoJourneyResponse)
async def demo_submission(
    service_id: str,
    request: DemoSubmissionRequest,
    locale: SupportedLocale = "en",
) -> DemoJourneyResponse | JSONResponse:
    if procedure_registry is None:
        return JSONResponse({"error": "Procedure guidance is unavailable"}, status_code=503)
    loaded = procedure_registry.get(service_id)
    if loaded is None:
        return JSONResponse({"error": "Procedure not found"}, status_code=404)
    try:
        return start_demo_submission(loaded, request, locale=locale)
    except ValueError:
        return JSONResponse({"error": "Invalid demo submission request"}, status_code=422)


@app.post("/api/v1/procedures/{service_id}/demo-status", response_model=DemoJourneyResponse)
async def demo_status(
    service_id: str,
    request: DemoStatusRequest,
    locale: SupportedLocale = "en",
) -> DemoJourneyResponse | JSONResponse:
    if procedure_registry is None:
        return JSONResponse({"error": "Procedure guidance is unavailable"}, status_code=503)
    loaded = procedure_registry.get(service_id)
    if loaded is None:
        return JSONResponse({"error": "Procedure not found"}, status_code=404)
    try:
        return get_demo_status(loaded, request, locale=locale)
    except ValueError:
        return JSONResponse({"error": "Invalid demo status request"}, status_code=422)


@app.post("/api/v1/assistant/turn", response_model=AssistantTurnResponse)
async def assistant_turn(request: Request, turn: AssistantTurnRequest) -> AssistantTurnResponse | JSONResponse:
    if procedure_registry is None:
        return JSONResponse({"error": "Procedure guidance is unavailable"}, status_code=503)
    address = request.client.host if request.client is not None else "unknown"
    return await run_assistant_turn(turn, procedure_registry, agent_runtime, address)


@app.post("/api/v1/conversation/turn", response_model=ConversationTurnResponse)
async def conversation_turn(request: Request, turn: ConversationTurnRequest) -> ConversationTurnResponse | JSONResponse:
    if procedure_registry is None:
        return JSONResponse({"error": "Procedure guidance is unavailable"}, status_code=503)
    address = request.client.host if request.client is not None else "unknown"
    return await run_conversation_turn(turn, procedure_registry, agent_runtime, address)


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/")
    async def kiosk_index() -> FileResponse:
        return FileResponse(frontend_dist / "index.html")

    @app.get("/{path:path}")
    async def kiosk_fallback(path: str) -> FileResponse:
        requested = frontend_dist / path
        if path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(frontend_dist / "index.html")
