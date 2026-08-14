"""OpenAPI models. Safe quiz cards intentionally contain no answer key."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


QuestionStyle = Literal["multiple_choice", "enumeration", "problem", "mixed"]


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=_camel_case, populate_by_name=True)


class MultipleChoiceCard(ApiModel):
    id: int
    type: Literal["multiple_choice"]
    question: str
    options: list[str]


class EnumerationCard(ApiModel):
    id: int
    type: Literal["enumeration"]
    question: str
    expected_count: int


class ProblemCard(ApiModel):
    id: int
    type: Literal["problem"]
    question: str
    answer_format_hint: str | None = None


QuizCard = Annotated[
    MultipleChoiceCard | EnumerationCard | ProblemCard,
    Field(discriminator="type"),
]


class DeckSummary(ApiModel):
    id: int
    name: str
    subject: str
    modules: list[str]
    card_count: int
    question_types: dict[str, int]
    total_misses: int


class DeckDetail(DeckSummary):
    cards: list[QuizCard] | None = None


class ModuleItem(ApiModel):
    id: str
    filename: str
    media_type: str
    size_bytes: int
    content_hash: str
    extraction_status: Literal["pending", "ready", "failed"]
    duplicate: bool = False


class ModuleList(ApiModel):
    items: list[ModuleItem]


class GenerationRequest(ApiModel):
    deck_name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=200)
    module_ids: list[str] = Field(min_length=1)
    question_style: QuestionStyle = "mixed"
    total_questions: int = Field(ge=1, le=100)


class GenerationJob(ApiModel):
    id: str
    status: Literal["queued", "running", "complete", "failed"]
    stage: Literal["queued", "extracting", "retrieving_memory", "generating", "validating", "saving", "complete", "failed"]
    progress: int = Field(ge=0, le=100)
    message: str | None = None
    cards_received: int = 0
    cards_valid: int = 0
    deck_id: int | None = None
    error: str | None = None


class QuizSessionRequest(ApiModel):
    deck_id: int
    mode: Literal["all", "missed"] = "all"


class DeckReference(ApiModel):
    id: int
    name: str


class QuizSession(ApiModel):
    id: str
    deck: DeckReference
    total_questions: int
    current_index: int
    card: QuizCard | None
    complete: bool


class MultipleChoiceAnswer(ApiModel):
    type: Literal["multiple_choice"]
    value: str


class EnumerationAnswer(ApiModel):
    type: Literal["enumeration"]
    value: str


class ProblemAnswer(ApiModel):
    type: Literal["problem"]
    value: str


AnswerPayload = Annotated[
    MultipleChoiceAnswer | EnumerationAnswer | ProblemAnswer,
    Field(discriminator="type"),
]


class SubmitAnswer(ApiModel):
    card_id: int
    answer: AnswerPayload


class GradeResult(ApiModel):
    correct: bool
    complete: bool
    feedback: str
    caught_items: list[str] | None = None
    missed_items: list[str] | None = None
    expected_answer: str | None = None
    solution_steps: list[str] | None = None


class RevealResult(ApiModel):
    expected_answer: str
    solution_steps: list[str]


class SessionSummary(ApiModel):
    total_questions: int
    attempted: int
    correct: int
    missed_card_ids: list[int]
    revealed_card_ids: list[int]
    complete: bool
