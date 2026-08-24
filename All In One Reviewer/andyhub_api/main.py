"""Versioned FastAPI application for the AndyHub Phase 2 parity surface."""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import time
from typing import AsyncIterator, Callable
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from generator import GenerationDependencies, default_generation_dependencies
from rag_engine import initialize_course_memory

from .persistence import ApiRepository
from .schemas import (
    DeckDetail,
    DeckSummary,
    GenerationJob,
    GenerationRequest,
    GradeResult,
    ModuleItem,
    ModuleList,
    QuizSession,
    QuizSessionRequest,
    RevealResult,
    SessionSummary,
    SubmitAnswer,
)
from .services import ALLOWED_UPLOADS, DeckService, GenerationService, ModuleService, QuizService
from .settings import Settings
from .structured_logging import configure_logging, log_event


LOGGER = logging.getLogger("andyhub.api")


def create_app(
    settings: Settings | None = None,
    *,
    dependencies_factory: Callable[[], GenerationDependencies] = default_generation_dependencies,
) -> FastAPI:
    configure_logging()
    settings = settings or Settings.defaults()
    repository = ApiRepository(settings.database_path)
    module_service = ModuleService(settings, repository)
    deck_service = DeckService(settings.database_path)
    generation_service = GenerationService(settings, repository, dependencies_factory)
    quiz_service = QuizService(repository, settings.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.course_memory_status = "ok"
        if settings.initialize_course_memory:
            try:
                initialize_course_memory(settings.resolved_course_memory_directory)
            except Exception:
                app.state.course_memory_status = "unavailable"
        if settings.start_generation_worker:
            generation_service.start()
        try:
            yield
        finally:
            if settings.start_generation_worker:
                generation_service.stop()

    app = FastAPI(title="AndyHub API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.generation_service = generation_service

    @app.middleware("http")
    async def structured_request_log(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            log_event(
                LOGGER,
                "http_request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status=500,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code=type(exc).__name__,
            )
            raise
        response.headers["x-request-id"] = request_id
        log_event(
            LOGGER,
            "http_request_completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "request_error", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "Request validation failed", "details": exc.errors()}})

    @app.get("/api/v1/health")
    def health() -> JSONResponse:
        database_status = "ok" if repository.ping() else "unavailable"
        course_memory_status = getattr(app.state, "course_memory_status", "ok")
        generator_status = "configured" if _groq_is_configured() else "unconfigured"
        status = (
            "ok"
            if database_status == "ok"
            and course_memory_status == "ok"
            and generator_status == "configured"
            else "degraded"
        )
        return JSONResponse(
            status_code=200 if status == "ok" else 503,
            content={
                "status": status,
                "service": "api",
                "database": database_status,
                "course_memory": course_memory_status,
                "generator": generator_status,
                "worker_mode": "embedded" if settings.start_generation_worker else "external",
            },
        )

    @app.get("/api/v1/capabilities")
    def capabilities() -> dict[str, object]:
        return {"file_types": list(ALLOWED_UPLOADS.values()), "max_upload_bytes": settings.max_upload_bytes, "question_styles": ["multiple_choice", "enumeration", "problem", "mixed"], "features": {"sse_generation_progress": True, "durable_quiz_sessions": True}}

    @app.get("/api/v1/modules", response_model=ModuleList)
    def list_modules() -> ModuleList:
        return ModuleList(items=module_service.list())

    @app.post("/api/v1/modules", status_code=201, response_model=ModuleList)
    async def upload_modules(files: list[UploadFile] = File(...)) -> ModuleList:
        if not files:
            raise HTTPException(status_code=422, detail={"code": "no_files", "message": "At least one file is required"})
        return ModuleList(items=[await module_service.store(upload) for upload in files])

    @app.get("/api/v1/decks", response_model=list[DeckSummary])
    def list_decks(subject: str | None = None, search: str | None = None, limit: int = Query(default=50, ge=1, le=100)) -> list[DeckSummary]:
        return deck_service.list(subject, search, limit)

    @app.get("/api/v1/decks/{deck_id}", response_model=DeckDetail)
    def get_deck(deck_id: int, include: str | None = None) -> DeckDetail:
        return deck_service.get(deck_id, include_cards=include == "cards")

    @app.post("/api/v1/generation-jobs", status_code=202, response_model=GenerationJob)
    def create_generation_job(request: GenerationRequest) -> GenerationJob:
        return generation_service.submit(request)

    @app.get("/api/v1/generation-jobs/{job_id}", response_model=GenerationJob)
    def get_generation_job(job_id: str) -> GenerationJob:
        return generation_service.job(job_id)

    @app.get("/api/v1/generation-jobs/{job_id}/events")
    async def generation_events(job_id: str) -> StreamingResponse:
        generation_service.job(job_id)

        async def stream() -> AsyncIterator[str]:
            last = None
            while True:
                job = generation_service.job(job_id).model_dump(mode="json", by_alias=True)
                payload = json.dumps(job, separators=(",", ":"))
                if payload != last:
                    yield f"event: progress\ndata: {payload}\n\n"
                    last = payload
                if job["status"] in {"complete", "failed"}:
                    break
                import asyncio
                await asyncio.sleep(0.1)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/v1/quiz-sessions", response_model=QuizSession)
    def create_quiz_session(request: QuizSessionRequest) -> QuizSession:
        return quiz_service.create(request.deck_id, request.mode)

    @app.get("/api/v1/quiz-sessions/{session_id}", response_model=QuizSession)
    def get_quiz_session(session_id: str) -> QuizSession:
        return quiz_service.get(session_id)

    @app.post("/api/v1/quiz-sessions/{session_id}/answers", response_model=GradeResult)
    def submit_answer(session_id: str, request: SubmitAnswer) -> GradeResult:
        return quiz_service.grade(session_id, request.card_id, request.answer.type, request.answer.value)

    @app.post("/api/v1/quiz-sessions/{session_id}/cards/{card_id}/reveal-solution", response_model=RevealResult)
    def reveal_solution(session_id: str, card_id: int) -> RevealResult:
        return quiz_service.reveal(session_id, card_id)

    @app.post("/api/v1/quiz-sessions/{session_id}/advance", response_model=QuizSession)
    def advance_session(session_id: str) -> QuizSession:
        return quiz_service.advance(session_id)

    @app.get("/api/v1/quiz-sessions/{session_id}/summary", response_model=SessionSummary)
    def session_summary(session_id: str) -> SessionSummary:
        return quiz_service.summary(session_id)

    return app


def _groq_is_configured() -> bool:
    if os.environ.get("GROQ_API_KEY", "").strip():
        return True
    secret_file = os.environ.get("GROQ_API_KEY_FILE", "").strip()
    if secret_file:
        try:
            return bool(Path(secret_file).read_text(encoding="utf-8").strip())
        except OSError:
            return False
    return False


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
