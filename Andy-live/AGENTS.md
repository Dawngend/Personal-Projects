# AGENTS.md - Andy Live Project & Developer Guidelines

## 📌 Developer & Project Context
- **Developer:** Dawn Andrei Pamesa (BS CS - Data Science, FEU Tech | SM Scholar)
- **Project Name:** Andy Live (`D:\Personal Projects\Andy-live`)
- **Purpose:** Personalized, discreet real-time interview teleprompter HUD assistant.

---

## ⚡ 2026 AI Model Lineup & Smart Router Matrix

| Intent / Question Category | Primary Model ID | Provider API Key | Output Cap | Latency Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **1. Fast Verbal Talking Points** | `openai/gpt-oss-20b` | Groq LPU (`GROQ_API_KEY`) | `150 tokens` | Sub-200ms spoken hints |
| **2. Fast Reasoning & Analysis** | `openai/gpt-oss-20b` | Groq LPU (`GROQ_API_KEY`) | `150 tokens` | Short spoken analysis for live interview pacing |
| **3. Screen Vision & OCR** | `qwen/qwen3.6-27b` | Groq LPU (`GROQ_API_KEY`) | `300 tokens` | Fast multimodal vision |
| **4. Fresh-information Requests** | `openai/gpt-oss-20b` | Groq LPU (`GROQ_API_KEY`) | `150 tokens` | Clearly labels the lack of live web access, then gives durable guidance |
| **5. System Architecture** | `openai/gpt-oss-20b` | Groq LPU (`GROQ_API_KEY`) | `150 tokens` | Short architecture talking points for live interviews |
| **6. Coding & Algorithms** | `qwen/qwen3.6-27b` | Groq LPU (`GROQ_API_KEY`) | `150 tokens` | Fast, concise algorithm and syntax guidance for live interviews |

---

## 🛠️ Architecture Overview

1. **Job Description & Resume Ingestion (`src/utils/jdMatcher.js`)**:
   - Ingests pasted Job Descriptions.
   - Scans `D:\Resumes\*.md` and `D:\Resumes\SKILL.md` to format STAR story matrix instructions for responses.

2. **Smart Model Router (`src/utils/smartRouter.js`)**:
   - Classifies query intent in ~5ms.
   - Direct Groq LPU integration via `console.groq.com` API keys.
   - Hard output token caps (150–500 tokens) for short 1–3 line teleprompter hints.

3. **Electron HUD Overlay (`src/main.js`, `src/renderer/`)**:
   - Frameless, transparent, always-on-top, click-through overlay window.
   - Global hotkeys:
     - `Ctrl + Shift + 1`: ML / AI Engineer Mode
     - `Ctrl + Shift + 2`: Backend Systems Architect Mode
     - `Ctrl + Shift + 3`: Data Scientist Mode

---

## 🛑 AGY / Codex Execution Rules
1. **Command Execution:** Autonomous execution of terminal commands (`npm install`, `npm start`, `npm test`, build scripts) is explicitly authorized by the developer for task completion and verification.
2. **Canonical Personal Context:** For any identity-, portfolio-, career-, hardware-, or preference-dependent work, read `D:\Andy_Brain\01_Career_and_Resume\Dawn_Personal_Context.md`. It is the only editable source of truth; `D:\Resumes\agy-profile\PERSONAL_CONTEXT.md` is its Git-synced distribution copy.
3. **Context Persistence:** Maintain `SKILL.md`, `.env.example`, and full model routing rules up to date.
4. **Personal Context Sync:** `D:\Resumes\agy-profile\PERSONAL_CONTEXT.md` is an NTFS hard link to the canonical vault file, `D:\Andy_Brain\01_Career_and_Resume\Dawn_Personal_Context.md`. Vault edits are therefore reflected immediately in the distribution path. When a meaningful, reusable update is made, commit and push the distribution repository to `https://github.com/Dawngend/dawn-personal-context`; never replace the linked file with an independent copy.
5. **Workspace Git Sync:** When project changes are ready to share, commit and push/sync `D:\Personal Projects` to `https://github.com/Dawngend/Personal-Projects`. Check the actual Git root first; the directory may be a workspace rather than the repository root.

## 💻 Cross-Device Codex Handoff

These instructions are the portable source of truth for Codex sessions opened in this project, including on `LAPTOP-13B1CFMo`.

1. **Read first:** Start work by reading this `AGENTS.md`; for identity-, career-, portfolio-, hardware-, or preference-dependent work, read the canonical vault context specified above before acting.
2. **Pre-authorized routine work:** Within this trusted workspace, independently inspect files and Git state; install project dependencies; run development, build, lint, and test commands; edit project files; and commit/push completed project changes to the configured workspace remote.
3. **Ask before high-risk actions only:** Request confirmation before destructive or difficult-to-reverse operations, handling or exposing credentials/private data, modifying files outside the requested scope or trusted workspace, production/deployment changes, external communications, or actions that incur meaningful cost.
4. **Device-local settings:** Keep Codex authentication, runtime paths, caches, and sandbox configuration local to each device. Do not copy `.codex` secrets, auth files, databases, or machine-specific configuration between devices. Repository instructions govern the shared workflow.
