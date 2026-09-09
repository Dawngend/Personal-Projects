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
    module_ids: str | None = None


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
    # Additive migration: CREATE TABLE IF NOT EXISTS never alters an existing
    # table. Decks created before the Reviewer view shipped have no module_ids
    # column at all, so it is added as nullable JSON (a list of module ids) --
    # NULL for decks generated before this migration, which simply have no
    # per-module Reviewer link. Legacy modules_included stays untouched; it is
    # still the only source of module names for the Streamlit path, which has
    # no module ids to offer.
    # The check-then-ALTER above is not atomic across processes: the API and
    # worker containers both call open_connection at startup, both can see the
    # column missing, and whichever loses the race hits "duplicate column
    # name" and crashes (observed on the production api container 2026-09-09,
    # restarted clean once the column already existed). Swallow exactly that
    # race instead of the check, so a real schema problem still raises.
    deck_columns = {row[1] for row in connection.execute("PRAGMA table_info(decks)")}
    if "module_ids" not in deck_columns:
        try:
            connection.execute("ALTER TABLE decks ADD COLUMN module_ids TEXT")
        except sqlite3.OperationalError as error:
            if "duplicate column name" not in str(error):
                raise


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
            rows = connection.execute("SELECT id, name, modules_included, subject, module_ids FROM decks").fetchall()
        return [Deck(*row) for row in rows]

    def get(self, deck_id: int) -> Deck | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, name, modules_included, subject, module_ids FROM decks WHERE id = ?",
                (deck_id,),
            ).fetchone()
        return Deck(*row) if row else None

    def set_module_ids(self, deck_id: int, module_ids: list[str]) -> None:
        """Record which module ids a deck was generated from, for the Reviewer link.

        Separate from creation because the legacy Streamlit path never has module ids
        to offer, and the API worker only learns deck_id after persist_valid_cards
        returns it.
        """

        with self._connection() as connection:
            connection.execute(
                "UPDATE decks SET module_ids = ? WHERE id = ?",
                (json.dumps(module_ids), deck_id),
            )

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
