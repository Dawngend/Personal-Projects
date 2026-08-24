"""Pure grading and legacy card-payload helpers shared by UI and future API code."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, Literal


ComparisonTier = Literal["exact", "numeric", "structured", "symbolic", "fail"]
Scalar = float | complex


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
    items: tuple[Scalar | _StructuredValue, ...]


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

    structured_answer = _parse_structured(comparable_answer) or _parse_assignment_sequence(
        normalized_answer
    )
    structured_expected = _parse_structured(comparable_expected) or _parse_assignment_sequence(
        normalized_expected
    )
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
    identifier = r"[a-z][a-z0-9_]*"
    label = rf"(?:answer|{identifier}\([^()]*\)|{identifier}(?:\^[a-z0-9]+|[ᵀᵗ])?)"
    match = re.fullmatch(rf"{label}\s*=\s*(.+)", value)
    return match.group(1) if match else value


def _parse_scalar(value: str) -> Scalar | None:
    normalized = value.replace("−", "-").replace(",", "").strip()
    if not normalized:
        return None
    complex_value = _parse_complex(normalized)
    if complex_value is not None:
        return complex_value
    return _parse_real_scalar(normalized)


def _parse_real_scalar(normalized: str) -> float | None:
    if normalized.endswith("%"):
        percentage = _parse_real_scalar(normalized[:-1])
        return percentage / 100 if percentage is not None else None
    fraction = re.fullmatch(r"(.+?)\s*/\s*(.+)", normalized)
    if fraction:
        numerator = _parse_real_scalar(fraction.group(1))
        denominator = _parse_real_scalar(fraction.group(2))
        if numerator is None or denominator in (None, 0):
            return None
        return numerator / denominator
    radical_product = re.fullmatch(r"(.+?)\s*sqrt\s*\(\s*(.+)\s*\)", normalized)
    if radical_product:
        coefficient = _parse_real_scalar(radical_product.group(1))
        radicand = _parse_real_scalar(radical_product.group(2))
        if coefficient is None or radicand is None or radicand < 0:
            return None
        return coefficient * math.sqrt(radicand)
    square_root = re.fullmatch(r"sqrt\s*\(\s*(.+)\s*\)", normalized)
    if square_root:
        radicand = _parse_real_scalar(square_root.group(1))
        return math.sqrt(radicand) if radicand is not None and radicand >= 0 else None
    try:
        result = float(normalized)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _parse_complex(value: str) -> complex | None:
    compact = re.sub(r"\s+", "", value)
    if compact in {"i", "+i"}:
        return complex(0, 1)
    if compact == "-i":
        return complex(0, -1)

    suffix = re.fullmatch(r"(.+?)([+-])(.*)i", compact)
    if suffix:
        real = _parse_real_scalar(suffix.group(1))
        imaginary_text = suffix.group(3) or "1"
        imaginary = _parse_real_scalar(imaginary_text)
        if real is None or imaginary is None:
            return None
        return complex(real, imaginary if suffix.group(2) == "+" else -imaginary)

    prefix = re.fullmatch(r"(.+?)([+-])i(.+)", compact)
    if prefix:
        real = _parse_real_scalar(prefix.group(1))
        imaginary = _parse_real_scalar(prefix.group(3))
        if real is None or imaginary is None:
            return None
        return complex(real, imaginary if prefix.group(2) == "+" else -imaginary)
    return None


def _numbers_close(
    left: Scalar,
    right: Scalar,
    tolerance: float,
    left_text: str,
    right_text: str,
) -> bool:
    resolutions = [
        resolution
        for resolution in (_display_resolution(left_text), _display_resolution(right_text))
        if resolution > 0
    ]
    rounding_tolerance = min(resolutions) / 2 if resolutions else 0.0
    return abs(left - right) <= max(tolerance, rounding_tolerance)


def _display_resolution(value: str) -> float:
    normalized = value.replace("−", "-").replace(",", "").strip()
    if normalized.endswith("%"):
        return _display_resolution(normalized[:-1]) / 100
    match = re.fullmatch(r"[+-]?(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?", normalized)
    if match is not None:
        decimal_places = len(match.group(2) or "")
        exponent = int(match.group(3) or "0")
        return 10.0 ** (exponent - decimal_places)
    if "i" not in normalized:
        return 0.0
    numeric_tokens = re.findall(r"(?:\d+\.\d*|\.\d+)(?:e[+-]?\d+)?", normalized)
    resolutions: list[float] = []
    for token in numeric_tokens:
        match = re.fullmatch(r"(?:\d+)?\.(\d*)(?:e([+-]?\d+))?", token)
        if match is None:
            continue
        decimal_places = len(match.group(1) or "")
        exponent = int(match.group(2) or "0")
        resolutions.append(10.0 ** (exponent - decimal_places))
    return min(resolutions, default=0.0)


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
    rows = _split_top_level(inner, separators=";")
    if rows is None:
        return None
    if opening == "[" and len(rows) > 1:
        parsed_rows = tuple(_parse_sequence(row) for row in rows)
        if any(row is None for row in parsed_rows):
            return None
        return _StructuredValue("sequence", parsed_rows)
    sequence = _parse_sequence(inner)
    if sequence is None:
        return None
    return _StructuredValue("set" if opening == "{" else "sequence", sequence.items)


def _parse_sequence(value: str) -> _StructuredValue | None:
    parts = _split_top_level(value, separators=",|")
    if parts is None:
        return None
    if len(parts) == 1:
        spaced_parts = _split_top_level_whitespace(value)
        if spaced_parts is not None and len(spaced_parts) > 1:
            parts = spaced_parts
    items: list[Scalar | _StructuredValue] = []
    for part in parts:
        part = _strip_answer_label(part)
        nested = _parse_structured(part)
        if nested is not None:
            items.append(nested)
            continue
        scalar = _parse_scalar(part)
        if scalar is None:
            return None
        items.append(scalar)
    return _StructuredValue("sequence", tuple(items))


def _parse_assignment_sequence(value: str) -> _StructuredValue | None:
    """Parse an unwrapped list of labelled scalar components in source order."""

    parts = _split_top_level(value)
    if parts is None or len(parts) < 2:
        return None
    stripped_parts = [_strip_answer_label(part) for part in parts]
    if any(part == stripped for part, stripped in zip(parts, stripped_parts)):
        return None
    items = tuple(_parse_scalar(part) for part in stripped_parts)
    if any(item is None for item in items):
        return None
    return _StructuredValue("sequence", items)


def _split_top_level(value: str, *, separators: str = ",") -> list[str] | None:
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
        elif character in separators and not stack:
            part = value[start:index].strip()
            if not part:
                return None
            parts.append(part)
            start = index + 1
    if stack:
        return None
    final_part = value[start:].strip()
    return parts + [final_part] if final_part else None


def _split_top_level_whitespace(value: str) -> list[str] | None:
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
        elif character.isspace() and not stack:
            part = value[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1
    if stack:
        return None
    final_part = value[start:].strip()
    if final_part:
        parts.append(final_part)
    return parts or None


def _structured_equal(
    left: Scalar | _StructuredValue, right: Scalar | _StructuredValue, tolerance: float
) -> bool:
    if isinstance(left, (float, complex)) and isinstance(right, (float, complex)):
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
        actual_vector = _parse_symbolic_vector(answer, parse_expr, transformations)
        expected_vector = _parse_symbolic_vector(expected_answer, parse_expr, transformations)
        if actual_vector is not None or expected_vector is not None:
            if actual_vector is None or expected_vector is None:
                return False
            if len(actual_vector) != len(expected_vector):
                return False
            return all(
                bool(sympy.simplify(actual - expected) == 0)
                for actual, expected in zip(actual_vector, expected_vector)
            )

        actual = parse_expr(answer, transformations=transformations)
        expected = parse_expr(expected_answer, transformations=transformations)
        return bool(sympy.simplify(actual - expected) == 0)
    except (SyntaxError, TypeError, ValueError):
        return False


def _parse_symbolic_vector(value: str, parse_expr: Any, transformations: Any) -> tuple[Any, ...] | None:
    """Parse vector literals and linear combinations of scalar-vector terms."""

    literal = _symbolic_vector_literal(value, parse_expr, transformations)
    if literal is not None:
        return literal

    terms = _split_top_level_addition(value)
    if terms is None:
        return None
    total: list[Any] | None = None
    for sign, term in terms:
        scaled = _symbolic_scaled_vector(term, parse_expr, transformations)
        if scaled is None:
            return None
        coefficient, vector = scaled
        if total is None:
            total = [0] * len(vector)
        if len(total) != len(vector):
            return None
        for index, component in enumerate(vector):
            total[index] += sign * coefficient * component
    return tuple(total) if total is not None else None


def _symbolic_vector_literal(
    value: str, parse_expr: Any, transformations: Any
) -> tuple[Any, ...] | None:
    stripped = value.strip()
    delimiters = {"[": "]", "(": ")", "<": ">"}
    if len(stripped) < 2 or delimiters.get(stripped[0]) != stripped[-1]:
        return None
    parts = _split_top_level(stripped[1:-1])
    if parts is None or len(parts) < 2:
        return None
    return tuple(parse_expr(part, transformations=transformations) for part in parts)


def _symbolic_scaled_vector(
    value: str, parse_expr: Any, transformations: Any
) -> tuple[Any, tuple[Any, ...]] | None:
    stripped = value.strip()
    opening_index = _first_top_level_opening(stripped)
    if opening_index is None:
        return None
    vector = _symbolic_vector_literal(
        stripped[opening_index:], parse_expr, transformations
    )
    if vector is None:
        return None
    coefficient_text = stripped[:opening_index].strip()
    if coefficient_text.endswith("*"):
        coefficient_text = coefficient_text[:-1].rstrip()
    if not coefficient_text:
        return None
    coefficient = parse_expr(coefficient_text, transformations=transformations)
    return coefficient, vector


def _first_top_level_opening(value: str) -> int | None:
    for index, character in enumerate(value):
        if character in "([<":
            return index
    return None


def _split_top_level_addition(value: str) -> list[tuple[int, str]] | None:
    """Split a symbolic linear combination without splitting vector components."""

    stack: list[str] = []
    closing = {")": "(", "]": "[", ">": "<"}
    terms: list[tuple[int, str]] = []
    sign = 1
    start = 0
    for index, character in enumerate(value):
        if character in "([<":
            stack.append(character)
        elif character in closing:
            if not stack or stack.pop() != closing[character]:
                return None
        elif character in "+-" and not stack:
            prefix = value[start:index].strip()
            if prefix:
                terms.append((sign, prefix))
            elif index != 0:
                return None
            sign = 1 if character == "+" else -1
            start = index + 1
    if stack:
        return None
    final = value[start:].strip()
    if not final:
        return None
    terms.append((sign, final))
    return terms
