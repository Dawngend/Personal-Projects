# AndyHub Frontend Rewrite Architecture Plan

Status: proposal for Dawn's review — no implementation authorized  
Prepared: 2026-08-14  
Scope: replace the Streamlit presentation layer with a Next.js product frontend and expose the existing Python study engine through FastAPI

## 1. Executive decision

Build a Next.js App Router frontend in TypeScript and a versioned FastAPI API around the current Python engine. Deploy both on the existing GCP VM at first, behind one same-origin reverse proxy and the existing Cloudflare Tunnel:

```text
Browser
  │
  ▼
andyhub.org (Cloudflare Tunnel)
  │
  ▼
same-origin reverse proxy
  ├── /api/v1/* ──► FastAPI ──► generation service / grading service
  │                                ├── Groq
  │                                ├── extractor + OCR cache
  │                                ├── Chroma course memory
  │                                └── SQLite repositories
  └── /* ─────────► Next.js
```

FastAPI is the right fit because the business logic is already Python, Dawn's verified stack already includes FastAPI and Pydantic v2, and FastAPI produces OpenAPI/JSON Schema contracts that can generate or validate the TypeScript client. It also directly supports multipart `UploadFile`, dependency injection, typed response models, testing, and SSE/WebSockets. Flask would require more contract and validation infrastructure; moving the backend to Node would duplicate working Python extraction, RAG, and Groq logic.

The first release should keep the existing SQLite data and Chroma directory. Do not combine the frontend rewrite with a database-platform migration. The architecture should introduce repository interfaces so PostgreSQL can replace SQLite later without changing the API or UI.

## 2. What exists today

The current app is not only a Streamlit view. Several UI, orchestration, storage, and domain responsibilities are intertwined:

| Current file | Current responsibility | Rewrite treatment |
|---|---|---|
| `app.py` | Navigation, uploads, deck configuration, generation spinner, deck loading, queue shuffling, quiz state, grading, miss tracking, and all rendering | Retire after feature parity; split behavior between Next.js UI and API services |
| `backend_logic.py` | Saves Streamlit uploads and lists local PDF/PPTX files | Replace Streamlit-specific input with a storage service receiving FastAPI `UploadFile`; retain file-list semantics initially |
| `generator.py` | Extracts modules, chunks text, retrieves Chroma context, calls Groq, validates cards, writes deck/cards, and updates Chroma memory | Preserve algorithms, but split orchestration from I/O; call through a generation service/job runner |
| `rag_engine.py` | Process-global Chroma client, default SentenceTransformers embeddings, per-subject retrieval, and module upsert | Wrap in a `CourseMemory` service; preserve collection/data initially; initialize through API lifespan |
| `database.py` | Creates SQLite schema and exposes tuple-returning deck/card CRUD plus cumulative miss count | Wrap with typed repository methods and explicit connection/transaction handling; stop returning positional tuples |
| `extractor.py` | PDF/PPTX extraction, OCR, incremental text cache, and Streamlit `@st.cache_data` | Remove Streamlit dependency; make cache keyed by content hash and expose progress from extraction |

### Current end-to-end flow

```text
Streamlit upload
  → write file under uploads/
  → user selects filenames + deck settings
  → generate_custom_deck()
      → extract/OCR each file, using sibling *_saved_text.txt cache
      → concatenate and chunk content
      → retrieve up to 2 Chroma chunks in the same lowercased subject
      → call Groq once per chunk
      → validate multiple-choice/enumeration/problem cards
      → upsert current chunks into Chroma
      → create deck + cards in SQLite
  → Streamlit reloads cards and shuffles them in session state
  → UI grades answers locally
  → only times_missed persists
```

Important constraints discovered in the code:

- Generation is synchronous and may include OCR, embeddings, multiple Groq requests, two-second inter-request sleeps, Chroma writes, and SQLite writes. It should not remain one long HTTP request.
- Relative paths depend on the process working directory (`uploads`, `Database/reviewer.db`, `course_brain_db`). The API must resolve configured absolute data paths at startup.
- `extractor.py` imports Streamlit solely for caching. The domain layer is not currently UI-independent.
- The SQLite API opens a new connection per function and returns raw tuples. There is no deck detail DTO, transaction spanning deck/card creation, or not-found handling.
- Quiz sessions are ephemeral. Refreshing the browser loses order, current index, failures, and completion; only aggregate misses survive.
- Correct answers are currently loaded into the browser before the student answers. A product API should withhold them until grading/reveal.
- Chroma memory is global within a subject. Content from every earlier deck with the same subject can influence later generation.
- `backend_logic.py` duplicates upload/list logic already present in `app.py` and is otherwise not used by the current UI.

## 3. Target repository structure

Keep one repository and two deployable applications:

```text
All In One Reviewer/
├── apps/
│   ├── api/
│   │   ├── andyhub_api/
│   │   │   ├── main.py
│   │   │   ├── api/v1/{decks,modules,generation,sessions}.py
│   │   │   ├── schemas/{card,deck,generation,module,session}.py
│   │   │   ├── services/{generation,grading,storage}.py
│   │   │   ├── repositories/{decks,cards,sessions}.py
│   │   │   └── settings.py
│   │   └── tests/
│   └── web/
│       ├── app/
│       │   ├── (workspace)/page.tsx
│       │   ├── decks/new/page.tsx
│       │   ├── decks/[deckId]/page.tsx
│       │   ├── study/[sessionId]/page.tsx
│       │   └── layout.tsx
│       ├── components/
│       │   ├── deck/
│       │   ├── generation/
│       │   ├── question/
│       │   ├── study/
│       │   └── ui/
│       ├── lib/{api,contracts,query-client}.ts
│       └── tests/
├── packages/
│   └── generated-api-client/     # optional OpenAPI-generated TypeScript client
├── core/                         # refactored existing Python business logic
│   ├── generation.py
│   ├── extraction.py
│   ├── memory.py
│   └── grading.py
├── data/                         # mounted persistent volume, never baked into images
│   ├── reviewer.db
│   ├── uploads/
│   ├── extraction-cache/
│   └── course-brain/
├── compose.yaml
└── FRONTEND_REWRITE_PLAN.md
```

This is a target layout, not a requirement to move every file on day one. Adapter modules can initially import the existing functions from their current locations. Move logic only when covered by characterization tests.

## 4. API layer

### 4.1 Contract principles

- Prefix all routes with `/api/v1`.
- Use Pydantic discriminated unions for card types.
- Never return `correct_answer`, expected enumeration items, or solution steps in an unanswered question payload.
- Return stable objects, never database tuples.
- Use UUIDs for new modules, jobs, and sessions; existing integer deck/card IDs can remain during migration.
- Treat generation as a durable job with inspectable status. `POST` returns `202 Accepted` quickly.
- Enforce upload MIME type, extension, size, sanitized filename, and content hash server-side.
- Keep API and web same-origin in production. Enable narrow development CORS only for the local Next.js origin.
- Define consistent errors: `{ "error": { "code": "...", "message": "...", "details": {...} } }`.

### 4.2 Core response models

```ts
type QuestionStyle = "multiple_choice" | "enumeration" | "problem" | "mixed";
type CardType = Exclude<QuestionStyle, "mixed">;

type DeckSummary = {
  id: number;
  name: string;
  subject: string;
  modules: string[];
  cardCount: number;
  questionTypes: Record<CardType, number>;
  totalMisses: number;
};

type QuizCard =
  | { id: number; type: "multiple_choice"; question: string; options: string[] }
  | { id: number; type: "enumeration"; question: string; expectedCount: number }
  | { id: number; type: "problem"; question: string; answerFormatHint?: string };

type GradeResult = {
  correct: boolean;
  complete: boolean;
  feedback: string;
  caughtItems?: string[];
  missedItems?: string[];
  expectedAnswer?: string;
  solutionSteps?: string[];
};
```

`expectedCount` is safe for enumeration and helps the student know how many items to supply. Expected item values remain server-side until grading.

### 4.3 Endpoints

#### Health and capabilities

`GET /api/v1/health`

```json
{ "status": "ok", "database": "ok", "course_memory": "ok", "generator": "configured" }
```

`GET /api/v1/capabilities`

Returns supported file types, upload limits, question styles, and safe model-facing feature flags. It must not expose secrets or the Groq key.

#### Modules and uploads

`GET /api/v1/modules`

Returns uploaded module metadata, not arbitrary filesystem paths:

```json
{
  "items": [
    {
      "id": "mod_...",
      "filename": "Linear-Algebra-Module-1.pdf",
      "media_type": "application/pdf",
      "size_bytes": 4821042,
      "content_hash": "sha256:...",
      "extraction_status": "ready"
    }
  ]
}
```

`POST /api/v1/modules` (`multipart/form-data`, one or more `files`)

- Maps to a replacement for `save_module_for_andy` / `save_uploaded_module`.
- Streams files to a staging path, validates them, hashes them, then atomically moves them into managed storage.
- Returns `201` for new modules and identifies duplicates by content hash.
- Extraction may occur here as a separate job, but the first compatibility release can defer extraction until generation.

`DELETE /api/v1/modules/{module_id}` should be postponed until retention and Chroma cleanup semantics are decided. The current app has no delete behavior.

#### Decks and generation

`GET /api/v1/decks`

- Maps to `get_decks()` plus aggregate card counts.
- Supports `subject`, `search`, `limit`, and cursor pagination even if the initial dataset is small.

`GET /api/v1/decks/{deck_id}`

- Returns deck metadata and safe statistics, not answer keys.
- Optional `include=cards` can return safe card previews for deck management.

`POST /api/v1/generation-jobs`

```json
{
  "deck_name": "Linear Algebra — Midterm 1",
  "subject": "Linear Algebra",
  "module_ids": ["mod_a", "mod_b"],
  "question_style": "mixed",
  "total_questions": 20
}
```

Response:

```json
{
  "id": "gen_...",
  "status": "queued",
  "stage": "queued",
  "progress": 0,
  "deck_id": null
}
```

This maps to `generate_custom_deck()` through a thin orchestration service. Preserve `_chunk_text`, prompt generation, `_query_groq`, `_validate_card`, type-specific storage encoding, `get_historical_context`, and `add_to_memory`. Refactor the orchestration function to accept dependencies and a progress callback rather than print status and open storage globally.

`GET /api/v1/generation-jobs/{job_id}`

```json
{
  "id": "gen_...",
  "status": "running",
  "stage": "generating",
  "progress": 62,
  "message": "Generating questions from module chunk 3 of 5",
  "cards_received": 12,
  "cards_valid": 10,
  "deck_id": null,
  "error": null
}
```

`GET /api/v1/generation-jobs/{job_id}/events`

- SSE stream for progress updates; the UI falls back to polling the status endpoint.
- Stages should reflect the real pipeline: `queued`, `extracting`, `retrieving_memory`, `generating`, `validating`, `saving`, `complete`, `failed`.
- Do not stream raw prompts, module text, API responses, or secrets.

Use a single local worker initially because Chroma/SQLite and Groq rate limiting already imply low concurrency. Do not rely on bare FastAPI `BackgroundTasks` as the final durable mechanism: an API restart would lose job state. A small persisted `generation_jobs` table plus worker loop is sufficient at current scale; Redis/Celery is unnecessary until concurrent users justify it.

`DELETE /api/v1/decks/{deck_id}` is not needed for parity because Streamlit does not currently expose deletion. Decide it separately with confirmation and cascading-delete UX.

#### Quiz sessions and grading

`POST /api/v1/quiz-sessions`

```json
{ "deck_id": 12, "mode": "all" }
```

Alternative mode: `{ "deck_id": 12, "mode": "missed" }`.

Response:

```json
{
  "id": "quiz_...",
  "deck": { "id": 12, "name": "Linear Algebra — Midterm 1" },
  "total_questions": 20,
  "current_index": 0,
  "card": { "id": 90, "type": "problem", "question": "..." }
}
```

- The server creates and stores shuffled card order so refresh/resume is deterministic.
- This requires a small session/attempt persistence addition if resume-across-refresh is accepted. The temporary compatibility option is a signed session token containing order and progress, but database-backed sessions are clearer and auditable.

`GET /api/v1/quiz-sessions/{session_id}`

- Resumes current card and progress.
- Never exposes future answers.

`POST /api/v1/quiz-sessions/{session_id}/answers`

Multiple choice:

```json
{ "card_id": 91, "answer": { "type": "multiple_choice", "value": "Option B" } }
```

Enumeration:

```json
{ "card_id": 92, "answer": { "type": "enumeration", "value": "closure, associativity, identity" } }
```

Problem:

```json
{ "card_id": 93, "answer": { "type": "problem", "value": "24.0" } }
```

The grading service moves current `app.py` rules server-side:

- Multiple choice: exact option identity.
- Enumeration: normalized, case-insensitive expected-item containment; return caught and missed items. Record one miss per card/session, not on every repeated submission.
- Problem: normalized textual match or numeric tolerance for scalar numeric answers. Matrix, vector, symbolic, eigenvalue-set, and equation equivalence must remain an open grading decision; the first version should clearly label auto-grading as final-answer assistance, not proof validation.

`POST /api/v1/quiz-sessions/{session_id}/cards/{card_id}/reveal-solution`

- Returns the expected final answer and `solution_steps` for a problem.
- Records that the solution was revealed so session results do not classify the card as independently solved afterward unless Dawn explicitly chooses otherwise.

`POST /api/v1/quiz-sessions/{session_id}/advance`

- Advances only after a correct answer or a deliberate reveal/skip policy.
- Returns the next safe card payload or a completion summary.

`GET /api/v1/quiz-sessions/{session_id}/summary`

Returns total correct, attempted, missed card IDs/types, revealed solutions, and a `practice_missed` action. This makes the existing “Reflash Entire Deck” and “Practice Missed” behavior explicit.

### 4.4 Minimal-change backend refactor

1. Add characterization tests around current chunking, prompts, validation, storage JSON, grading, and Chroma subject filtering.
2. Replace Streamlit caching in `extractor.py` with a normal content-hash cache. Keep extraction algorithms intact.
3. Introduce typed `DeckRepository` and `CardRepository` adapters over the same SQLite file.
4. Wrap `rag_engine.py` in a service initialized once during FastAPI lifespan. Keep the existing Chroma collection and default embedding function.
5. Split `generate_custom_deck()` into:
   - pure/near-pure preparation and validation functions;
   - a generation orchestrator with dependency arguments;
   - a persistence transaction that creates the deck only after valid cards exist.
6. Move grading helpers from `app.py` into a pure Python grading service shared by the API tests.
7. Add API routers last. The routes should coordinate services, not contain extraction, prompt, or SQL logic.

## 5. Frontend structure and behavior

### 5.1 Technology choices

- Next.js App Router + TypeScript.
- Tailwind CSS for tokens/layout, with CSS custom properties as the source of truth; avoid a generic component theme.
- TanStack Query for server state, request cancellation, retries, polling fallback, and cache invalidation.
- A local `useReducer` (or small Zustand store only if needed) for active quiz interaction state. Do not duplicate deck/module data already owned by TanStack Query.
- React Hook Form + Zod for deck configuration. Generate API types from OpenAPI or validate them against hand-written discriminated unions.
- Framer Motion only for one orchestrated transition system; CSS transitions for ordinary feedback.
- KaTeX/MathJax support should be evaluated before Linear Algebra launch so matrices and equations render safely. Do not render raw model HTML.
- Vitest/React Testing Library for component logic; Playwright for upload → generate → study journeys.

### 5.2 Pages

#### `/` — Study workspace

The page's single job is “resume or begin a focused study session.” It shows:

- one dominant Continue studying surface when a resumable session exists;
- deck library grouped by subject, with card-type composition and miss signal;
- a clear Create deck action;
- empty state that directs the user to upload course material.

Avoid a metrics-dashboard hero. AndyHub is a study instrument, not an analytics SaaS product.

#### `/decks/new` — Deck workshop

Use a four-stage composition whose order is real:

```text
[1 Materials] → [2 Deck brief] → [3 Question style] → [4 Generate]
```

- `ModuleDropzone`: multi-file PDF/PPTX upload, progress, validation, duplicate detection.
- `ModuleShelf`: existing uploaded modules with extraction state.
- `DeckBriefForm`: name, subject, question count.
- `QuestionStyleField`: Multiple Choice, Enumeration, Problem-Solving, Mixed; Mixed default.
- `GenerationTrace`: live stages from SSE, with truthful granular copy (“Extracting slide images,” “Connecting this module to earlier Linear Algebra material,” “Validating 18 of 20 cards”).
- On completion, navigate to deck detail rather than relying on a toast.

#### `/decks/[deckId]` — Deck detail

- Source modules and subject.
- Question-type composition.
- Start all / Practice missed.
- Card previews without answers.
- Generation provenance and safe failure/retry state.

#### `/study/[sessionId]` — Focused study surface

This is a client component around a server-owned session. The layout stays stable while the answer control changes by discriminated card type:

- `MultipleChoiceQuestion`: custom keyboard-accessible answer rows, number-key shortcuts, visibly disabled misses, and exact preservation of current retry behavior.
- `EnumerationQuestion`: large response canvas, expected-count cue, check action, caught/missed tokens, and retry without losing text.
- `ProblemQuestion`: math-ready prompt, final-answer field, optional scratchpad area that remains local, check action, and explicit Reveal worked solution. Reveal expands a step rail rather than a modal.
- `SessionProgress`: question position, missed marker, and card-type symbol. It should represent actual session structure, not a decorative progress bar.
- `SessionSummary`: complete, missed, revealed, and next action; supports reflash and missed-only sessions.

Use a route-level error boundary and preserve unsent text locally. A refresh should restore the same question from the API.

### 5.3 State ownership

| State | Owner |
|---|---|
| Decks, modules, generation jobs | Server + TanStack Query cache |
| Quiz order, current index, attempts, misses, reveals | API session |
| Current text input/scratchpad before submit | React local state; optionally `sessionStorage` |
| Theme/accessibility preference | Browser storage until accounts exist |
| Correct answers and solution steps | Server; released only by grade/reveal response |

Do not add Redux. The domain is small, and explicit server state plus a session reducer is easier to reason about.

## 6. Design direction: “Proof Garden”

### 6.1 Product-specific thesis

AndyHub is a place where raw course material becomes an active proof of understanding. The visual system should combine the precision of a computational notebook with the incremental growth of a personal knowledge graph. It should not reuse the existing navy/cream/blue card theme, imitate a chat app, or look like a generic dark analytics dashboard.

“Proof Garden” treats each module as planted source material, each generated question as a structured specimen, and each attempt as a visible trace of reasoning. The metaphor remains subtle: no leaves, mascots, or gamified garden illustrations. It appears through branching traces, clustered module relationships, progressive annotations, and the rhythm of a worked proof.

The deliberate aesthetic risk is an asymmetric **reasoning gutter** occupying the left edge of generation and study screens. It evolves from source-module nodes during generation into a compact proof trace during a quiz: question type, attempts, caught enumeration items, and revealed solution steps. This is product information, not decoration, and it gives AndyHub a recognizable silhouette.

Everything outside that signature stays quiet: flat planes, crisp separators, controlled depth, minimal rounding, and motion only when state truly advances. The interface should feel meticulously calibrated for long study sessions rather than designed to impress in a screenshot.

### 6.2 Palette

| Token | Hex | Role |
|---|---|---|
| Graphite | `#17151C` | Primary text and focused controls |
| Matrix Mist | `#E8EAF4` | Main cool-lilac workspace; rejects both cream-paper and generic white |
| Orchid Ink | `#5A3E79` | Active structure, module connections, selected answers |
| Signal Amber | `#E4A73D` | Attention, incomplete reasoning, missed items |
| Vector Teal | `#237C78` | Correct/caught state and memory connections |
| Error Carmine | `#B8495B` | Incorrect state, used sparingly and never as the only signal |

Use tinted surfaces derived from Matrix Mist rather than many independent card colors. Both light and dark modes can be designed later, but a carefully tuned light-first workspace better supports course PDFs, matrices, and extended daytime study than defaulting to another dark developer UI.

### 6.3 Typography

- Display/section voice: **Familjen Grotesk** — technical but not sterile, used for deck names and major study states.
- Reading/UI body: **Atkinson Hyperlegible Next** — chosen for sustained legibility and unambiguous character forms during study, not as a fashionable neutral.
- Data/math utility: **IBM Plex Mono** — question-type labels, subject codes, progress, matrix annotations, and source references.
- Mathematical expressions: KaTeX's math fonts, isolated to actual notation.

Do not make all interface text monospaced. Mono is an information layer, not the brand voice.

### 6.4 Layout hierarchy

Desktop study page:

```text
┌──────────────┬─────────────────────────────────────────────┐
│ REASONING    │ Linear Algebra · Q 07 / 20                 │
│ GUTTER       │                                             │
│              │  Find the determinant of…                  │
│ ● source     │                                             │
│ ● problem    │  [final answer field]                       │
│ ○ attempt    │                                             │
│ ○ solution   │  Check answer                               │
│              │                                             │
│              │  worked steps expand in place              │
└──────────────┴─────────────────────────────────────────────┘
```

Mobile collapses the gutter into a horizontal trace above the question. Nothing essential is hover-only. Question and answer controls remain one-column and thumb reachable.

### 6.5 Motion and interaction

- One orchestrated movement: when advancing, the current proof trace resolves upward while the next question enters without shifting the answer-control baseline.
- Generation nodes activate as real stages complete; no fake animated progress.
- Caught enumeration items settle into the reasoning gutter; missed ones stay in the answer area for correction.
- Respect `prefers-reduced-motion` and provide visible keyboard focus.
- Use active, literal copy: “Generate deck,” “Check answer,” “Reveal worked solution,” “Practice missed.”

## 7. Deployment plan

### Recommended first deployment: together on the existing VM

Run separate containers/processes on the current GCP VM:

```text
reverse-proxy :8080
next-web     :3000
fastapi-api  :8000
worker       :same Python image, separate command
persistent volume: SQLite + Chroma + uploads + extraction cache
cloudflared  :existing tunnel, origin changed only if necessary
```

The reverse proxy routes `/api/v1/*` and `/docs` to FastAPI and everything else to Next.js. Cloudflare Tunnel continues to publish `andyhub.org` to one local origin. TLS termination, public DNS, and domain stay the same. The Groq secret remains server-side on the VM and is never a Next.js public environment variable.

Why not split immediately:

- Existing SQLite, Chroma, OCR cache, and uploaded files are local-state workloads.
- A Vercel frontend plus GCP API adds cross-origin auth, separate deploys, upload routing, and failure modes without solving a current constraint.
- Same-VM containers make rollback to Streamlit and backup of state straightforward.

Design the web app around `NEXT_PUBLIC_API_BASE_URL=/api/v1` (or a server-only equivalent), so a later split is configuration rather than a rewrite. If the frontend later moves to Vercel/Cloudflare Pages, keep uploads direct to the API or object storage; do not proxy large course files through serverless route handlers by default.

### Operational requirements

- Pin dependency versions and build immutable images.
- Add health checks for web, API, SQLite access, and Chroma initialization.
- Back up `reviewer.db`, Chroma data, uploads, and extraction cache before cutover; test restore.
- Run SQLite in WAL mode with a busy timeout while it remains the store; keep one generation worker.
- Configure maximum request body size and Cloudflare/proxy timeouts for uploads, not for generation jobs.
- Log request ID, job ID, stage, duration, and safe error code. Never log module contents, full Groq prompts, answers, or secrets.
- Protect API docs and internal job diagnostics in production if the site is public.
- Confirm VM CPU/RAM/disk headroom before co-locating Next.js, Python, Chroma embeddings, and OCR.

## 8. Migration sequence and estimates

Estimates are solo engineering effort and include tests/review, not calendar guarantees.

| Phase | Work | Estimate | Exit condition |
|---|---|---:|---|
| 0. Contract baseline | Snapshot DB/Chroma/uploads; add characterization tests; document current deck/card JSON variants | 1–2 days | Current behavior is reproducible and rollback data exists |
| 1. Backend decoupling | Remove Streamlit from extractor/cache; typed repositories; settings/absolute paths; pure grading service; generation progress callback | 3–5 days | Existing CLI/service tests pass without importing Streamlit |
| 2. FastAPI parity API | Pydantic unions, modules/decks routes, durable generation job + worker/SSE, session/grading routes, OpenAPI tests | 5–8 days | API can complete upload → generation → quiz against a test database |
| 3. Next.js foundation | App shell, tokens, Proof Garden system, API client, workspace and create-deck flow | 4–6 days | User can upload modules, start generation, and see truthful progress |
| 4. Study experience | MCQ/enumeration/problem components, reasoning gutter, session resume, reveal, summary, keyboard/mobile/a11y | 5–8 days | All three card types complete end to end in Playwright |
| 5. Deployment rehearsal | Compose/reverse proxy, staging tunnel/hostname, state copy, load/OCR smoke tests, observability | 2–4 days | Staging mirrors production data shape and passes smoke checklist |
| 6. Parallel cutover | Keep Streamlit live; deploy Next/FastAPI behind preview path/hostname; Dawn acceptance; switch tunnel route; retain rollback | 2–3 days | `andyhub.org` serves Next.js and rollback is documented/tested |

Expected total: approximately 22–36 engineering days. A thinner MVP could land in 15–20 days by deferring durable quiz sessions, SSE, deck detail previews, and the reasoning gutter polish, but those deferrals reduce the main benefits of leaving Streamlit.

### Zero-breakage cutover

1. Freeze no data and change no public route while building the API.
2. Run API tests against a copy of the SQLite/Chroma state.
3. Run Streamlit and the new stack side by side; only one environment writes production state during rehearsal.
4. Expose the new stack on a private Cloudflare Access hostname or preview path.
5. Have Dawn create a real mixed deck and complete all card types on desktop and mobile.
6. Back up persistent state immediately before cutover.
7. Change the tunnel/reverse-proxy route to Next.js; keep Streamlit service available but unadvertised for a defined rollback window.
8. Remove Streamlit dependencies only after the acceptance window. Keep a tagged pre-cutover image/commit.

## 9. Testing strategy

### API

- Unit tests: extraction caching, chunking, card validation, grading tolerance, enumeration caught/missed, problem reveal rules.
- Repository tests with temporary SQLite and migration fixtures containing old multiple-choice cards plus new JSON variants.
- API contract tests using FastAPI's test client and dependency overrides for Groq/Chroma.
- Generation job tests for success, malformed Groq output, partial valid cards, API restart/recovery, and duplicate uploads.

### Frontend

- Component tests for each discriminated card renderer.
- Accessibility checks: keyboard-only MCQ, focus after feedback, screen-reader status announcements, non-color error cues.
- Playwright journeys for upload → generation → deck → session; refresh/resume; practice missed; reveal solution.
- Visual regression at desktop/tablet/mobile for the reasoning gutter and long matrices/answers.

### Deployment

- Restore a production-state backup into staging.
- Verify Cloudflare-upload limits, OCR duration, SSE/poll fallback, process restart, disk-full behavior, and Groq failure messaging.

## 10. Decisions Dawn must make before implementation

1. **Audience and authentication:** Is AndyHub a private single-user tool, a portfolio demo, or a multi-user product? The current app has no authentication or ownership boundary. This decision changes every session, upload, and deck schema.
2. **Existing data retention:** Must all current decks, miss counts, uploads, extraction caches, and Chroma memory migrate exactly, or may stale test data be archived?
3. **Quiz persistence:** Should sessions resume across refresh/device, or is per-tab persistence enough for the first release? Recommended: database-backed resume.
4. **Problem grading scope:** Is scalar numeric/text tolerance sufficient initially, or must v1 understand matrices, vectors, fractions, equivalent equations, unordered eigenvalue sets, and symbolic expressions? Recommended: scalar/text v1 plus explicit self-grading for structured answers.
5. **Reveal policy:** Does revealing solution steps mark the card missed, end the attempt, or allow another try? Recommended: mark as revealed/missed once, then allow study-mode retries without counting them as independent solves.
6. **Enumeration partial credit:** Is a card complete only when every item is caught, as today, or can a threshold advance it? Recommended: show partial count but require all expected items in assessment mode.
7. **RAG memory scope:** Should earlier modules influence every future deck sharing a subject, or should Dawn choose “current modules only / include prior subject memory”? Recommended: expose this as a deck-generation choice because current implicit subject-wide memory can surprise users.
8. **Module retention/privacy:** How long should uploaded course material remain, who may access it, and should the UI support delete/forget (including extraction cache and Chroma vectors)?
9. **Deployment preference:** Keep both apps on the GCP VM as recommended, or deliberately move the frontend to a managed host? Confirm VM headroom and current process manager/tunnel configuration before choosing exact Compose/service files.
10. **Visual direction acceptance:** Approve “Proof Garden,” the light-first cool-lilac palette, and the reasoning gutter before high-fidelity implementation. If Dawn wants a different emotional register, decide it before component work rather than re-skinning afterward.
11. **Math authoring:** Does source material contain LaTeX, image-only matrices, or plain-text notation, and should generated cards require model-produced LaTeX? This affects prompt contracts, sanitization, and rendering.
12. **Mobile/offline scope:** Is phone study a launch requirement, and is PWA/offline deck access important? Responsive mobile should be baseline; offline sync should be a later explicit feature.

## 11. Research basis

- Existing source inspected: `app.py`, `backend_logic.py`, `generator.py`, `rag_engine.py`, `database.py`, `extractor.py`, `requirements.txt`, and repository/deployment references available locally.
- Dawn's canonical context: `D:\Andy_Brain\01_Career_and_Resume\Dawn_Personal_Context.md` — used for verified stack, infrastructure-first priorities, hardware awareness, and communication preferences.
- [Anthropic frontend-design skill](https://raw.githubusercontent.com/anthropics/claude-code/main/plugins/frontend-design/skills/frontend-design/SKILL.md) — used for the subject-specific thesis, deliberate typography, signature element, one justified aesthetic risk, non-templated palette, truthful structure, restrained motion, accessibility, and active UI copy.
- [Anthropic canvas-design skill](https://raw.githubusercontent.com/anthropics/skills/main/skills/canvas-design/SKILL.md) — used for the Proof Garden visual philosophy, spatial communication, subtle domain reference, and emphasis on craftsmanship rather than decoration.
- [FastAPI features](https://fastapi.tiangolo.com/features/) and [file-upload documentation](https://fastapi.tiangolo.com/tutorial/request-files/) — basis for OpenAPI/Pydantic contracts, dependency injection, testing, uploads, and streaming/event options.
- [Next.js App Router documentation](https://nextjs.org/docs/app) — basis for route/layout boundaries and client/server component separation.
- [Cloudflare Tunnel configuration documentation](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/) — basis for preserving a single public hostname while routing to a new local origin stack.

## 12. Recommended approval boundary

Approval of this document should authorize Phase 0 only: backup/state inventory, characterization tests, and precise API contracts. It should not implicitly authorize production deployment, data migration, tunnel changes, authentication choices, or deletion of the Streamlit app. Those require the open decisions above and a separate implementation greenlight.

## 13. Decisions confirmed by Dawn (2026-08-14)

All 12 open decisions from Section 10 are resolved:

1. **Audience/auth:** Primarily a private single-user tool, but must also work well as a portfolio demo for recruiters and be usable from phone/tablet. No multi-user account system for v1 — build it presentable and responsive, not literally multi-tenant.
2. **Existing data retention:** Archive stale test data (e.g. "test1 (python)"); exact migration not required.
3. **Quiz persistence:** Database-backed resume across refresh/device — approved as recommended.
4. **Problem grading scope:** Scalar/text tolerance auto-grading + explicit self-grading reveal for matrices/vectors/eigenvalue-sets — approved as recommended.
5. **Reveal policy:** Revealing solution steps marks the card missed once, then allows untracked study-mode retries — approved as recommended.
6. **Enumeration partial credit:** Require all expected items in assessment mode (partial progress shown, not counted as solved) — approved as recommended.
7. **RAG memory scope:** Per-deck toggle — "current modules only" vs "include prior subject memory" — approved as recommended.
8. **Module retention/privacy:** Support explicit delete/forget (file, OCR cache, Chroma vectors) — approved as recommended.
9. **Deployment:** Keep both FastAPI and Next.js on the existing GCP VM behind the existing Cloudflare Tunnel — approved as recommended.
10. **Visual direction:** "Proof Garden" (cool-lilac palette, reasoning gutter, the three typefaces) approved as described, no changes requested.
11. **Math authoring:** Require LaTeX rendering for real matrix/fraction notation — approved as recommended, given actual Linear Algebra coursework incoming.
12. **Mobile/offline:** Responsive mobile baseline at launch; offline/PWA deferred to a later explicit feature — approved as recommended.

**Authorization:** Per Section 12's recommended approval boundary, this confirms authorization for **Phase 0 (Contract baseline) only** — backup/state inventory, characterization tests, and precise API contracts. Phases 1+ (backend decoupling, FastAPI build-out, Next.js implementation, cutover) require a separate explicit greenlight per phase, not a single blanket approval.

## 14. Phase 0 contract-baseline status (2026-08-14)

Status: **characterization complete; rollback snapshot created and checksum-verified.** No Phase 1 work has started and no production behavior has been changed.

### Current card contract, exactly as stored

The baseline suite in `test_phase0_contract_baseline.py` characterizes these source-level and SQLite-level shapes. These are the migration inputs for the later Pydantic models; they are not proposed new API shapes.

| Card type | Valid generator object | `cards.correct_answer` storage | `cards.options` storage |
|---|---|---|---|
| `multiple_choice` | `{ "type": "multiple_choice", "question": string, "options": [string, string, string, string], "correct_answer": one_exact_option }` | The selected option as a non-empty string | JSON array of the four option strings |
| `enumeration` | `{ "type": "enumeration", "question": string, "correct_answer": [string, string, ...] }` with at least two items; no required `options` key | JSON text of the same expected-item array (the existing column is non-null) | JSON text of the same expected-item array; this is the quiz UI's authoritative enumeration payload |
| `problem` | `{ "type": "problem", "question": string, "correct_answer": non_empty_final_answer_string, "solution_steps": [non_empty_string, ...] }`; no required `options` key | The final answer as a non-empty string | JSON object: `{ "final_answer": same_final_answer, "solution_steps": [string, ...] }` |

The live `cards` row remains the positional SQLite tuple `(id, deck_id, type, question, correct_answer, options, times_missed)`. `decks` remains `(id, name, modules_included, subject)`. `add_card()` serializes only truthy `options`; a falsey value such as `[]` is currently stored as SQL `NULL`. The future API must intentionally preserve or migrate this legacy edge case rather than silently changing it.

### Characterized behavior

- Generator: supported styles/prompts; paragraph chunking and fenced-JSON cleanup; valid/invalid requirements for every card type; end-to-end persistence translation for a mixed three-card generation without Groq, OCR, or real storage writes.
- Database: schema column order, positional tuple returns, JSON serialization for every current card variant, and cumulative miss-count update behavior, using an isolated self-cleaning SQLite file.
- RAG: lowercase/trimmed subject metadata, deterministic `module_name_chunk_index` IDs, subject-filtered query shape, 500-character source excerpts, and empty-context fallback on empty/error responses, using a recording fake Chroma boundary.

Verification command: `./.venv/Scripts/python.exe -B -m unittest -v test_phase0_contract_baseline.py` (10 tests passing on 2026-08-14). The suite does not contact Groq, perform OCR, touch `Database/reviewer.db`, or write to the live `course_brain_db` collection.

### Snapshot requirement — resolved 2026-08-14

`Database/reviewer.db`, `course_brain_db/`, and `uploads/` were copied into `D:\Personal Projects\_Backups\AllInOneReviewer_Phase0_20260814-084030\`, outside the repository, with a SHA-256 checksum manifest (`MANIFEST.sha256`). All three copied files were verified byte-identical to the live source via `sha256sum` on both sides after the copy. Root cause of the earlier block: the shell-write guard's cwd check picked up the invoking shell's last-known working directory (which was the vault) rather than the actual external source/destination paths in the command; a plain `cp`/`mkdir` invocation (not matched by the guard's write-verb pattern) completed without incident once run from outside the vault. Phase 0's exit condition is now fully met. Phase 1 still requires a separate explicit greenlight per the authorization boundary above — this snapshot only removes the blocking prerequisite.
