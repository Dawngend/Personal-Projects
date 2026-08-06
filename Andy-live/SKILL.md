---
name: dawn-pamesa-profile
description: AGY system skill and developer context configuration for Dawn Andrei Pamesa (Data Scientist, AI/ML Engineer, Backend Systems Architect). Use this skill to align AGY with Dawn's identity, technical stack, engineering principles, hardware setup, key hackathon/flagship projects, and response formatting guidelines.
---

# AGY System Skill & Context Configuration: Dawn Andrei Pamesa

## 👤 Developer Identity & Persona
* **Name:** Dawn Andrei Pamesa
* **Target Role:** Data Scientist / AI ML Engineer / Backend Systems Architect
* **Academic Status:** BS Computer Science (Data Science Specialization) at FEU Institute of Technology | 100% SM Foundation Scholar | Completed 3rd Term (Expected Graduation: July 2028)
* **Current Professional Roles:**
  * Machine Learning Intern at FlyRank AI (Started July 2026)
  * Co-Founder & Lead Backend Engineer at Dzuka Agri
  * Junior Officer at FEU Tech ACM Student Chapter
* **Core Brand Ecosystem:** "Andy Hub" (andyhub.org) and "Andy" (Custom AI Assistant Engine)
* **Development Philosophy:** Active learner continuously expanding technical depth, domain knowledge, and hands-on engineering experience.

---

## 🛠️ Core Engineering Style & Execution Rules for AGY
1. **Infrastructure-First Mindset:** Prioritize backend architecture, data integrity, low latency, and hardware efficiency over superficial UI fluff. Frontends may be rapidly prototyped (e.g., Streamlit, Next.js), but the underlying system design must be production-ready.
2. **Communication Tone:** Direct, punchy, execution-focused, and highly technical. Avoid fluff or corporate jargon.
3. **Code Quality & Typing:** Enforce strict type hints (`mypy --strict` in Python), robust Pydantic schemas, modular file structures, and comprehensive error handling.
4. **Hardware Awareness:** Respect hardware constraints (NVIDIA RTX 2060/3060, AMD Ryzen CPUs, and enterprise AMD MI300X ROCm workloads).
5. **No Hallucinations / Strict Schema Enforcement:** Use multi-model validation pipelines (e.g., Dual-API generation and JSON validation) whenever architecting agentic systems.

---

## 🧰 Technical Stack & System Architecture

### Programming Languages & Frameworks
* **Languages:** Python 3.11+, SQL, PL/SQL, C++, Assembly, PHP, HTML/CSS, JSON, Java
* **Backend Frameworks:** FastAPI, Pydantic v2, WebSockets, RESTful APIs, Node.js, Express
* **Frontend:** Next.js (App Router, TypeScript, Tailwind CSS), Streamlit, Electron

### AI, Machine Learning & Data Infrastructure
* **ML & Deep Learning:** PyTorch, scikit-learn, pandas, Optuna (Pareto Frontier multi-objective search), ROCm Workloads, Model Quantization (INT8/FP8/INT4), Knowledge Distillation, Model Pruning
* **LLM Orchestration & RAG:** Dual-API Pipelines, Groq Cloud LPU (`openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.6-27b`), Google Gemini (`gemini-3.6-flash`), Anthropic Claude (`claude-sonnet-5`), OpenAI (`gpt-5.6-soul`), SentenceTransformers, ChromaDB
* **Data Processing & OCR:** pdfplumber, Pytesseract OCR with fallback caching strategies, Geospatial Data Ingestion

### Cloud, DevOps & Databases
* **Databases:** Supabase (PostgreSQL with Spaced Repetition System logic), SQLite / aiosqlite, ChromaDB (Vector Isolation), Oracle PL/SQL
* **DevOps & Infrastructure:** GCP Virtual Machines, Cloudflare Tunnels (`cloudflared`), Docker containerization, Git/GitHub, CI/CD, Optuna

---

## 🏛️ Project Profile & Architecture Knowledge Base

### 1. Andy Live (Personal Real-Time AI Interview Teleprompter HUD)
* **Location:** `D:\Personal Projects\Andy-live`
* **Architecture:** Electron transparent click-through HUD overlay + Smart AIRouter using 2026 AI Model Lineup & Job Description Ingestion Engine.
* **Key Components:**
  * **Groq LPU Integration (`GROQ_API_KEY`):** Sub-200ms spoken hint generation using `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, and `qwen/qwen3.6-27b` (Vision).
  * **Multi-AI Router (`smartRouter.js`):** Classifies query intent in ~5ms and routes to Groq (Talking Points/Reasoning), Gemini 3.6 Flash (Search), Claude Sonnet 5 (Architecture), or GPT-5.6 Soul (Hard Coding).
  * **Dynamic Resume Matcher (`jdMatcher.js`):** Ingests Job Descriptions, scans `D:\Resumes\*.md` and `SKILL.md`, and formats STAR story matrix instructions for responses.
  * **Stealth Glassmorphism HUD:** Always-on-top, click-through window with global hotkeys (`Ctrl+Shift+1/2/3`) for role mode switching.

### 2. ForgeAI (AMD Developer Cloud Hackathon)
* **Architecture:** Hardware-Aware AI Model Optimization & Quantization Platform for PyTorch models on AMD Instinct MI300X GPUs via ROCm.

### 3. BANGON (eGovPH Hackathon 2026)
* **Architecture:** PII-Secure, Blockchain-Anchored SuperApp Integration built for the eGovPH ecosystem.

### 4. Sophy (ACM Techsprint Hackathon)
* **Architecture:** Adaptive, low-latency AI study engine and stateful RAG platform for Filipino learners.

### 5. Andy's Hub (Personal Flagship Project)
* **Architecture:** Stateful RAG-driven AI academic reviewer hosted at `andyhub.org`.

### 6. Dzuka Agri (lablab.ai Band of Agents Hackathon)
* **Architecture:** Multi-agent agricultural intelligence platform serving smallholder farmers across Africa.
