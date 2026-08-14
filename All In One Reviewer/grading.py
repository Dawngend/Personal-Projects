"""Pure grading and legacy card-payload helpers shared by UI and future API code."""

from __future__ import annotations

import json
from typing import Any


def decode_card_options(raw_options: str | None) -> Any:
    """Read legacy multiple-choice arrays and structured card payloads."""

    if not raw_options:
        return []
    try:
        return json.loads(raw_options)
    except json.JSONDecodeError:
        return []


def grade_enumeration(answer: str, expected_items: list[str]) -> tuple[list[str], list[str]]:
    """Grade expected phrases case-insensitively, preserving their stored spelling."""

    normalized_answer = normalize_answer(answer)
    caught = [item for item in expected_items if normalize_answer(item) in normalized_answer]
    missed = [item for item in expected_items if item not in caught]
    return caught, missed


def grade_problem_answer(answer: str, expected_answer: str, tolerance: float = 1e-9) -> bool:
    """Accept normalized text matches and ordinary scalar numeric representations."""

    normalized_answer = normalize_answer(answer)
    normalized_expected = normalize_answer(expected_answer)
    if normalized_answer == normalized_expected:
        return True
    try:
        return abs(
            float(normalized_answer.replace(",", ""))
            - float(normalized_expected.replace(",", ""))
        ) <= tolerance
    except ValueError:
        return False


def problem_payload(options: Any, correct_answer: str) -> tuple[str, list[str]]:
    """Support problem payloads while retaining the legacy correct-answer fallback."""

    if isinstance(options, dict):
        final_answer = str(options.get("final_answer") or correct_answer)
        steps = options.get("solution_steps", [])
        if isinstance(steps, list) and all(isinstance(step, str) for step in steps):
            return final_answer, steps
        return final_answer, []
    return correct_answer, []


def normalize_answer(value: str) -> str:
    return " ".join(value.casefold().split())
