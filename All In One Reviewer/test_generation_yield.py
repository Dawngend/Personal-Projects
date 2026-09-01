"""Regression tests for the partial-yield defect.

A measured 20-question run on 2026-08-30 produced only 10 valid cards. The
cause was a truncated provider response: the JSON failed to parse, the whole
chunk was discarded, and with `questions_per_chunk = ceil(total / chunks)`
losing one chunk of two halves the deck. Three defects are covered here.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import generator


def _valid_card(suffix: str) -> dict:
    return {
        "type": "multiple_choice",
        "question": f"Which option is correct for case {suffix}?",
        "options": ["alpha", "bravo", "charlie", "delta"],
        "correct_answer": "alpha",
    }


class SalvageTruncatedResponseTests(unittest.TestCase):
    """A truncated completion must lose only the incomplete question."""

    def test_recovers_complete_objects_and_drops_the_cut_tail(self) -> None:
        payload = json.dumps({"questions": [_valid_card("a"), _valid_card("b")]})
        # Cut inside the second object, as a token limit would.
        truncated = payload[: payload.rindex("bravo")]

        with self.assertRaises(json.JSONDecodeError):
            json.loads(truncated)

        recovered = generator._salvage_questions(truncated)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["correct_answer"], "alpha")

    def test_returns_empty_when_nothing_is_recoverable(self) -> None:
        self.assertEqual(generator._salvage_questions("not json at all"), [])
        self.assertEqual(generator._salvage_questions('{"other": [1, 2]}'), [])
        self.assertEqual(generator._salvage_questions('{"questions": ['), [])

    def test_braces_and_escapes_inside_strings_do_not_confuse_the_scan(self) -> None:
        card = _valid_card("c")
        card["question"] = 'What does {"a": 1} mean, and why the \\" quote?'
        payload = json.dumps({"questions": [card]}) + ', {"type": "enumeration"'

        recovered = generator._salvage_questions(payload)
        self.assertGreaterEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["question"], card["question"])

    def test_query_groq_returns_salvaged_cards_instead_of_discarding_the_chunk(self) -> None:
        payload = json.dumps({"questions": [_valid_card("d"), _valid_card("e")]})
        truncated = payload[: payload.rindex("bravo")]

        client = MagicMock()
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=truncated))]
        )

        with patch.dict("os.environ", {"ANDYHUB_EXTRACTION_CACHE_DIR": ""}, clear=False):
            questions = generator._query_groq(client, "some module text")

        self.assertEqual(len(questions), 1, "a truncated chunk must not be discarded whole")


class CompletionBudgetTests(unittest.TestCase):
    """The completion limit must be explicit, not the provider default."""

    def test_max_completion_tokens_is_sent(self) -> None:
        client = MagicMock()
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({"questions": []})))]
        )

        generator._query_groq(client, "some module text")

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertIn("max_completion_tokens", kwargs)
        self.assertGreaterEqual(kwargs["max_completion_tokens"], 4096)

    def test_budget_is_configurable_without_a_code_edit(self) -> None:
        import importlib

        try:
            # The restoring reload must happen AFTER patch.dict exits, or the
            # module is rebuilt while the override is still set and every
            # later test in the process inherits it.
            with patch.dict("os.environ", {"ANDYHUB_MAX_COMPLETION_TOKENS": "1234"}):
                reloaded = importlib.reload(generator)
                self.assertEqual(reloaded.MAX_COMPLETION_TOKENS, 1234)
        finally:
            importlib.reload(generator)


class ValidateThenTrimTests(unittest.TestCase):
    """Trimming before validating silently shrank the deck."""

    def test_invalid_cards_do_not_consume_slots_in_the_requested_total(self) -> None:
        malformed = {"type": "multiple_choice", "question": "missing its answer"}
        raw = [malformed, _valid_card("1"), _valid_card("2"), _valid_card("3")]

        kept = generator.validate_generated_cards(raw, total_questions=3)

        self.assertEqual(
            len(kept), 3,
            "a malformed card inside the first N must not reduce the deck below N "
            "when valid cards exist past the cut",
        )
        self.assertTrue(all(card.get("correct_answer") for card in kept))

    def test_never_returns_more_than_requested(self) -> None:
        raw = [_valid_card(str(i)) for i in range(10)]
        self.assertEqual(len(generator.validate_generated_cards(raw, total_questions=4)), 4)

    def test_all_invalid_yields_empty_rather_than_raising(self) -> None:
        raw = [{"type": "multiple_choice"}, {"nope": True}]
        self.assertEqual(generator.validate_generated_cards(raw, total_questions=5), [])


if __name__ == "__main__":
    unittest.main()
