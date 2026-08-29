"""Tests for the optional answer_format card field.

The field lets the generating model declare the shape of the answer it
produced. It is strictly optional: absent means auto-detect, so every card
already stored in Database/reviewer.db keeps validating and keeps grading
exactly as before.
"""

import json

import pytest

from generator import (
    ANSWER_FORMATS,
    CARD_FORMATS,
    _card_storage_values,
    _validate_card,
)
from grading import decode_card_options, problem_payload


def problem_card(**overrides):
    card = {
        "type": "problem",
        "question": "Solve for x.",
        "correct_answer": "0.75",
        "solution_steps": ["Divide both sides by 4."],
    }
    card.update(overrides)
    return card


def multiple_choice_card(**overrides):
    card = {
        "type": "multiple_choice",
        "question": "Which is a scalar?",
        "options": ["3", "[1,2]", "{1,2}", "<1,2>"],
        "correct_answer": "3",
    }
    card.update(overrides)
    return card


class TestBackwardCompatibility:
    """Cards stored before this field existed must keep working untouched."""

    def test_problem_card_without_answer_format_is_valid(self):
        assert _validate_card(problem_card(), 1) is True

    def test_multiple_choice_card_without_answer_format_is_valid(self):
        assert _validate_card(multiple_choice_card(), 1) is True

    def test_enumeration_card_without_answer_format_is_valid(self):
        card = {
            "type": "enumeration",
            "question": "Name two row operations.",
            "correct_answer": ["swap", "scale"],
        }
        assert _validate_card(card, 1) is True

    def test_storage_omits_the_key_entirely_when_absent(self):
        _correct, options = _card_storage_values(problem_card())
        assert "answer_format" not in options

    def test_absent_format_leaves_the_payload_shape_unchanged(self):
        _correct, options = _card_storage_values(problem_card())
        answer, steps = problem_payload(options, "0.75")
        assert answer == "0.75"
        assert steps == ["Divide both sides by 4."]


class TestAcceptedValues:
    @pytest.mark.parametrize("declared", ANSWER_FORMATS)
    def test_every_documented_format_is_accepted(self, declared):
        assert _validate_card(problem_card(answer_format=declared), 1) is True

    def test_the_documented_set_is_the_one_the_brief_specified(self):
        assert set(ANSWER_FORMATS) == {
            "scalar",
            "fraction",
            "matrix",
            "vector",
            "set",
            "expression",
            "text",
        }

    def test_format_is_accepted_on_non_problem_cards_too(self):
        assert _validate_card(multiple_choice_card(answer_format="scalar"), 1) is True


class TestRejectedValues:
    def test_unknown_format_is_rejected(self):
        assert _validate_card(problem_card(answer_format="tensor"), 1) is False

    def test_non_string_format_is_rejected(self):
        assert _validate_card(problem_card(answer_format=["scalar"]), 1) is False

    def test_empty_format_is_rejected(self):
        assert _validate_card(problem_card(answer_format="   "), 1) is False

    def test_none_is_rejected_rather_than_treated_as_absent(self):
        # An explicit null is a malformed declaration, not an omission.
        assert _validate_card(problem_card(answer_format=None), 1) is False

    def test_case_variant_is_rejected(self):
        assert _validate_card(problem_card(answer_format="Scalar"), 1) is False


class TestStorageRoundTrip:
    def test_declared_format_survives_storage(self):
        _correct, options = _card_storage_values(
            problem_card(correct_answer="3/4", answer_format="fraction")
        )
        assert options["answer_format"] == "fraction"

    def test_declared_format_survives_a_json_round_trip(self):
        _correct, options = _card_storage_values(
            problem_card(correct_answer="3/4", answer_format="fraction")
        )
        decoded = decode_card_options(json.dumps(options))
        assert decoded["answer_format"] == "fraction"

    def test_problem_payload_ignores_the_extra_key(self):
        _correct, options = _card_storage_values(
            problem_card(correct_answer="3/4", answer_format="fraction")
        )
        answer, steps = problem_payload(options, "3/4")
        assert answer == "3/4"
        assert steps == ["Divide both sides by 4."]


class TestPromptContract:
    def test_card_formats_documents_the_field_as_optional(self):
        assert "answer_format" in CARD_FORMATS
        assert "optional" in CARD_FORMATS.lower()

    def test_card_formats_lists_every_accepted_value(self):
        for declared in ANSWER_FORMATS:
            assert declared in CARD_FORMATS
