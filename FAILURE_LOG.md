# Engineering Failure Log & Post-Mortems
## Project: AVA // THE MACHINE (Zero-Storage Local DevSecOps Mentor)

> *"A perfect repository is a red flag. What distinguishes an engineer is not the absence of failure, but the ability to diagnose, isolate, and systematically resolve bare-metal failures under constraints."*

This document provides transparent, technical post-mortems of the real bugs, deadlocks, and performance bottlenecks encountered during the development and bare-metal testing of **AVA // THE MACHINE**, along with the root-cause analyses (RCA) and permanent fixes applied.

---

### Failure Index
1. [Failure 01: The Mystery Disk Exhaustion & Locked Installer Ghost](#failure-01-the-mystery-disk-exhaustion--locked-installer-ghost)
2. [Failure 02: The Private Llama-Server Socket Mutex Deadlock](#failure-02-the-private-llama-server-socket-mutex-deadlock)
3. [Failure 03: The Premature STT Audio Clipper (150ms Silence Bug)](#failure-03-the-premature-stt-audio-clipper-150ms-silence-bug)
4. [Failure 04: The High-Frequency CRT Scanline Moiré Fatigue](#failure-04-the-high-frequency-crt-scanline-moir-fatigue)
5. [Failure 05: The UTF-8 Byte Order Mark (BOM) Parser Breakage](#failure-05-the-utf-8-byte-order-mark-bom-parser-breakage)

---

### Failure 01: The Mystery Disk Exhaustion & Locked Installer Ghost

* **Date & Context**: Runtime validation on workstation (`C:` drive).
* **Observed Symptom**: Available disk space on `C:` abruptly plummeted from **10.6 GB** down to **3.2 GB**, triggering low-disk alerts. Initial hypothesis suspected that Ollama was writing massive activation caches or uncompressed log files to disk during Qwen inference.
* **Root-Cause Analysis (RCA)**:
  1. We ran PowerShell disk footprint analyses across `C:\Users\AERO\.ollama\models`. The model directory was completely static at **21.50 GB**—zero bytes were being added by Ollama.
  2. We conducted a depth-first traversal of `AppData\Local\Temp`.
  3. We discovered an orphaned directory: `AppData\Local\Temp\0d5vj0yp` containing **4.67 GB** of uncompressed Visual Studio / Edge setup debris.
  4. Attempting to delete the folder failed with `PermissionError / Access is Denied` because an orphaned background installer process held an active Win32 file lock on `setup.exe` inside the directory.
* **Resolution**:
  1. Identified and terminated the dormant background installer task.
  2. Executed a clean removal using Python's `shutil.rmtree()`.
  3. Free disk space instantly recovered from **3.2 GB to 8.66 GB**.
  4. Integrated live real-time disk telemetry (`shutil.disk_usage("C:\\")`) into the Web Ops-Center header to continuously monitor free space.

---

### Failure 02: The Private Llama-Server Socket Mutex Deadlock

* **Date & Context**: Full-system chat turn execution via `src/mentor.py` and `src/ui_server.py`.
* **Observed Symptom**: Submitting broad requests like *"How could we start today?"* caused the mentor to hang indefinitely (30+ seconds), resulting in HTTP client timeouts in the UI.
* **Root-Cause Analysis (RCA)**:
  1. In an earlier iteration, an experimental runner discovery module attempted to bypass Ollama by using `psutil` to find the ephemeral port of child `llama-server.exe` processes (e.g., port `53188`).
  2. We tested sending raw OpenAI-compatible completions requests directly to `http://127.0.0.1:53188/v1/chat/completions`.
  3. The request hung indefinitely. Why? Ollama spawns `llama-server` as an internal managed child worker using standard I/O pipes and internal synchronization. Connecting an external HTTP client directly to this child socket interfered with Ollama's internal process orchestration and deadlocked the server's mutex.
  4. Furthermore, the child runner did not recognize model aliases like `"qwen2.5:3b"`—it only recognized raw SHA-256 model digests.
* **Resolution**:
  1. Removed all child socket hunting and ephemeral port scanning.
  2. Routed all local requests strictly through Ollama's official, multi-client OpenAI-compatible API on port `11434` (`http://127.0.0.1:11434/v1`).
  3. Introduced a **hard 2.0-second timeout** on intent routing and a **5.0-second timeout** on local coder inference.
  4. Added an automated failover to OpenRouter's 550B free cloud neural mesh (`nvidia/nemotron-3-ultra-550b:free`). If local GPU VRAM is congested, the system automatically falls over in 5s and completes generation in 1.8s.

---

### Failure 03: The Premature STT Audio Clipper (150ms Silence Bug)

* **Date & Context**: Hands-free voice testing using Windows `System.Speech` speech recognition.
* **Observed Symptom**: In voice mode, whenever the user took a natural breath between clauses or thought for a split second, the microphone immediately closed. The system attempted to process fragments like *"how..."* or returned an empty string.
* **Root-Cause Analysis (RCA)**:
  1. Inspecting the PowerShell STT automation script revealed that `EndSilenceTimeout` was configured to `0.15` seconds (150 ms).
  2. Human speech cadences—especially when formulating complex technical queries—frequently include natural inter-clause pauses of 400 ms to 1,000 ms.
  3. The recognition engine treated any brief 150 ms drop in audio amplitude as the definitive end of user transmission, terminating input prematurely.
* **Resolution**:
  1. Recalibrated the speech recognition timeouts in `src/voice.py`:
     * `EndSilenceTimeout`: Increased from `0.15s` to **`1.8s`** (allows natural conversational pauses).
     * `InitialSilenceTimeout`: Increased to **`10.0s`** (gives the user ample time to begin speaking).
     * `BabbleTimeout`: Set to **`4.0s`**.
  2. Implemented a multi-phrase accumulation loop: if audio input continues after a short pause, the recognized text segments are concatenated into a single coherent prompt before dispatching to the mentor.

---

### Failure 04: The High-Frequency CRT Scanline Moiré Fatigue

* **Date & Context**: UI/UX review of the Web Ops-Center HUD.
* **Observed Symptom**: User reported: *"The text hurts the eyes to look at because the font isn't very smooth."* Reading longer mentor explanations was physically uncomfortable after 5–10 minutes.
* **Root-Cause Analysis (RCA)**:
  1. The original cyberpunk design implemented an aesthetic CRT television effect using a CSS pseudo-element:
     ```css
     background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%);
     background-size: 100% 2px;
     ```
  2. On high-DPI modern displays (e.g., 1080p/1440p/4K laptop screens), alternating dark 1px horizontal bands create optical Moiré patterns and micro-flicker as the eye tracks across lines of text.
  3. Additionally, rendering paragraphs in thin monospace fonts caused glyph stems to collide with the scanlines, creating perceived blurriness.
* **Resolution**:
  1. Completely eradicated horizontal scanline overlays.
  2. Replaced the background with a subtle, non-intrusive static dot grid:
     ```css
     background-image: radial-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px);
     background-size: 24px 24px;
     ```
  3. Shifted body typography to a clean, highly legible system sans-serif stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", Roboto`), reserving monospace strictly for code blocks (`<pre><code>`) and tactical HUD telemetry badges.

---

### Failure 05: The UTF-8 Byte Order Mark (BOM) Parser Breakage

* **Date & Context**: System startup and AST syntax verification across `src/`.
* **Observed Symptom**: Python's compiler failed during automated syntax verification:
  ```text
  SyntaxError: invalid non-printable character U+FEFF
  ```
* **Root-Cause Analysis (RCA)**:
  1. Certain Windows-native editing commands and legacy PowerShell `Out-File` cmdlets default to encoding files with a UTF-8 Byte Order Mark (`b'\xef\xbb\xbf'`) at byte index 0.
  2. Python's AST parser (`ast.parse`) strictly expects clean UTF-8 text. When a BOM is present at the start of a script, the parser reads `\ufeffimport os` instead of `import os`, causing a fatal syntax error.
* **Resolution**:
  1. Built an automated byte-level inspection utility that iterated across every `.py` file in `src/`.
  2. Checked `data.startswith(b'\xef\xbb\xbf')` and stripped the 3-byte prefix from all affected scripts.
  3. Added an automated validation check in `test_system.py` to ensure all repository source files are saved in clean BOM-free UTF-8.
