# Architecture Decision Records (ADRs)
## Project: AVA // THE MACHINE (Zero-Storage Local DevSecOps Mentor)

This document records the architectural and engineering decisions made during the design, implementation, and optimization of **AVA // THE MACHINE**. Each record documents the problem context, alternatives evaluated, technical trade-offs, and final decision.

---

### Table of Contents
* [ADR-001: Zero-Storage RAM-Only Ingestion vs. Heavy Persistent Vector Stores](#adr-001-zero-storage-ram-only-ingestion-vs-heavy-persistent-vector-stores)
* [ADR-002: Three-Tier Model Pipeline & Automatic 5-Second VRAM Contention Failover](#adr-002-three-tier-model-pipeline--automatic-5-second-vram-contention-failover)
* [ADR-003: Bare-Metal Windows CoreAudio Registry Probing for Full-Duplex Voice Barge-In](#adr-003-bare-metal-windows-coreaudio-registry-probing-for-full-duplex-voice-barge-in)
* [ADR-004: Strict Socratic Mentorship Directives ("Anti-Copilot" Pedagogical Guardrail)](#adr-004-strict-socratic-mentorship-directives-anti-copilot-pedagogical-guardrail)
* [ADR-005: In-Memory Document Ingestion & Session Takeaway Exporter](#adr-005-in-memory-document-ingestion--session-takeaway-exporter)

---

### ADR-001: Zero-Storage RAM-Only Ingestion vs. Heavy Persistent Vector Stores

#### Status
**Accepted**

#### Context & Problem Statement
The operational host environment is an NVIDIA RTX 5060 Laptop with constrained available disk space on the primary `C:` drive (< 10 GB free space baseline). Standard local RAG implementations rely on heavy dependencies:
* PyTorch (`torch`): ~2.5 GB on disk
* HuggingFace Transformers & Accelerate: ~1.5 GB on disk
* Sentence-Transformers / ONNX embedding models: ~1–3 GB on disk
* Persistent Vector Databases (ChromaDB, Weaviate, LanceDB): Continuous disk growth via persistent vector indices and SQLite/parquet stores.

Installing this standard RAG stack would quickly exhaust available disk space, causing Windows file-system paging lockups and system instability.

#### Decision
We explicitly rejected PyTorch, HuggingFace embeddings, and persistent vector databases. 

Instead, we built an extractive retrieval engine (`src/retriever.py` and `src/notebook.py`) using **pure NumPy and SciPy sparse Compressed Sparse Row (CSR) matrices**:
1. Documents (web docs, YouTube transcripts, PDFs, Markdown notes) are streamed or read strictly into volatile RAM.
2. Text is tokenized with regex and converted into a sparse Term Frequency-Inverse Document Frequency (TF-IDF) CSR matrix.
3. Cosine similarity queries are executed using CPU sparse-dense dot products (`mat.dot(q_vec) / (norms * q_norm)`).
4. After inference, raw text buffers and matrices are garbage-collected from RAM. **Zero bytes are written to persistent disk.**

#### Consequences & Trade-offs
* **Benefits**:
  * **0 MB Persistent Disk Growth**: Completely immune to disk exhaustion.
  * **Ultra-Low Latency**: Pure CPU matrix math executes in `< 10 ms` for 100+ document chunks, eliminating the ~200 ms overhead of neural embedding inferences.
  * **Minimal Dependency Footprint**: Depends only on standard `numpy` and `scipy`.
* **Trade-offs**:
  * Lexical/TF-IDF similarity does not capture deep abstract semantic synonyms as well as dense multi-layer transformers; mitigated by using character n-grams and domain-specific tokenization.

---

### ADR-002: Three-Tier Model Pipeline & Automatic 5-Second VRAM Contention Failover

#### Status
**Accepted**

#### Context & Problem Statement
The local GPU is an NVIDIA GeForce RTX 5060 Laptop GPU with 8,151 MiB total VRAM. In a typical Windows 11 workstation session, desktop apps (Windows Shell, Edge/Chrome, NVIDIA Overlay, background services) consume 5.5–6.2 GB of VRAM. This leaves approximately **1.8–2.2 GB of free VRAM** during peak desktop usage.

Attempting to run a 7B coder model (`Qwen2.5-Coder:latest`, ~4.7 GB unquantized footprint) when free VRAM drops below 2.5 GB forces the local Ollama/llama-server engine to page memory into system RAM, stalling inference for 40+ seconds or causing IPC socket timeouts.

#### Decision
We implemented a **resilient 3-tier routing and auto-failover pipeline** (`src/config.py` and `src/mentor.py`):
1. **Tier 1 (Fast Router)**: `qwen2.5:3b` (1.9 GB model) handles intent classification with a strict **2.0-second timeout**. If it does not respond within 2 seconds, the system defaults to the code mentor path with zero delay.
2. **Tier 2 (Local Coder)**: `Qwen2.5-Coder:latest` runs locally with a strict **5.0-second execution timeout**. If GPU memory contention prevents generation within 5 seconds, it immediately raises an exception.
3. **Tier 3 (Cloud Neural Mesh Failover)**: When Tier 2 times out, the turn automatically fails over to OpenRouter Free tier (`nvidia/nemotron-3-ultra-550b-a55b:free` or `openrouter/free`). Execution completes in ~1.8 seconds at $0.00 cost.
4. **Offline Fallback**: If network is unavailable and remote failover fails, it falls back to local `qwen3.5:9b-q4_K_M` with capped context window.

#### Consequences & Trade-offs
* **Benefits**:
  * **Zero Freezes**: The user interface never hangs when background desktop apps consume GPU memory.
  * **Best of Both Worlds**: Enjoys 0 ms local latency when VRAM is available, and instantaneous 550B cloud reasoning when VRAM is constrained.
* **Trade-offs**:
  * Requires an active internet connection and OpenRouter API key for the remote failover tier.

---

### ADR-003: Bare-Metal Windows CoreAudio Registry Probing for Full-Duplex Voice Barge-In

#### Status
**Accepted**

#### Context & Problem Statement
In voice-assisted AI interfaces, user barge-in (interrupting the model while it is speaking) is notoriously difficult. If the model speaks through external laptop speakers while the microphone is open, the microphone captures the model's own voice (acoustic echo), causing the system to falsely interrupt itself in an infinite feedback loop.

#### Decision
We implemented hardware-aware device resolution via direct Windows Registry querying (`src/voice.py`):
1. We probe `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render` using PowerShell / Python registry APIs to resolve the active Windows audio rendering endpoint.
2. We inspect device properties and friendly names (e.g., `Logitech G522 LIGHTSPEED`, USB headsets, Bluetooth headphones).
3. **Adaptive Barge-In Policy**:
   * **Headphones Detected**: **Full-Duplex Voice Barge-In is Armed.** The user can speak over Ava at any point. Speech recognition interrupts the native non-blocking Windows MCI audio playback thread instantly.
   * **Speakers Detected**: Voice barge-in is disarmed to prevent echo loops; barge-in gracefully falls back to non-blocking keyboard tap (`[Enter]`).

#### Consequences & Trade-offs
* **Benefits**:
  * Zero acoustic echo loops without requiring heavy digital signal processing (DSP) echo cancellation libraries like WebRTC AEC3.
  * Frictionless, natural conversational flow when wearing a headset.
* **Trade-offs**:
  * Relies on Windows CoreAudio registry architecture; non-Windows environments require platform-specific audio device enumeration (e.g. CoreAudio on macOS, ALSA/PulseAudio on Linux).

---

### ADR-004: Strict Socratic Mentorship Directives ("Anti-Copilot" Pedagogical Guardrail)

#### Status
**Accepted**

#### Context & Problem Statement
Generative AI coding assistants (e.g., GitHub Copilot, ChatGPT) default to providing complete, multi-file code solutions. For a mentee transitioning into DevSecOps from a "script kiddie" baseline with zero enterprise job experience, copy-pasting code produces the illusion of competence while leaving fundamental gaps in Linux internals, networking, IAM security, and debugging.

#### Decision
We established a strict pedagogical contract in [`mentor_profile.md`](mentor_profile.md) and [`src/mentor.py`](src/mentor.py):
1. **First-Principles Analogies**: Every abstract concept must begin with an intuitive physical analogy (e.g., IAM roles as temporary visitor badges vs. IAM users as employee keycards; CIDR blocks as apartment building room numbers).
2. **Micro-Scaffolding (One Parameter at a Time)**: Complete copy-paste solutions are prohibited. The mentor provides a minimal 2–4 line code skeleton, explains what each parameter/flag does, and requires the Operator to supply or fix exactly one parameter.
3. **Attacker-Perspective Auditing**: The mentor audits terminal outputs and configs like a threat actor, explaining the exact attack vector of common beginner mistakes (`chmod 777`, `0.0.0.0/0`, wildcard `Action: "*"`).
4. **Socratic Closing**: Every turn concludes with exactly one focused question or diagnostic command.

#### Consequences & Trade-offs
* **Benefits**:
  * Actively trains problem-solving, terminal muscle memory, and security intuition.
  * Prepares the mentee for technical interviews where interviewers ask candidates to defend their architectural choices without an AI assistant.
* **Trade-offs**:
  * Requires higher initial cognitive effort from the mentee compared to instant code-generation tools.

---

### ADR-005: In-Memory Document Ingestion & Session Takeaway Exporter

#### Status
**Accepted**

#### Context & Problem Statement
The Operator downloads reference whitepapers, AWS documentation, and custom cheat-sheets locally, and uses tools like Google NotebookLM for conceptual study. To integrate these study materials into the mentoring workflow, the agent needed a way to search and reference downloaded documents without setting up complex external vector databases or cloud sync daemons.

#### Decision
We implemented a local filesystem workflow in `study_notebook/` with three isolated subdirectories:
* `references/`: Drop point for user-downloaded PDFs, Markdown (`.md`), and plain text (`.txt`) study materials.
* `takeaways/`: Export target where Ava compiles structured Markdown session summaries (`session_YYYY-MM-DD_HH-MM.md`).
* `quizzes/`: Export target where Ava saves auto-generated 5-question review drills.

Text extraction uses PyMuPDF (`fitz`) for PDF page extraction entirely into RAM, and text is vectorized on-the-fly by the shared NumPy/SciPy sparse TF-IDF engine.

#### Consequences & Trade-offs
* **Benefits**:
  * Completely offline-capable, local-first, zero cloud credentials required for reference lookup.
  * Extracted text stays in volatile memory—no persistent vector databases inflating disk usage.
  * Formatted in clean standard Markdown, ready to copy or upload directly to Google NotebookLM, Notion, or personal notes.
* **Trade-offs**:
  * Ingestion is file-based: the user downloads or places reference files into the `references/` folder directly.
