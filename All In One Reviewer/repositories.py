"""Typed SQLite access adapters over AndyHub's existing deck/card schema."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable


DEFAULT_DATABASE_PATH = Path("Database") / "reviewer.db"


@dataclass(frozen=True)
class Deck:
    id: int
    name: str
    modules_included: str
    subject: str


@dataclass(frozen=True)
class Card:
    id: int
    deck_id: int
    card_type: str
    question: str
    correct_answer: str
    options: str | None
    times_missed: int


@dataclass(frozen=True)
class NewCard:
    card_type: str
    question: str
    correct_answer: str
    options: Any = None


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the unchanged legacy schema on an existing or new SQLite file."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            modules_included TEXT NOT NULL,
            subject TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_id INTEGER,
            type TEXT NOT NULL,
            question TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            options TEXT,
            times_missed INTEGER DEFAULT 0,
            FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
        )
        """
    )


@contextmanager
def open_connection(database_path: str | Path):
    """Provide a transactional connection that always closes on Windows too."""

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30.0)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys=ON")
    initialize_schema(connection)
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


class DeckRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)

    def create(self, name: str, modules_included: str, subject: str) -> Deck:
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO decks (name, modules_included, subject) VALUES (?, ?, ?)",
                (name, modules_included, subject),
            )
            return Deck(int(cursor.lastrowid), name, modules_included, subject)

    def list(self) -> list[Deck]:
        with self._connection() as connection:
            rows = connection.execute("SELECT id, name, modules_included, subject FROM decks").fetchall()
        return [Deck(*row) for row in rows]

    def get(self, deck_id: int) -> Deck | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, name, modules_included, subject FROM decks WHERE id = ?",
                (deck_id,),
            ).fetchone()
        return Deck(*row) if row else None

    def create_with_cards(
        self, name: str, modules_included: str, subject: str, cards: Iterable[NewCard]
    ) -> Deck:
        """Persist a deck and its valid cards atomically on the same schema/file."""

        materialized_cards = tuple(cards)
        if not materialized_cards:
            raise ValueError("A deck cannot be created without valid cards")
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO decks (name, modules_included, subject) VALUES (?, ?, ?)",
                (name, modules_included, subject),
            )
            deck = Deck(int(cursor.lastrowid), name, modules_included, subject)
            for card in materialized_cards:
                connection.execute(
                    """
                    INSERT INTO cards (deck_id, type, question, correct_answer, options)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        deck.id,
                        card.card_type,
                        card.question,
                        card.correct_answer,
                        json.dumps(card.options) if card.options else None,
                    ),
                )
        return deck

    def _connection(self):
        return open_connection(self.database_path)


class CardRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)

    def list_for_deck(self, deck_id: int) -> list[Card]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, deck_id, type, question, correct_answer, options, times_missed "
                "FROM cards WHERE deck_id = ?",
                (deck_id,),
            ).fetchall()
        return [Card(*row) for row in rows]

    def get(self, card_id: int) -> Card | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, deck_id, type, question, correct_answer, options, times_missed "
                "FROM cards WHERE id = ?",
                (card_id,),
            ).fetchone()
        return Card(*row) if row else None

    def add(self, deck_id: int, card: NewCard) -> Card:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO cards (deck_id, type, question, correct_answer, options)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    deck_id,
                    card.card_type,
                    card.question,
                    card.correct_answer,
                    json.dumps(card.options) if card.options else None,
                ),
            )
            return Card(
                int(cursor.lastrowid), deck_id, card.card_type, card.question,
                card.correct_answer, json.dumps(card.options) if card.options else None, 0,
            )

    def increment_miss_count(self, card_id: int, increment: int = 1) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE cards SET times_missed = times_missed + ? WHERE id = ?",
                (increment, card_id),
            )

    def _connection(self):
        return open_connection(self.database_path)
