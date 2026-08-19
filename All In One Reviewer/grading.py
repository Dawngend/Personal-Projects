"""Pure grading and legacy card-payload helpers shared by UI and future API code."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, Literal


ComparisonTier = Literal["exact", "numeric", "structured", "symbolic", "fail"]


class ProblemAnswerResult(int):
    """A truthy-compatible grading result that records the first matching tier."""

    tier: ComparisonTier

    def __new__(cls, tier: ComparisonTier) -> ProblemAnswerResult:
        result = super().__new__(cls, tier != "fail")
        result.tier = tier
        return result

    @property
    def matched(self) -> bool:
        return bool(self)


@dataclass(frozen=True)
class _StructuredValue:
    kind: Literal["sequence", "set"]
    items: tuple[float | _StructuredValue, ...]


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
    caught = [item for item in expected_items if _contains_complete_phrase(normalized_answer, item)]
    missed = [item for item in expected_items if item not in caught]
    return caught, missed


def grade_problem_answer(
    answer: str, expected_answer: str, tolerance: float = 1e-9
) -> ProblemAnswerResult:
    """Return the first answer-comparison tier that proves equivalence."""

    normalized_answer = normalize_answer(answer)
    normalized_expected = normalize_answer(expected_answer)
    if normalized_answer == normalized_expected:
        return ProblemAnswerResult("exact")

    comparable_answer = _strip_answer_label(normalized_answer)
    comparable_expected = _strip_answer_label(normalized_expected)
    if comparable_answer == comparable_expected:
        return ProblemAnswerResult("exact")

    numeric_answer = _parse_scalar(comparable_answer)
    numeric_expected = _parse_scalar(comparable_expected)
    if numeric_answer is not None and numeric_expected is not None:
        if _numbers_close(
            numeric_answer,
            numeric_expected,
            tolerance,
            comparable_answer,
            comparable_expected,
        ):
            return ProblemAnswerResult("numeric")
        return ProblemAnswerResult("fail")

    structured_answer = _parse_structured(comparable_answer)
    structured_expected = _parse_structured(comparable_expected)
    if structured_answer is not None and structured_expected is not None:
        if _structured_equal(structured_answer, structured_expected, tolerance):
            return ProblemAnswerResult("structured")
        return ProblemAnswerResult("fail")

    if _symbolic_equivalent(comparable_answer, comparable_expected):
        return ProblemAnswerResult("symbolic")
    return ProblemAnswerResult("fail")


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


def _contains_complete_phrase(normalized_answer: str, expected_item: str) -> bool:
    phrase = normalize_answer(expected_item)
    if not phrase:
        return False
    pattern = re.escape(phrase).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<!\w){pattern}(?!\w)", normalized_answer))


def _strip_answer_label(value: str) -> str:
    match = re.fullmatch(r"(?:[a-z]|answer)\s*=\s*(.+)", value)
    return match.group(1) if match else value


def _parse_scalar(value: str) -> float | None:
    normalized = value.replace("−", "-").replace(",", "").strip()
    if not normalized:
        return None
    if normalized.endswith("%"):
        percentage = _parse_scalar(normalized[:-1])
        return percentage / 100 if percentage is not None else None
    fraction = re.fullmatch(r"(.+?)\s*/\s*(.+)", normalized)
    if fraction:
        numerator = _parse_scalar(fraction.group(1))
        denominator = _parse_scalar(fraction.group(2))
        if numerator is None or denominator in (None, 0):
            return None
        return numerator / denominator
    square_root = re.fullmatch(r"sqrt\s*\(\s*(.+)\s*\)", normalized)
    if square_root:
        radicand = _parse_scalar(square_root.group(1))
        return math.sqrt(radicand) if radicand is not None and radicand >= 0 else None
    try:
        result = float(normalized)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _numbers_close(
    left: float,
    right: float,
    tolerance: float,
    left_text: str,
    right_text: str,
) -> bool:
    rounding_tolerance = max(_display_resolution(left_text), _display_resolution(right_text)) / 2
    return abs(left - right) <= max(tolerance, rounding_tolerance)


def _display_resolution(value: str) -> float:
    normalized = value.replace("−", "-").replace(",", "").strip()
    if normalized.endswith("%"):
        return _display_resolution(normalized[:-1]) / 100
    match = re.fullmatch(r"[+-]?(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?", normalized)
    if not match:
        return 0.0
    decimal_places = len(match.group(2) or "")
    exponent = int(match.group(3) or "0")
    return 10.0 ** (exponent - decimal_places)


def _parse_structured(value: str) -> _StructuredValue | None:
    stripped = value.strip()
    if len(stripped) < 2:
        return None
    delimiters = {"[": "]", "(": ")", "<": ">", "{": "}"}
    opening = stripped[0]
    closing = delimiters.get(opening)
    if closing is None or stripped[-1] != closing:
        return None
    inner = stripped[1:-1].strip()
    parts = _split_top_level(inner)
    if parts is None:
        return None
    items: list[float | _StructuredValue] = []
    for part in parts:
        nested = _parse_structured(part)
        if nested is not None:
            items.append(nested)
            continue
        scalar = _parse_scalar(part)
        if scalar is None:
            return None
        items.append(scalar)
    return _StructuredValue("set" if opening == "{" else "sequence", tuple(items))


def _split_top_level(value: str) -> list[str] | None:
    if not value:
        return []
    opening = {"[", "(", "<", "{"}
    closing = {"]": "[", ")": "(", ">": "<", "}": "{"}
    stack: list[str] = []
    parts: list[str] = []
    start = 0
    for index, character in enumerate(value):
        if character in opening:
            stack.append(character)
        elif character in closing:
            if not stack or stack.pop() != closing[character]:
                return None
        elif character == "," and not stack:
            part = value[start:index].strip()
            if not part:
                return None
            parts.append(part)
            start = index + 1
    if stack:
        return None
    final_part = value[start:].strip()
    return parts + [final_part] if final_part else None


def _structured_equal(
    left: float | _StructuredValue, right: float | _StructuredValue, tolerance: float
) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        return abs(left - right) <= tolerance
    if not isinstance(left, _StructuredValue) or not isinstance(right, _StructuredValue):
        return False
    if left.kind != right.kind or len(left.items) != len(right.items):
        return False
    if left.kind == "sequence":
        return all(_structured_equal(item, other, tolerance) for item, other in zip(left.items, right.items))
    unmatched = list(right.items)
    for item in left.items:
        for index, other in enumerate(unmatched):
            if _structured_equal(item, other, tolerance):
                unmatched.pop(index)
                break
        else:
            return False
    return True


def _symbolic_equivalent(answer: str, expected_answer: str) -> bool:
    try:
        import sympy
        from sympy.parsing.sympy_parser import (
            implicit_multiplication_application,
            parse_expr,
            standard_transformations,
        )
    except ImportError:
        return False
    try:
        transformations = standard_transformations + (implicit_multiplication_application,)
        actual = parse_expr(answer, transformations=transformations)
        expected = parse_expr(expected_answer, transformations=transformations)
        return bool(sympy.simplify(actual - expected) == 0)
    except (SyntaxError, TypeError, ValueError):
        return False
