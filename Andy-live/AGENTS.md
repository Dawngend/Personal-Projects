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
| **2. Fast Reasoning & Analysis** | `openai/gpt-oss-120b` | Groq LPU (`GROQ_API_KEY`) | `300 tokens` | High-speed open-weights LPU |
| **3. Screen Vision & OCR** | `qwen/qwen3.6-27b` | Groq LPU (`GROQ_API_KEY`) | `300 tokens` | Fast multimodal vision |
| **4. Search & News Grounding** | `gemini-3.6-flash` | Google AI Studio | `200 tokens` | Real-time web search grounding |
| **5. Complex System Architecture** | `claude-sonnet-5` | Anthropic Console | `400 tokens` | Deep architecture & design diagrams |
| **6. Hard Coding & Algorithms** | `openai/gpt-oss-120b` | Groq LPU (`GROQ_API_KEY`) | `500 tokens` | Strong coding reasoning without a separate API account |

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
1. **Command Execution:** DO NOT run terminal commands (`npm install`, `npm start`, build scripts) without explicit user greenlight.
2. **Context Persistence:** Maintain `SKILL.md`, `.env.example`, and full model routing rules up to date.
3. **Personal Context Sync:** When a meaningful, reusable update is made to Dawn's developer profile, project portfolio, working preferences, or AGY guidance, also update `https://github.com/Dawngend/dawn-personal-context`.
4. **Workspace Git Sync:** When project changes are ready to share, commit and push/sync `D:\Personal Projects` to `https://github.com/Dawngend/Personal-Projects`. Check the actual Git root first; the directory may be a workspace rather than the repository root.
