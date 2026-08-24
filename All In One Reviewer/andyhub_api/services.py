"""API orchestration services; extraction, prompts, and SQL remain outside routes."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import random
import re
import threading
import time
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from generator import (
    GenerationDependencies,
    _chunk_text,
    get_andy_prompt,
    persist_valid_cards,
    prepare_custom_deck,
    validate_generated_cards,
)
from grading import decode_card_options, grade_enumeration, grade_problem_answer, problem_payload
from repositories import Card, CardRepository, Deck, DeckRepository

from .persistence import ApiRepository, StoredModule
from .schemas import (
    DeckDetail,
    DeckReference,
    DeckSummary,
    EnumerationCard,
    GenerationJob,
    GenerationRequest,
    GradeResult,
    ModuleItem,
    MultipleChoiceCard,
    ProblemCard,
    QuizCard,
    QuizSession,
    RevealResult,
    SessionSummary,
)
from .settings import Settings
from .structured_logging import log_event


ALLOWED_UPLOADS = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

LOGGER = logging.getLogger("andyhub.jobs")


def _not_found(kind: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "not_found", "message": f"{kind} was not found"})


def safe_card(card: Card) -> QuizCard:
    if card.card_type == "multiple_choice":
        options = decode_card_options(card.options)
        return MultipleChoiceCard(id=card.id, type="multiple_choice", question=card.question, options=options if isinstance(options, list) else [])
    if card.card_type == "enumeration":
        items = decode_card_options(card.options)
        if not isinstance(items, list):
            items = decode_card_options(card.correct_answer)
        return EnumerationCard(id=card.id, type="enumeration", question=card.question, expected_count=len(items) if isinstance(items, list) else 0)
    if card.card_type == "problem":
        return ProblemCard(id=card.id, type="problem", question=card.question, answer_format_hint="Final answer (scalar/text auto-grading)")
    raise HTTPException(status_code=500, detail={"code": "unsupported_card", "message": "Stored card type is unsupported"})


class ModuleService:
    def __init__(self, settings: Settings, repository: ApiRepository) -> None:
        self.settings = settings
        self.repository = repository
        self.settings.uploads_directory.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[ModuleItem]:
        return [self._to_item(module) for module in self.repository.list_modules()]

    async def store(self, upload: UploadFile) -> ModuleItem:
        original = upload.filename or "module"
        filename = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(original).name).strip(". ")
        extension = Path(filename).suffix.lower()
        if not filename or extension not in ALLOWED_UPLOADS:
            raise HTTPException(status_code=415, detail={"code": "unsupported_file", "message": "Only PDF and PPTX modules are supported"})
        if upload.content_type and upload.content_type not in {ALLOWED_UPLOADS[extension], "application/octet-stream"}:
            raise HTTPException(status_code=415, detail={"code": "unsupported_media_type", "message": "Upload media type does not match its extension"})

        staging = self.settings.uploads_directory / f".{uuid4().hex}.upload"
        digest = hashlib.sha256()
        size = 0
        try:
            with staging.open("wb") as target:
                while block := await upload.read(1024 * 1024):
                    size += len(block)
                    if size > self.settings.max_upload_bytes:
                        raise HTTPException(status_code=413, detail={"code": "upload_too_large", "message": "Upload exceeds the configured size limit"})
                    digest.update(block)
                    target.write(block)
            content_hash = f"sha256:{digest.hexdigest()}"
            duplicate = self.repository.get_module_by_hash(content_hash)
            if duplicate:
                return self._to_item(duplicate, duplicate=True)
            stored_filename = f"{digest.hexdigest()}{extension}"
            staging.replace(self.settings.uploads_directory / stored_filename)
            module = self.repository.create_module(filename, stored_filename, ALLOWED_UPLOADS[extension], size, content_hash)
            return self._to_item(module)
        finally:
            await upload.close()
            staging.unlink(missing_ok=True)

    @staticmethod
    def _to_item(module: StoredModule, duplicate: bool = False) -> ModuleItem:
        return ModuleItem(
            id=module.id, filename=module.filename, media_type=module.media_type,
            size_bytes=module.size_bytes, content_hash=module.content_hash,
            extraction_status=module.extraction_status, duplicate=duplicate,
        )


class DeckService:
    def __init__(self, database_path: Path) -> None:
        self.decks = DeckRepository(database_path)
        self.cards = CardRepository(database_path)

    def list(self, subject: str | None = None, search: str | None = None, limit: int = 50) -> list[DeckSummary]:
        decks = self.decks.list()
        if subject:
            decks = [deck for deck in decks if deck.subject.casefold() == subject.casefold()]
        if search:
            needle = search.casefold()
            decks = [deck for deck in decks if needle in deck.name.casefold() or needle in deck.subject.casefold()]
        return [self._summary(deck) for deck in decks[:limit]]

    def get(self, deck_id: int, include_cards: bool = False) -> DeckDetail:
        deck = self.decks.get(deck_id)
        if not deck:
            raise _not_found("Deck")
        summary = self._summary(deck)
        return DeckDetail(**summary.model_dump(), cards=[safe_card(card) for card in self.cards.list_for_deck(deck.id)] if include_cards else None)

    def _summary(self, deck: Deck) -> DeckSummary:
        cards = self.cards.list_for_deck(deck.id)
        counts = {kind: sum(card.card_type == kind for card in cards) for kind in ("multiple_choice", "enumeration", "problem")}
        modules = [item.strip() for item in deck.modules_included.split(",") if item.strip()]
        return DeckSummary(id=deck.id, name=deck.name, subject=deck.subject, modules=modules, card_count=len(cards), question_types=counts, total_misses=sum(card.times_missed for card in cards))


class GenerationService:
    def __init__(self, settings: Settings, repository: ApiRepository, dependencies_factory: Callable[[], GenerationDependencies]) -> None:
        self.settings = settings
        self.repository = repository
        self.dependencies_factory = dependencies_factory
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def submit(self, request: GenerationRequest) -> GenerationJob:
        missing = [module_id for module_id in request.module_ids if not self.repository.get_module(module_id)]
        if missing:
            raise HTTPException(status_code=422, detail={"code": "unknown_modules", "message": "One or more module IDs do not exist", "details": {"module_ids": missing}})
        return self.job(self.repository.create_job(request))

    def job(self, job_id: str) -> GenerationJob:
        row = self.repository.get_job(job_id)
        if not row:
            raise _not_found("Generation job")
        return GenerationJob(**row)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="andyhub-generation-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def run_pending_once(self) -> bool:
        job = self.repository.claim_next_job()
        if not job:
            return False
        started = time.perf_counter()
        log_event(LOGGER, "generation_job_started", service="worker", job_id=job["id"])
        try:
            modules = [self.repository.get_module(module_id) for module_id in json.loads(job["module_ids"])]
            if any(module is None for module in modules):
                raise ValueError("A selected module no longer exists")
            resolved = [module for module in modules if module is not None]
            deps = self.dependencies_factory()
            self._update_job(job["id"], stage="extracting", progress=10, message="Extracting selected modules")
            preparation = prepare_custom_deck(
                [module.filename for module in resolved],
                extract_file=deps.extract_file,
                uploads_directory=str(self.settings.uploads_directory),
                report=lambda _: None,
            )
            if preparation is None:
                raise ValueError("No usable text was extracted from the selected modules")
            self._update_job(job["id"], stage="retrieving_memory", progress=25, message="Preparing subject memory")
            client = deps.create_client()
            raw_cards: list[dict] = []
            per_chunk = -(-job["total_questions"] // len(preparation.chunks))
            for index, chunk in enumerate(preparation.chunks, start=1):
                self._update_job(
                    job["id"], stage="generating", progress=25 + int(55 * (index - 1) / len(preparation.chunks)),
                    message=f"Generating questions from module chunk {index} of {len(preparation.chunks)}", cards_received=len(raw_cards),
                )
                raw_cards.extend(deps.query_cards(client, chunk + deps.get_context(chunk, job["subject"]), get_andy_prompt(per_chunk, job["question_style"])))
                if index < len(preparation.chunks):
                    deps.sleep(2)
            deps.add_memory(job["deck_name"], job["subject"], list(preparation.chunks))
            self._update_job(job["id"], stage="validating", progress=85, message="Validating generated cards", cards_received=len(raw_cards))
            valid_cards = validate_generated_cards(raw_cards, job["total_questions"])
            if not valid_cards:
                raise ValueError("The generator returned no valid cards")
            self._update_job(job["id"], stage="saving", progress=95, message="Saving deck", cards_valid=len(valid_cards))
            deck_id = persist_valid_cards(
                deck_name=job["deck_name"], subject=job["subject"], selected_files=preparation.selected_files,
                valid_cards=valid_cards, persist_deck=deps.persist_deck,
            )
            self._update_job(job["id"], status="complete", stage="complete", progress=100, message="Deck ready", cards_received=len(raw_cards), cards_valid=len(valid_cards), deck_id=deck_id)
            log_event(
                LOGGER,
                "generation_job_completed",
                service="worker",
                job_id=job["id"],
                stage="complete",
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                cards_received=len(raw_cards),
                cards_valid=len(valid_cards),
            )
        except Exception as exc:
            self._update_job(job["id"], status="failed", stage="failed", message="Generation failed", error=str(exc)[:500])
            log_event(
                LOGGER,
                "generation_job_failed",
                service="worker",
                job_id=job["id"],
                stage="failed",
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code=type(exc).__name__,
            )
        return True

    def _update_job(self, job_id: str, **fields: object) -> None:
        self.repository.update_job(job_id, **fields)
        safe_fields = {
            key: value
            for key, value in fields.items()
            if key
            in {
                "status",
                "stage",
                "progress",
                "cards_received",
                "cards_valid",
                "deck_id",
            }
        }
        log_event(
            LOGGER,
            "generation_job_progress",
            service="worker",
            job_id=job_id,
            **safe_fields,
        )

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            if not self.run_pending_once():
                self._stop.wait(0.1)


class QuizService:
    def __init__(self, repository: ApiRepository, database_path: Path) -> None:
        self.repository = repository
        self.decks = DeckRepository(database_path)
        self.cards = CardRepository(database_path)

    def create(self, deck_id: int, mode: str) -> QuizSession:
        deck = self.decks.get(deck_id)
        if not deck:
            raise _not_found("Deck")
        cards = self.cards.list_for_deck(deck_id)
        if mode == "missed":
            cards = [card for card in cards if card.times_missed > 0]
        random.SystemRandom().shuffle(cards)
        if not cards:
            raise HTTPException(status_code=422, detail={"code": "empty_session", "message": "No cards match this quiz mode"})
        return self._view(self.repository.create_session(deck_id, mode, [card.id for card in cards]))

    def get(self, session_id: str) -> QuizSession:
        return self._view(session_id)

    def grade(self, session_id: str, card_id: int, answer_type: str, value: str) -> GradeResult:
        session, card = self._current(session_id, card_id)
        if answer_type != card.card_type:
            raise HTTPException(status_code=422, detail={"code": "answer_type_mismatch", "message": "Answer type does not match the current card"})
        caught: list[str] | None = None
        missed: list[str] | None = None
        expected_answer: str | None = None
        steps: list[str] | None = None
        if card.card_type == "multiple_choice":
            correct = value == card.correct_answer
        elif card.card_type == "enumeration":
            expected = decode_card_options(card.options)
            if not isinstance(expected, list):
                expected = decode_card_options(card.correct_answer)
            caught, missed = grade_enumeration(value, expected if isinstance(expected, list) else [])
            correct = bool(expected) and not missed
        else:
            expected_answer, steps = problem_payload(decode_card_options(card.options), card.correct_answer)
            correct = grade_problem_answer(value, expected_answer)
        self.repository.record_attempt(session_id, card_id, correct)
        attempt = self.repository.attempt_for_current_card(session_id, card_id)
        complete = bool(attempt and (attempt["status"] == "correct" or attempt["revealed"]))
        if correct:
            feedback = "Correct."
        elif complete:
            feedback = "This card is already resolved; your earlier result stands."
        else:
            feedback = "Not correct yet; try again or reveal the worked solution."
        return GradeResult(
            correct=correct, complete=complete, feedback=feedback,
            caught_items=caught, missed_items=missed, expected_answer=expected_answer, solution_steps=steps if correct else None,
        )

    def reveal(self, session_id: str, card_id: int) -> RevealResult:
        _, card = self._current(session_id, card_id)
        if card.card_type != "problem":
            raise HTTPException(status_code=422, detail={"code": "reveal_not_available", "message": "Only problem cards have worked solutions"})
        answer, steps = problem_payload(decode_card_options(card.options), card.correct_answer)
        self.repository.record_attempt(session_id, card_id, False, revealed=True)
        return RevealResult(expected_answer=answer, solution_steps=steps)

    def advance(self, session_id: str) -> QuizSession:
        session = self.repository.get_session(session_id)
        if not session:
            raise _not_found("Quiz session")
        order = json.loads(session["card_order"])
        if session["current_index"] < len(order):
            attempt = self.repository.attempt_for_current_card(session_id, order[session["current_index"]])
            if not attempt or (attempt["status"] != "correct" and not attempt["revealed"]):
                raise HTTPException(status_code=409, detail={"code": "card_not_resolved", "message": "Answer correctly or reveal the solution before advancing"})
        self.repository.advance(session_id)
        return self._view(session_id)

    def summary(self, session_id: str) -> SessionSummary:
        data = self.repository.summary(session_id)
        attempts = data["attempts"]
        return SessionSummary(
            total_questions=len(json.loads(data["session"]["card_order"])), attempted=len(attempts),
            correct=sum(item["status"] == "correct" and not item["revealed"] for item in attempts),
            missed_card_ids=[item["card_id"] for item in attempts if item["wrong_count"] > 0],
            revealed_card_ids=[item["card_id"] for item in attempts if item["revealed"]],
            complete=bool(data["session"]["completed"]),
        )

    def _current(self, session_id: str, card_id: int) -> tuple[dict, Card]:
        session = self.repository.get_session(session_id)
        if not session:
            raise _not_found("Quiz session")
        order = json.loads(session["card_order"])
        if session["completed"] or session["current_index"] >= len(order) or order[session["current_index"]] != card_id:
            raise HTTPException(status_code=409, detail={"code": "not_current_card", "message": "Only the current card can be answered"})
        card = self.cards.get(card_id)
        if not card:
            raise _not_found("Card")
        return session, card

    def _view(self, session_id: str) -> QuizSession:
        session = self.repository.get_session(session_id)
        if not session:
            raise _not_found("Quiz session")
        deck = self.decks.get(session["deck_id"])
        if not deck:
            raise _not_found("Deck")
        order = json.loads(session["card_order"])
        current = None
        if not session["completed"] and session["current_index"] < len(order):
            card = self.cards.get(order[session["current_index"]])
            if card:
                current = safe_card(card)
        return QuizSession(id=session["id"], deck=DeckReference(id=deck.id, name=deck.name), total_questions=len(order), current_index=session["current_index"], card=current, complete=bool(session["completed"]))
