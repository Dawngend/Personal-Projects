"""Legacy tuple-returning database façade backed by typed Phase 1 repositories."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from repositories import CardRepository, DeckRepository, NewCard


def _default_database_path() -> str:
    """Resolve the same database file the API process uses.

    Streamlit has always opened `Database/reviewer.db` relative to the current
    directory, so that stays the fallback and its behavior is unchanged. The
    deployed stack mounts its state elsewhere and configures it through the
    same environment variables `andyhub_api.settings.Settings` reads. Without
    honoring them a containerized worker importing this module writes decks to
    a private path inside the image while the API serves a different file, so
    generated decks silently disappear.
    """

    configured = os.environ.get("ANDYHUB_DATABASE_PATH", "").strip()
    if configured:
        return configured
    data_root = os.environ.get("ANDYHUB_DATA_ROOT", "").strip()
    if data_root:
        return str(Path(data_root) / "Database" / "reviewer.db")
    return str(Path("Database") / "reviewer.db")


# Preserve the legacy function signatures used by Streamlit.
DB_PATH = _default_database_path()


def _decks() -> DeckRepository:
    return DeckRepository(DB_PATH)


def _cards() -> CardRepository:
    return CardRepository(DB_PATH)


def init_db() -> None:
    # Opening either repository initializes the unchanged tables on the same file.
    _decks().list()


def create_deck(name: str, modules_included: str, subject: str) -> int:
    return _decks().create(name, modules_included, subject).id


def add_card(
    deck_id: int | str,
    card_type: str,
    question: str,
    correct_answer: str,
    options: Any = None,
) -> None:
    _cards().add(int(deck_id), NewCard(card_type, question, correct_answer, options))


def create_deck_with_cards(
    name: str,
    modules_included: str,
    subject: str,
    cards: Iterable[NewCard],
) -> int:
    """Phase 1 transaction API; creates no deck until valid cards are supplied."""

    return _decks().create_with_cards(name, modules_included, subject, cards).id


def get_decks() -> list[tuple[int, str, str, str]]:
    return [
        (deck.id, deck.name, deck.modules_included, deck.subject)
        for deck in _decks().list()
    ]


def get_cards_for_deck(deck_id: int | str) -> list[tuple[int, int, str, str, str, str | None, int]]:
    return [
        (
            card.id,
            card.deck_id,
            card.card_type,
            card.question,
            card.correct_answer,
            card.options,
            card.times_missed,
        )
        for card in _cards().list_for_deck(int(deck_id))
    ]


def update_card_miss_count(card_id: int | str, increment: int = 1) -> None:
    _cards().increment_miss_count(int(card_id), increment)


init_db()
