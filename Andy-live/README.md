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
| **5. Complex System Architecture**| `claude-sonnet-5` | Anthropic Console | `400 tokens` | Deep architectural specs & diagrams |
| **6. Hard Coding & Algorithms** | `gpt-5.6-soul` | OpenAI API | `500 tokens` | Top-tier LeetCode / syntax precision |

---

## 🛠️ Features

1. **Dynamic Job Description Ingestion**: Paste company JDs before the interview. Auto-scans all resumes in `D:\Resumes\*.md` + `D:\Resumes\SKILL.md` to format STAR alignment talking points.
2. **Groq LPU Direct Cloud Integration**: Uses pure Cloud LPU API keys directly from `console.groq.com`.
3. **Stealth Glassmorphism HUD**: Always-on-top, transparent, click-through overlay interface.
4. **Global Hotkeys**:
   - `Ctrl + Shift + 1`: ML / AI Engineer Profile Mode
   - `Ctrl + Shift + 2`: Backend Systems Architect Profile Mode
   - `Ctrl + Shift + 3`: Data Scientist Profile Mode

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
   ANTHROPIC_API_KEY=sk-ant-api03_...
   OPENAI_API_KEY=sk-proj-...
   ```

3. **Run Andy Live**:
   ```bash
   npm start
   ```
