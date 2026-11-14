# Ava — Zero-Storage Local DevSecOps AI Mentor & Ops-Center

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![VRAM 8GB](https://img.shields.io/badge/VRAM-8GB%20Optimized-green.svg)](https://developer.nvidia.com/cuda-gpus)
[![Zero-Storage](https://img.shields.io/badge/Ingestion-Zero--Storage%20RAM-orange.svg)](#zero-storage-ram-ingestion)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Author: Adel Battah](https://img.shields.io/badge/Author-Adel%20Battah-purple.svg)](https://github.com/AdelBattah)

Ava is a local-first, zero-storage artificial intelligence mentor engineered to run on an **8 GB VRAM RTX 5060 Laptop GPU** under strict host disk constraints (< 10 GB free space).

Unlike generic AI code generators that output copy-paste blocks and foster dependency, Ava is an active DevSecOps mentor. She guides the operator from foundational scripting into Linux system security, cloud infrastructure as code (Terraform), and secure automated deployment pipelines using Socratic, step-by-step challenges.

---

## 📑 Technical Documentation

* **[`ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md)** — Architectural Decision Records (ADRs) covering zero-storage sparse matrix mathematics, 8 GB VRAM multi-tier routing, and low-latency audio device detection.
* **[`FAILURE_LOG.md`](FAILURE_LOG.md)** — Engineering post-mortems and root-cause analyses of bare-metal race conditions, installer locks, socket mutexes, and parser issues.

---

## 🎯 Motivation: Why This Exists

Most local AI tutorials assume unlimited enterprise hardware: high-end multi-GPU workstations, tens of gigabytes of free disk, and heavy frameworks like PyTorch, Transformers, and persistent vector databases.

In real-world practitioner environments, these assumptions fail:
1. **The Disk Problem**: Installing PyTorch, HuggingFace weights, and database stores consumes 8–15 GB, risking host disk exhaustion.
2. **The VRAM Problem**: A dedicated 8 GB mobile GPU shared with modern operating systems and web browsers typically has only 2 GB of free VRAM during active multitasking.
3. **The Pedagogical Problem**: Large language models default to answering with 50-line boilerplate scripts. Beginners copy-paste without understanding the threat model, file permissions, or security implications.

Ava was built as an engineering solution to these three constraints:
* **Zero Persistent Ingestion Storage**: Scraped web documentation, study PDFs, and transcripts are streamed directly into volatile RAM, indexed using pure NumPy/SciPy sparse linear algebra, and wiped immediately after inference.
* **Multi-Tier Fault-Tolerant Routing**: Fast local intent routing (2s timeout), local code evaluation (5s timeout), and automatic seamless failover to free high-parameter cloud reasoning when local GPU memory experiences desktop contention.
* **Socratic, Security-First Mentoring**: Ava audits commands through an attacker's lens (`chmod 777`, open CIDRs, wildcard IAM policies) and provides micro-challenges, requiring the mentee to construct the secure fix.

---

## ⚡ Core Architecture & Highlights

* **In-Memory Document Ingestion & Takeaway Exporter (`study_notebook/`)**: Drop study PDFs, Markdown notes, or cheat sheets into `references/`. Ava parses them into RAM on demand via PyMuPDF and computes sparse TF-IDF cosine similarity in < 10 ms. Export session takeaways to `takeaways/` or generate active recall quiz banks in `quizzes/` formatted for your personal notes or Google NotebookLM.
* **Hardware-Aware Full-Duplex Audio**: Direct Windows registry querying identifies when headphones (such as the Logitech G522 LIGHTSPEED) are connected, automatically arming full-duplex voice barge-in so the operator can speak over Ava at any point without acoustic feedback.
* **Reactive Web Ops-Center HUD**: A 60 FPS HTML5 canvas tactical dashboard displaying real-time VRAM allocation, audio connection status, disk budget telemetry, and quick-action chips.
* **Dataset Accumulator**: Mentor dialogues are continuously validated and logged to `training_logs/mentor_dataset.jsonl` for future fine-tuning.

---

## 🚀 Quickstart

### Prerequisites
* Windows 11 / 10 (or Linux via WSL2)
* Python 3.10+
* Local model runtime (Ollama with `qwen2.5:3b` and `Qwen2.5-Coder:latest`)
* Optional: Free OpenRouter API key for 550B cloud reasoning failover

### Option 1: Web Ops-Center (Recommended)
```powershell
cd domain-agent
python src/ui_server.py
```
Open your browser to:
👉 **`http://127.0.0.1:8765`**

* **Hotkeys**:
  * `Alt + V`: Toggle microphone speech input
  * `Ctrl + Space`: Focus message / command deck
  * `Enter`: Transmit message or instantly cut off speech playback
* **Quick Actions**:
  * `[📓 SYNC NOTES]`: Export current session takeaways to `study_notebook/takeaways/`
  * `[📚 NOTEBOOK]`: Display indexed study materials and RAM passage count
  * `[🎤 AMBIENT HANDS-FREE]`: Continuous conversational loop

### Option 2: Interactive Terminal CLI
```powershell
cd domain-agent
python src/mentor.py
```

---

## 📋 Command Reference

| Command | Environment | Description |
| :--- | :--- | :--- |
| `/voice` or `/v` | CLI & Web | Toggle speech synthesis and microphone recognition on/off. |
| `/notebook` or `/nb` | CLI & Web | List all indexed study reference files and total RAM passages. |
| `/sync-notes` or `/sync` | CLI & Web | Export current session takeaways to `study_notebook/takeaways/`. |
| `/quiz <topic>` | CLI & Web | Generate a 5-question beginner quiz from your references and session notes. |
| `/profile` | CLI & Web | Display Ava's persona, pedagogical rules, and mentee baseline. |
| `/clear` | CLI & Web | Reset short-term conversation context memory. |
| `/grade <lab_name>`| CLI & Web | Submit work for grading against home-lab security test suites. |
| `https://<url>` | CLI & Web | Live zero-storage RAM extraction of documentation pages. |
| `exit` or `quit` | CLI | Save session and exit. |

---

## 📂 Repository Layout

```text
domain-agent/
│
├── .gitignore                # Protects .env, keys, audio buffers, and scratch files
├── LICENSE                   # MIT License (Adel Battah)
├── ARCHITECTURE_DECISIONS.md # ADRs: Sparse matrix math, VRAM tiering, CoreAudio probing
├── FAILURE_LOG.md            # Bare-metal debugging post-mortems & root-cause analyses
├── mentor_profile.md         # Ava persona specification & pedagogical rules
├── test_system.py            # Automated end-to-end verification script
├── README.md                 # Project operational runbook
│
├── study_notebook/           # In-RAM reference ingestion & takeaway exporter
│   ├── references/           # Drop study PDFs, Markdown notes, cheat-sheets here
│   ├── takeaways/            # Auto-exported session takeaways (session_YYYY-MM-DD.md)
│   └── quizzes/              # Auto-generated practice drill banks
│
├── ui/
│   └── index.html            # 60 FPS Web Ops-Center HUD
│
├── src/
│   ├── config.py             # Model routing, failsafe endpoints, VRAM optimization
│   ├── notebook.py           # In-RAM PyMuPDF / TF-IDF study notebook indexing engine
│   ├── retriever.py          # Pure NumPy/SciPy sparse TF-IDF CPU retriever (< 10 ms)
│   ├── researcher.py         # Zero-storage RAM researcher for YouTube & docs
│   ├── voice.py              # Neural TTS + Windows non-blocking barge-in
│   ├── mentor.py             # Interactive CLI, intent router, strict coaching
│   ├── ui_server.py          # Multi-threaded HTTP API server for Web Ops-Center
│   └── labs/                 # Home-lab grader scripts and challenge tests
│
└── training_logs/
    └── mentor_dataset.jsonl  # Continuous fine-tuning dataset accumulated in RAM
```

---

## 👤 Author

* **Adel Battah**
* GitHub: [@AdelBattah](https://github.com/AdelBattah)
