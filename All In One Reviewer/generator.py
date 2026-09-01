import os
import json
import re
import sys
import tempfile
import time
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from groq import Groq
from rag_engine import add_to_memory, get_historical_context
from extractor import process_module_file_v2
from database import add_card, create_deck, create_deck_with_cards
from repositories import NewCard

# ── Constants & Configuration ────────────────────────────────────────────────

# MODEL CHOICES:
#
# Read from the environment so a retired model is a config change rather than
# a code edit and redeploy. Groq removed `llama-3.3-70b-versatile`, which had
# been hardcoded here, and every generation failed with a 404 while the health
# check still reported the generator as "configured" because it only checks
# that an API key exists.
#
# The default was verified against the real generation prompt on 2026-08-29:
# openai/gpt-oss-120b returned 6 of 6 valid cards with the correct question
# mix. openai/gpt-oss-20b and qwen/qwen3.8-27b both failed JSON parsing on the
# same input, so do not switch the default without re-running that check.
MODEL_NAME = os.environ.get("ANDYHUB_GROQ_MODEL", "").strip() or "openai/gpt-oss-120b"

MAX_CHUNK_CHARS = 12_000

# Completion budget for one chunk's JSON payload.
#
# This was previously unset, so the provider default applied. A truncated
# response is not a partial loss: the JSON fails to parse, `_query_groq`
# returns an empty list, and EVERY question in that chunk is discarded. With
# `questions_per_chunk = ceil(total / len(chunks))`, losing one chunk of two
# turns a 20-question request into 10 valid cards, which is exactly the defect
# measured on 2026-08-30.
#
# A situational question with four options and an explanation runs roughly
# 250-400 tokens, so 10 per chunk needs about 4k. 8192 leaves headroom without
# approaching the model's limit.
MAX_COMPLETION_TOKENS = int(
    os.environ.get("ANDYHUB_MAX_COMPLETION_TOKENS", "").strip() or 8192
)

QUESTION_STYLES = {
    "multiple_choice": "Multiple Choice",
    "enumeration": "Enumeration",
    "problem": "Problem-Solving",
    "mixed": "Mixed",
}

ANSWER_FORMATS = (
    "scalar",
    "fraction",
    "matrix",
    "vector",
    "set",
    "expression",
    "text",
)

CARD_FORMATS = (
    'Every question object must have "type" and a non-empty "question". '
    'For "multiple_choice", provide "options" as exactly 4 non-empty strings and '
    '"correct_answer" as one option exactly. '
    'For "enumeration", provide "correct_answer" as a JSON array of at least 2 '
    'short expected items; do not provide multiple-choice options. '
    'For "problem", provide "correct_answer" as the concise final answer and '
    '"solution_steps" as a non-empty JSON array of worked, student-readable steps; '
    'do not provide multiple-choice options. '
    'You may add an optional "answer_format" naming the shape of "correct_answer", '
    'exactly one of: '
    + ", ".join(f'"{answer_format}"' for answer_format in ANSWER_FORMATS)
    + '. Omit "answer_format" entirely when unsure: it is detected automatically '
    'when absent, so a wrong declaration is worse than none.'
)

SYSTEM_PROMPT = (
    "You are an elite Computer Science professor writing an application-based exam. "
    "Analyze only the provided module text. Instead of asking for basic definitions, "
    "generate practical, conceptual, and situational questions. "
    "If 'PAST RELEVANT KNOWLEDGE' is provided, try to create at least one conceptual question "
    "that connects the current module's concepts to the past knowledge. "
    "Output a strictly formatted JSON object with a single key 'questions' containing an array of objects. "
    + CARD_FORMATS
)


def get_andy_prompt(target_count: int, question_style: str = "mixed") -> str:
    """Build a per-deck generation contract for the selected question style."""
    style_instruction = _question_style_instruction(question_style, target_count)
    return (
        f"You are Andy, an elite Computer Science study buddy. "
        f"Generate exactly {target_count} questions. "
        f"CRITICAL: Make them highly situational, practical, and scenario-based. "
        f"If 'PAST RELEVANT KNOWLEDGE' is provided, try to create at least one conceptual question "
        f"that connects the current module's concepts to the past knowledge. "
        f"{style_instruction} "
        f"Output a strictly formatted JSON object with a single key 'questions' containing an array of objects. "
        + CARD_FORMATS
    )


def _question_style_instruction(question_style: str, target_count: int) -> str:
    if question_style not in QUESTION_STYLES:
        raise ValueError(f"Unsupported question style: {question_style}")
    if question_style == "multiple_choice":
        return 'Generate only questions with "type": "multiple_choice".'
    if question_style == "enumeration":
        return 'Generate only questions with "type": "enumeration".'
    if question_style == "problem":
        return (
            'Generate only questions with "type": "problem". Problem questions must mirror '
            'the uploaded module\'s own problem wording, notation, values, and solution method. '
            'Do not invent generic textbook exercises disconnected from the taught material.'
        )
    if target_count >= 3:
        mix_requirement = "Include at least one multiple_choice, one enumeration, and one problem question."
    else:
        mix_requirement = "Use as much type variety as the requested count allows."
    return (
        'Generate a balanced mix of "multiple_choice", "enumeration", and "problem" questions. '
        + mix_requirement
        + " Every problem must mirror the uploaded module's own problem style, notation, and method."
    )

# ── Groq client ─────────────────────────────────────────────────────────────

def _get_client() -> Groq:
    """
    Create and return an authenticated Groq client.
    Checks environment variables first, then falls back to Streamlit secrets.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    api_key_file = os.environ.get("GROQ_API_KEY_FILE")
    secret_file_failed = False
    if not api_key and api_key_file:
        try:
            with open(api_key_file, encoding="utf-8") as source:
                # Strip: Docker secret files and most editors leave a trailing
                # newline, which would otherwise become part of the key and
                # fail auth while _groq_is_configured (which does strip)
                # still reports the key as present.
                api_key = source.read().strip()
        except OSError as read_error:
            # Swallowing this silently let a container whose mounted secret was
            # unreadable (the root-owned-secret failure of a95473d) fall through
            # to a key baked into the image, defeating the permission guard the
            # cutover checks. Fail loudly and do not fall back.
            secret_file_failed = True
            print(
                f"  [Error] GROQ_API_KEY_FILE is set to {api_key_file} but could not be read: "
                f"{read_error}. Refusing to fall back to any other key source."
            )

    # Fallback to local Streamlit secrets, for developer machines only. It is
    # deliberately skipped whenever GROQ_API_KEY_FILE was configured: in a
    # deployed container that variable is the single intended source, and a
    # silent fallback there hides a real misconfiguration.
    if not api_key and not api_key_file and not secret_file_failed:
        try:
            import tomllib  # Built-in in Python 3.11+
            secrets_path = os.path.join(".streamlit", "secrets.toml")
            if os.path.exists(secrets_path):
                with open(secrets_path, "rb") as f:
                    secrets = tomllib.load(f)
                    api_key = secrets.get("GROQ_API_KEY")
        except Exception:
            pass # Fall through to the error raise below

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not found in environment variables or .streamlit/secrets.toml. "
            "Please ensure your key is configured."
        )
    
    # Clean up any accidental whitespaces or quotes
    api_key = api_key.strip().strip('"').strip("'")
    
    return Groq(api_key=api_key)


# ── Text helpers ──────────────────────────────────────────────────────────────

def _chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """
    Split *text* into chunks of at most *max_chars* characters, breaking only
    on paragraph boundaries so that context is never cut mid-sentence.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    paragraphs = text.split("\n\n")
    current_chunk = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            for i in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[i : i + max_chars])
            continue

        if len(current_chunk) + len(paragraph) + 2 > max_chars:
            chunks.append(current_chunk.strip())
            current_chunk = paragraph
        else:
            current_chunk = (current_chunk + "\n\n" + paragraph).lstrip("\n")

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def _strip_json_fences(raw: str) -> str:
    """
    Remove markdown code fences to ensure pure JSON parsing.
    """
    pattern = r"[`]{3}(?:json)?\s*([\s\S]*?)[`]{3}"
    match = re.search(pattern, raw)
    if match:
        return match.group(1).strip()
    return raw.strip()


# ── LLM interaction ───────────────────────────────────────────────────────────

def _salvage_questions(raw_text: str) -> list[dict]:
    """
    Recover whole question objects from a response whose JSON does not parse.

    A truncated completion cuts off mid-object, so `json.loads` rejects the
    entire payload and the caller would otherwise discard a chunk's worth of
    perfectly good questions. Scan the `questions` array and return every
    object that closed cleanly, dropping only the incomplete tail.

    Returns an empty list when nothing can be recovered, so the caller's
    behaviour is unchanged in the genuinely unusable case.
    """
    marker = raw_text.find('"questions"')
    if marker == -1:
        return []
    start = raw_text.find("[", marker)
    if start == -1:
        return []

    recovered: list[dict] = []
    depth = 0
    in_string = False
    escaped = False
    object_start = -1

    for position in range(start + 1, len(raw_text)):
        character = raw_text[position]

        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character == "{":
            if depth == 0:
                object_start = position
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0 and object_start != -1:
                fragment = raw_text[object_start : position + 1]
                try:
                    candidate = json.loads(fragment)
                except json.JSONDecodeError:
                    pass
                else:
                    if isinstance(candidate, dict):
                        recovered.append(candidate)
                object_start = -1
        elif character == "]" and depth == 0:
            break

    return recovered


def _query_groq(client: Groq, text_chunk: str, system_prompt: str = SYSTEM_PROMPT) -> list[dict]:
    """
    Send a single *text_chunk* to Groq and return the parsed list of
    question dicts. Returns an empty list on any error.
    """
    prompt = (
        "Generate exam questions based ONLY on the following module content:\n\n"
        f"{text_chunk}"
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        )

        raw_text = response.choices[0].message.content
        cleaned = _strip_json_fences(raw_text)
        data = json.loads(cleaned)
        
        questions = data.get("questions", [])

        if not isinstance(questions, list):
            print("  [Warning] Groq returned JSON but 'questions' is not a list — skipping chunk.")
            return []

        return questions

    except json.JSONDecodeError as e:
        # A chunk that will not parse is recoverable: skip it and keep the
        # cards from the other chunks. Saving the raw response is a debugging
        # convenience and must never be able to fail the run. Writing it to the
        # working directory raised PermissionError under the container, whose
        # /app is not writable, so a single unparseable chunk aborted the whole
        # generation after other chunks had already produced valid cards.
        raw = raw_text if "raw_text" in locals() else "No response text"
        salvaged = _salvage_questions(raw) if raw != "No response text" else []
        if salvaged:
            print(
                f"  [Warning] JSON parse error: {e}. "
                f"Recovered {len(salvaged)} complete question(s) from the truncated response."
            )
        else:
            print(f"  [Warning] JSON parse error: {e}. Skipping this chunk.")
        try:
            debug_dir = Path(
                # .get(key, default) returns "" when the variable is SET but
                # empty, and Path("") resolves to the current directory, which
                # dropped debug dumps into the application root. Fall back on
                # emptiness, not just on absence.
                os.environ.get("ANDYHUB_EXTRACTION_CACHE_DIR", "").strip()
                or tempfile.gettempdir()
            )
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_path = debug_dir / "groq_raw_error.txt"
            debug_path.write_text(raw, encoding="utf-8")
            print(f"  [Warning] Raw response saved to {debug_path}.")
        except OSError as write_error:
            print(f"  [Warning] Could not save the raw response: {write_error}")
        return salvaged
    except Exception as e:
        print(f"  [Error] Groq request failed using {MODEL_NAME}: {e}")
        return []


# ── Card validation ───────────────────────────────────────────────────────────

def _validate_card(card: dict, index: int) -> bool:
    """
    Return True only if *card* has every required field in the correct shape.
    Logs a descriptive warning and returns False for every malformed entry.
    """
    required_keys = {"type", "question", "correct_answer"}

    if not isinstance(card, dict):
        print(f"  [Skipped] Card #{index}: not a dict.")
        return False

    missing = required_keys - card.keys()
    if missing:
        print(f"  [Skipped] Card #{index}: missing keys {missing}.")
        return False

    card_type = card.get("type")
    if card_type not in {"multiple_choice", "enumeration", "problem"}:
        print(f"  [Skipped] Card #{index}: unsupported type '{card_type}'.")
        return False

    if not isinstance(card.get("question"), str) or not card["question"].strip():
        print(f"  [Skipped] Card #{index}: 'question' must be a non-empty string.")
        return False

    # `answer_format` is optional. An absent key means "auto-detect", which is
    # how every card stored before this field existed keeps working. A present
    # key must be a real declaration, so a malformed one is rejected rather
    # than silently ignored.
    if "answer_format" in card:
        declared = card["answer_format"]
        if not isinstance(declared, str) or declared.strip() not in ANSWER_FORMATS:
            print(
                f"  [Skipped] Card #{index}: 'answer_format' must be omitted or one of "
                f"{', '.join(ANSWER_FORMATS)}; got {declared!r}."
            )
            return False

    if card_type == "multiple_choice":
        options = card.get("options")
        if not isinstance(options, list) or len(options) != 4:
            print(f"  [Skipped] Card #{index}: 'options' must be a list of exactly 4 strings.")
            return False

        if not all(isinstance(opt, str) and opt.strip() for opt in options):
            print(f"  [Skipped] Card #{index}: every option must be a non-empty string.")
            return False

        if card.get("correct_answer") not in options:
            print(
                f"  [Skipped] Card #{index}: 'correct_answer' does not match any option.\n"
                f"    correct_answer : {card.get('correct_answer')}\n"
                f"    options        : {options}"
            )
            return False
        return True

    if card_type == "enumeration":
        expected_items = card.get("correct_answer")
        if (
            not isinstance(expected_items, list)
            or len(expected_items) < 2
            or not all(isinstance(item, str) and item.strip() for item in expected_items)
        ):
            print(f"  [Skipped] Card #{index}: enumeration 'correct_answer' must be a list of at least 2 strings.")
            return False
        return True

    solution_steps = card.get("solution_steps")
    if not isinstance(card.get("correct_answer"), str) or not card["correct_answer"].strip():
        print(f"  [Skipped] Card #{index}: problem 'correct_answer' must be a non-empty final-answer string.")
        return False
    if not isinstance(solution_steps, list) or not solution_steps or not all(
        isinstance(step, str) and step.strip() for step in solution_steps
    ):
        print(f"  [Skipped] Card #{index}: problem 'solution_steps' must be a non-empty list of strings.")
        return False

    return True


def _card_storage_values(card: dict) -> tuple[str, object]:
    """Translate type-specific LLM fields into the existing database columns."""
    if card["type"] == "enumeration":
        expected_items = card["correct_answer"]
        # `options` is the authoritative JSON list used by the quiz UI. The
        # non-null legacy correct_answer column keeps the same JSON for
        # backward-safe storage without a schema migration.
        return json.dumps(expected_items), expected_items
    if card["type"] == "problem":
        final_answer = card["correct_answer"]
        payload = {
            "final_answer": final_answer,
            "solution_steps": card["solution_steps"],
        }
        # Only persist a declaration the model actually made; the key stays
        # absent otherwise so stored payloads match the pre-existing shape.
        declared = card.get("answer_format")
        if isinstance(declared, str) and declared.strip() in ANSWER_FORMATS:
            payload["answer_format"] = declared.strip()
        return final_answer, payload
    return card["correct_answer"], card["options"]


@dataclass(frozen=True)
class DeckPreparation:
    selected_files: tuple[str, ...]
    combined_text: str
    chunks: tuple[str, ...]


@dataclass(frozen=True)
class GenerationDependencies:
    extract_file: Callable[[str], str]
    create_client: Callable[[], Groq]
    get_context: Callable[[str, str], str]
    query_cards: Callable[[Groq, str, str], list[dict]]
    add_memory: Callable[[str, str, list[str]], None]
    persist_deck: Callable[[str, str, str, list[NewCard]], int]
    sleep: Callable[[float], None]


def prepare_custom_deck(
    selected_files: list[str],
    *,
    display_names: list[str] | None = None,
    extract_file: Callable[[str], str] = process_module_file_v2,
    uploads_directory: str = "uploads",
    report: Callable[[str], None] = print,
) -> DeckPreparation | None:
    """
    Extract selected modules and prepare stable chunks without LLM or storage I/O.

    *selected_files* are the names to READ from ``uploads_directory``. The API
    stores uploads under a content hash, so it passes `stored_filename` here and
    the user-facing names in *display_names*, which are used for provenance
    labels and for the persisted deck sources. When *display_names* is omitted
    the two are the same, which is what the local CLI path wants.
    """

    if display_names is None:
        display_names = list(selected_files)
    if len(display_names) != len(selected_files):
        raise ValueError("display_names must match selected_files one to one")

    report(f"\n[1/4] Processing {len(selected_files)} module(s)...")
    combined_text = ""
    for filename, display_name in zip(selected_files, display_names):
        file_path = os.path.join(uploads_directory, filename)
        if not os.path.exists(file_path) and os.path.exists(filename):
            file_path = filename
        text = extract_file(file_path)
        if not text.startswith("Error") and not text.startswith("Unsupported"):
            combined_text += f"\n\n--- Content from {display_name} ---\n\n" + text
        else:
            report(f"  [Warning] Skipping {display_name}: {text}")
    if len(combined_text) < 50:
        report("  [Abort] Not enough valid text extracted to generate meaningful questions.")
        return None
    chunks = tuple(_chunk_text(combined_text))
    report(f"  Extracted {len(combined_text):,} characters from all selected modules.")
    report(f"\n[2/4] Split into {len(chunks)} chunk(s) (max {MAX_CHUNK_CHARS:,} chars each).")
    return DeckPreparation(tuple(display_names), combined_text, chunks)


def validate_generated_cards(raw_cards: list[dict], total_questions: int) -> list[dict]:
    """Trim provider output and retain only cards matching the persisted contract."""

    # Validate first, then trim. Trimming first meant a malformed card inside
    # the first `total_questions` entries reduced the deck below the requested
    # size even when valid cards were waiting just past the cut, so a request
    # for 20 could return 18 while 20 good cards existed.
    valid_cards = [
        card
        for index, card in enumerate(raw_cards, start=1)
        if _validate_card(card, index)
    ]
    return valid_cards[:total_questions]


def persist_valid_cards(
    *,
    deck_name: str,
    subject: str,
    selected_files: tuple[str, ...],
    valid_cards: list[dict],
    persist_deck: Callable[[str, str, str, list[NewCard]], int],
) -> int:
    """Build the legacy storage payload then persist it in one transaction."""

    if not valid_cards:
        raise ValueError("A deck cannot be persisted without valid cards")
    cards: list[NewCard] = []
    for card in valid_cards:
        correct_answer, options = _card_storage_values(card)
        cards.append(NewCard(card["type"], card["question"], correct_answer, options))
    return persist_deck(deck_name, ", ".join(selected_files), subject, cards)


def default_generation_dependencies() -> GenerationDependencies:
    return GenerationDependencies(
        extract_file=process_module_file_v2,
        create_client=_get_client,
        get_context=get_historical_context,
        query_cards=_query_groq,
        add_memory=add_to_memory,
        persist_deck=create_deck_with_cards,
        sleep=time.sleep,
    )


def orchestrate_custom_deck(
    selected_files: list[str],
    deck_name: str,
    subject: str,
    total_questions: int,
    question_style: str = "mixed",
    *,
    dependencies: GenerationDependencies | None = None,
    report: Callable[[str], None] = print,
) -> int | None:
    """Coordinate extraction, memory, generation, validation, then transactional storage."""

    deps = dependencies or default_generation_dependencies()
    preparation = prepare_custom_deck(
        selected_files, extract_file=deps.extract_file, report=report
    )
    if preparation is None:
        return None
    questions_per_chunk = math.ceil(total_questions / len(preparation.chunks))
    report(f"\n[3/4] Andy is generating {total_questions} situational questions using '{MODEL_NAME}'...")
    client = deps.create_client()
    raw_cards: list[dict] = []
    for index, chunk in enumerate(preparation.chunks, start=1):
        report(f"  Chunk {index}/{len(preparation.chunks)} ...")
        augmented_chunk = chunk + deps.get_context(chunk, subject)
        raw_cards.extend(deps.query_cards(client, augmented_chunk, get_andy_prompt(questions_per_chunk, question_style)))
        if index < len(preparation.chunks):
            deps.sleep(2)
    deps.add_memory(deck_name, subject, list(preparation.chunks))
    valid_cards = validate_generated_cards(raw_cards, total_questions)
    report(f"\n[4/4] Validating and saving to database...")
    if not valid_cards:
        report("  [Abort] No valid cards were generated. Deck will not be created.")
        return None
    deck_id = persist_valid_cards(
        deck_name=deck_name,
        subject=subject,
        selected_files=preparation.selected_files,
        valid_cards=valid_cards,
        persist_deck=deps.persist_deck,
    )
    report(f"\n  Deck '{deck_name}' created successfully by Andy.")
    report(f"  Deck ID       : {deck_id}")
    report(f"  Cards saved   : {len(valid_cards)}")
    report(f"  Cards skipped : {len(raw_cards) - len(valid_cards)}")
    if len(valid_cards) < total_questions:
        report(
            f"  [Notice] {total_questions} questions were requested but only "
            f"{len(valid_cards)} valid cards were produced from "
            f"{len(raw_cards)} provider responses."
        )
    return deck_id


def generate_custom_deck(
    selected_files: list[str],
    deck_name: str,
    subject: str,
    total_questions: int,
    question_style: str = "mixed",
) -> int | None:
    """Compatibility façade for Streamlit; delegates to the injectable orchestrator."""

    return orchestrate_custom_deck(
        selected_files=selected_files,
        deck_name=deck_name,
        subject=subject,
        total_questions=total_questions,
        question_style=question_style,
    )


# ── Core public function ──────────────────────────────────────────────────────

def generate_deck_from_file(
    file_path: str,
    deck_name: str,
    subject: str,
    question_style: str = "mixed",
) -> int | None:
    """
    Full pipeline for a single file. Includes RAG context retrieval and insertion.
    """
    print(f"\n[1/4] Extracting text from: {file_path}")
    raw_text = process_module_file_v2(file_path)

    if raw_text.startswith("Error") or raw_text.startswith("Unsupported"):
        print(f"  [Abort] Extraction failed: {raw_text}")
        return None

    text_length = len(raw_text)
    print(f"  Extracted {text_length:,} characters.")

    if text_length < 50:
        print("  [Abort] Extracted text is too short to generate meaningful questions.")
        return None

    chunks = _chunk_text(raw_text)
    print(f"\n[2/4] Split into {len(chunks)} chunk(s) (max {MAX_CHUNK_CHARS:,} chars each).")

    print(f"\n[3/4] Querying Groq using '{MODEL_NAME}' ({len(chunks)} request(s))...")
    client = _get_client()

    all_raw_cards: list[dict] = []
    for i, chunk in enumerate(chunks, start=1):
        print(f"  Chunk {i}/{len(chunks)} ({len(chunk):,} chars) ...", end=" ", flush=True)
        
        # --- RAG RETRIEVAL STEP ---
        historical_context = get_historical_context(chunk, subject)
        augmented_chunk = chunk + historical_context
        
        cards = _query_groq(client, augmented_chunk, system_prompt=get_andy_prompt(1, question_style))
        
        print(f"received {len(cards)} card(s).")
        all_raw_cards.extend(cards)

    # --- RAG INGESTION STEP ---
    module_filename = os.path.basename(file_path)
    add_to_memory(module_filename, subject, chunks)

    print(f"  Total raw cards received: {len(all_raw_cards)}")

    print(f"\n[4/4] Validating and saving to database...")

    valid_cards = [
        card for i, card in enumerate(all_raw_cards, start=1)
        if _validate_card(card, i)
    ]

    if not valid_cards:
        print("  [Abort] No valid cards were generated. Deck will not be created.")
        return None

    deck_id = create_deck(
        name=deck_name,
        modules_included=module_filename,
        subject=subject,
    )

    for card in valid_cards:
        correct_answer, options = _card_storage_values(card)
        add_card(
            deck_id=deck_id,
            card_type=card["type"],
            question=card["question"],
            correct_answer=correct_answer,
            options=options,
        )

    print(f"\n  Deck '{deck_name}' created successfully.")
    print(f"  Deck ID       : {deck_id}")
    print(f"  Cards saved   : {len(valid_cards)}")
    print(f"  Cards skipped : {len(all_raw_cards) - len(valid_cards)}")

    return deck_id


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) == 4:
        TEST_FILE    = sys.argv[1]
        TEST_DECK    = sys.argv[2]
        TEST_SUBJECT = sys.argv[3]
    elif len(sys.argv) == 1:
        TEST_FILE    = "sample_module.pdf"   
        TEST_DECK    = "Sample CS Deck"
        TEST_SUBJECT = "Computer Science"
    else:
        print("Usage: python generator.py [<file_path> <deck_name> <subject>]")
        sys.exit(1)

    if not os.path.isfile(TEST_FILE):
        print(f"[Error] File not found: '{TEST_FILE}'")
        print("Please set TEST_FILE to the path of a real PDF or PPTX file.")
        sys.exit(1)

    deck_id = generate_deck_from_file(
        file_path=TEST_FILE,
        deck_name=TEST_DECK,
        subject=TEST_SUBJECT,
    )

    if deck_id is not None:
        print(f"\n[Done] Deck ID {deck_id} is ready to use in the quiz app.")
    else:
        print("\n[Done] No deck was created.")
