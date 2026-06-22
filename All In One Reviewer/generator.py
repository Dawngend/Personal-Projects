import os
import json
import re
import sys
import time
import math
from groq import Groq
from rag_engine import add_to_memory, get_historical_context
from extractor import process_module_file_v2
from database import create_deck, add_card

# ── Constants & Configuration ────────────────────────────────────────────────

# MODEL CHOICES: 
MODEL_NAME = "llama-3.3-70b-versatile"

MAX_CHUNK_CHARS = 12_000

SYSTEM_PROMPT = (
    "You are an elite Computer Science professor writing a tricky "
    "application-based exam. Analyze the provided module text. Instead of "
    "asking for basic definitions, you MUST generate highly practical, conceptual, and "
    "situational scenario-based questions. "
    "If 'PAST RELEVANT KNOWLEDGE' is provided, try to create at least one conceptual question "
    "that connects the current module's concepts to the past knowledge. "
    "Output a strictly formatted JSON object with a single key 'questions' containing an array of objects. "
    'Each object must have: "type" (must be "multiple_choice"), "question" '
    '(string), "options" (array of exactly 4 strings), and '
    '"correct_answer" (string matching one option exactly).'
)


def get_andy_prompt(target_count: int) -> str:
    return (
        f"You are Andy, an elite Computer Science study buddy. "
        f"Generate exactly {target_count} multiple-choice flashcards. "
        f"CRITICAL: Make them highly situational, practical, and scenario-based. "
        f"If 'PAST RELEVANT KNOWLEDGE' is provided, try to create at least one conceptual question "
        f"that connects the current module's concepts to the past knowledge. "
        f"Output a strictly formatted JSON object with a single key 'questions' containing an array of objects. "
        f'Each object must have: "type" (must be "multiple_choice"), "question", "options" (4 strings), and "correct_answer".'
    )

# ── Groq client ─────────────────────────────────────────────────────────────

def _get_client() -> Groq:
    """
    Create and return an authenticated Groq client.
    Checks environment variables first, then falls back to Streamlit secrets.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    
    # Fallback to loading Streamlit secrets if running locally
    if not api_key:
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
        print(f"  [Warning] JSON parse error: {e}. Raw response saved to 'groq_raw_error.txt'.")
        with open("groq_raw_error.txt", "w", encoding="utf-8") as f:
            f.write(raw_text if 'raw_text' in locals() else "No response text")
        return []
    except Exception as e:
        print(f"  [Error] Groq request failed using {MODEL_NAME}: {e}")
        return []


# ── Card validation ───────────────────────────────────────────────────────────

def _validate_card(card: dict, index: int) -> bool:
    """
    Return True only if *card* has every required field in the correct shape.
    Logs a descriptive warning and returns False for every malformed entry.
    """
    required_keys = {"type", "question", "options", "correct_answer"}

    if not isinstance(card, dict):
        print(f"  [Skipped] Card #{index}: not a dict.")
        return False

    missing = required_keys - card.keys()
    if missing:
        print(f"  [Skipped] Card #{index}: missing keys {missing}.")
        return False

    if card.get("type") != "multiple_choice":
        print(f"  [Skipped] Card #{index}: type is '{card.get('type')}', expected 'multiple_choice'.")
        return False

    options = card.get("options")
    if not isinstance(options, list) or len(options) != 4:
        print(f"  [Skipped] Card #{index}: 'options' must be a list of exactly 4 strings.")
        return False

    if not all(isinstance(opt, str) for opt in options):
        print(f"  [Skipped] Card #{index}: every option must be a string.")
        return False

    if card.get("correct_answer") not in options:
        print(
            f"  [Skipped] Card #{index}: 'correct_answer' does not match any option.\n"
            f"    correct_answer : {card.get('correct_answer')}\n"
            f"    options        : {options}"
        )
        return False

    return True


def generate_custom_deck(
    selected_files: list[str],
    deck_name: str,
    subject: str,
    total_questions: int,
) -> int | None:
    """
    Build a deck from multiple selected files and target a specific question count.
    Includes persistent memory (RAG) to connect past modules to current ones.
    """
    print(f"\n[1/4] Processing {len(selected_files)} module(s)...")
    combined_text = ""

    for filename in selected_files:
        file_path = os.path.join("uploads", filename)
        if not os.path.exists(file_path) and os.path.exists(filename):
            file_path = filename

        text = process_module_file_v2(file_path)
        if not text.startswith("Error") and not text.startswith("Unsupported"):
            combined_text += f"\n\n--- Content from {filename} ---\n\n" + text
        else:
            print(f"  [Warning] Skipping {filename}: {text}")

    text_length = len(combined_text)
    print(f"  Extracted {text_length:,} characters from all selected modules.")

    if text_length < 50:
        print("  [Abort] Not enough valid text extracted to generate meaningful questions.")
        return None

    chunks = _chunk_text(combined_text)
    print(f"\n[2/4] Split into {len(chunks)} chunk(s) (max {MAX_CHUNK_CHARS:,} chars each).")

    questions_per_chunk = math.ceil(total_questions / len(chunks))

    print(f"\n[3/4] Andy is generating {total_questions} situational questions using '{MODEL_NAME}'...")
    client = _get_client()
    all_raw_cards: list[dict] = []

    for i, chunk in enumerate(chunks, start=1):
        print(f"  Chunk {i}/{len(chunks)} ...", end=" ", flush=True)
        
        # --- RAG RETRIEVAL STEP ---
        historical_context = get_historical_context(chunk, subject)
        augmented_chunk = chunk + historical_context
        
        prompt = get_andy_prompt(questions_per_chunk)
        cards = _query_groq(client, augmented_chunk, system_prompt=prompt)
        
        print(f"received {len(cards)} card(s).")
        all_raw_cards.extend(cards)

        if i < len(chunks):
            time.sleep(2)

    # --- RAG INGESTION STEP ---
    add_to_memory(deck_name, subject, chunks)

    all_raw_cards = all_raw_cards[:total_questions]
    print(f"  Total raw cards finalized for validation: {len(all_raw_cards)}")

    print(f"\n[4/4] Validating and saving to database...")

    valid_cards = [
        card for i, card in enumerate(all_raw_cards, start=1)
        if _validate_card(card, i)
    ]

    if not valid_cards:
        print("  [Abort] No valid cards were generated. Deck will not be created.")
        return None

    modules_included_string = ", ".join(selected_files)

    deck_id = create_deck(
        name=deck_name,
        modules_included=modules_included_string,
        subject=subject,
    )

    for card in valid_cards:
        add_card(
            deck_id=deck_id,
            card_type=card["type"],
            question=card["question"],
            correct_answer=card["correct_answer"],
            options=card["options"],
        )

    print(f"\n  Deck '{deck_name}' created successfully by Andy.")
    print(f"  Deck ID       : {deck_id}")
    print(f"  Cards saved   : {len(valid_cards)}")
    print(f"  Cards skipped : {len(all_raw_cards) - len(valid_cards)}")

    return deck_id


# ── Core public function ──────────────────────────────────────────────────────

def generate_deck_from_file(
    file_path: str,
    deck_name: str,
    subject: str,
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
        
        cards = _query_groq(client, augmented_chunk)
        
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
        add_card(
            deck_id=deck_id,
            card_type=card["type"],
            question=card["question"],
            correct_answer=card["correct_answer"],
            options=card["options"],
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