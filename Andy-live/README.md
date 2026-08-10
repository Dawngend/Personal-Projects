# Andy Live 🎙️

**Andy Live** is a personalized, discreet real-time interview & technical teleprompter HUD assistant powered by a smart multi-AI provider router and dynamic resume/JD matcher.

Location: `D:\Personal Projects\Andy-live`

---

## ⚡ 2026 AI Model Lineup & Smart Router Matrix

| Intent / Question Category | Primary Model | Provider | Output Cap | Latency Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **1. Fast Spoken Talking Points** | `openai/gpt-oss-20b` | Groq LPU (`GROQ_API_KEY`) | `150 tokens` | Sub-200ms spoken hints |
| **2. Fast Reasoning & Analysis** | `openai/gpt-oss-120b` | Groq LPU (`GROQ_API_KEY`) | `300 tokens` | Flagship open-weights LPU speed |
| **3. Multimodal / Vision** | `qwen/qwen3.6-27b` | Groq LPU (`GROQ_API_KEY`) | `300 tokens` | Fast screen OCR & vision |
| **4. Search & News Grounding** | `gemini-3.6-flash` | Google AI Studio | `200 tokens` | Real-time web search grounding |
| **5. Complex System Architecture**| `openai/gpt-oss-120b` | Groq LPU (`GROQ_API_KEY`) | `400 tokens` | Deep architectural specs & diagrams |
| **6. Hard Coding & Algorithms** | `openai/gpt-oss-120b` | Groq LPU (`GROQ_API_KEY`) | `500 tokens` | Strong coding reasoning without a separate API account |

---

## 🛠️ Features

1. **Dynamic Job Description Ingestion**: Paste company JDs before the interview. Auto-scans all resumes in `D:\Resumes\*.md` + `D:\Resumes\SKILL.md` to format STAR alignment talking points.
2. **Groq LPU Direct Cloud Integration**: Uses pure Cloud LPU API keys directly from `console.groq.com`.
3. **Glassmorphism HUD**: Always-on-top, transparent overlay interface.
4. **Global Hotkeys**:
   - `Ctrl + Shift + 1`: ML / AI Engineer Profile Mode
   - `Ctrl + Shift + 2`: Backend Systems Architect Profile Mode
   - `Ctrl + Shift + 3`: Data Scientist Profile Mode

---

## Interview flow

1. Start the app, open **Setup JD**, paste the role description, and select a resume or let Andy auto-detect one.
2. Ask/paste each interviewer question into the footer. The router chooses a model based on intent, or you can override it from the provider menu.
3. Switch framing immediately with `Ctrl + Shift + 1` (ML/AI), `Ctrl + Shift + 2` (Backend), or `Ctrl + Shift + 3` (Data Science). The active mode updates the system prompt for the current session.

## Configuration and failure behavior

Copy `.env.example` to `.env`. At minimum, configure `GROQ_API_KEY` for the default fast-answer route. The remaining keys enable their respective specialized routes.

If a selected provider is unavailable or errors, Andy attempts a configured alternate provider. It never writes API keys or resume content to disk.

## Product boundary

Andy Live is an overt interview-preparation and communication-coaching tool. Future work may add consent-based contextual input, profiles, history, preferences, and keyboard window controls. It will not include concealment, click-through/stealth behavior, proctoring bypasses, or other evasion features.

---

## 🚀 Quick Start

1. **Install Dependencies**:
   ```bash
   cd "D:\Personal Projects\Andy-live"
   npm install
   ```

2. **Configure API Keys**:
   Copy `.env.example` to `.env` and insert your keys:
   ```env
   GROQ_API_KEY=gsk_...
   GEMINI_API_KEY=AIzaSy_...
   ```

3. **Run Andy Live**:
   ```bash
   npm start
   ```
