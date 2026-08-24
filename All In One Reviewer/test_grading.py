from __future__ import annotations

import pytest

from grading import grade_enumeration, grade_problem_answer


@pytest.mark.parametrize(
    ("answer", "expected", "tier"),
    [
        ("3/4", "0.75", "numeric"),
        ("[[1, 2], [3, 4]]", "[[1,2],[3,4]]", "structured"),
        ("(1, 2, 3)", "<1,2,3>", "structured"),
        ("x = 2t", "2t", "exact"),
        ("sqrt(2)", "1.41421356", "numeric"),
        ("{1, 2}", "{2, 1}", "structured"),
    ],
)
def test_problem_answer_comparison_ladder_accepts_equivalent_forms(
    answer: str, expected: str, tier: str
) -> None:
    result = grade_problem_answer(answer, expected)

    assert result
    assert result.tier == tier


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("[[1, 2], [3, 4]]", "[[1,2],[4,3]]"),
        ("0.75", "0.76"),
    ],
)
def test_problem_answer_comparison_ladder_rejects_distinct_forms(answer: str, expected: str) -> None:
    result = grade_problem_answer(answer, expected)

    assert not result
    assert result.tier == "fail"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("1,024", "1024"),
        ("-4", "−4"),
        ("25%", "0.25"),
        ("A = 2.5e3", "2500"),
    ],
)
def test_numeric_tier_handles_supported_scalar_formats(answer: str, expected: str) -> None:
    result = grade_problem_answer(answer, expected)

    assert result
    assert result.tier == "numeric"


def test_enumeration_requires_token_or_phrase_boundaries() -> None:
    caught, missed = grade_enumeration("arrow and ranked", ["row", "rank"])

    assert caught == []
    assert missed == ["row", "rank"]


def test_enumeration_accepts_complete_phrase_boundaries() -> None:
    caught, missed = grade_enumeration("row reduction, rank", ["row reduction", "rank"])

    assert caught == ["row reduction", "rank"]
    assert missed == []


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("{eigenvalue = 5, 1}", "{1, 5}"),
        ("x = 1, y = 2, z = 3", "(1, 2, 3)"),
        ("t(1, -1, 0)", "(t, -t, 0)"),
        ("s(2, 4) + t(1, 1)", "(2s+t, 4s+t)"),
        ("2*u(1, 3) - v(2, 1)", "(2u-2v, 6u-v)"),
    ],
)
def test_problem_answer_accepts_general_labelled_and_symbolic_vectors(
    answer: str, expected: str
) -> None:
    assert grade_problem_answer(answer, expected)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("x = 1, y = 3", "(1, 2)"),
        ("t(1, -1, 0)", "(t, t, 0)"),
        ("s(2, 4) + t(1, 1)", "(2s+t, 4s-t)"),
        ("u(1, 2)", "(u, 2u, 0)"),
    ],
)
def test_problem_answer_rejects_distinct_labelled_and_symbolic_vectors(
    answer: str, expected: str
) -> None:
    assert not grade_problem_answer(answer, expected)
