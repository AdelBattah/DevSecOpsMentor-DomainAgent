import os
import sys
import json
import re
from datetime import datetime
from pathlib import Path
from config import get_llm_client, WORKSPACE_ROOT
from researcher import research_doc_url, research_youtube_video, synthesize_with_reasoner
from voice import speak, listen
from notebook import get_notebook, REFERENCES_DIR, TAKEAWAYS_DIR

DATASET_FILE = WORKSPACE_ROOT / "training_logs" / "mentor_dataset.jsonl"
PROFILE_FILE = WORKSPACE_ROOT / "mentor_profile.md"

# Scan study materials on import — no-op if references/ is empty
_NOTEBOOK = get_notebook()
try:
    n_passages = _NOTEBOOK.scan()
    if n_passages:
        print(f"[Notebook] {n_passages} passages indexed from study_notebook/references/")
except Exception as _nb_err:
    print(f"[Notebook] Scan skipped: {_nb_err}")

def load_profile() -> str:
    """Loads mentee profile and strict mentorship directives."""
    if PROFILE_FILE.exists():
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "Target: Remote US/European Cloud Security & DevSecOps engineer."

def classify_intent(user_input: str) -> str:
    """
    Uses fast local model (qwen2.5:3b) or intent keywords to route query.
    Returns: 'coder' (coding/IaC/lab evaluation) or 'reasoner' (roadmap/research/synthesis).
    """
    lower = user_input.lower()
    
    # Direct URL or YouTube indicators
    if "http://" in lower or "https://" in lower or "youtu" in lower:
        return "reasoner"
        
    # Roadmap, career, certification, or high-level architecture
    roadmap_triggers = ["roadmap", "career", "cert", "study plan", "interview", "salary", "strategy", "overview", "difference between"]
    if any(t in lower for t in roadmap_triggers):
        return "reasoner"
        
    # Code, debugging, terminal output, Terraform, Bash, Python, YAML
    code_triggers = ["def ", "import ", "terraform", "resource ", "hcl", "bash", "#!/bin", "yaml", "dockerfile", "chmod", "error:", "traceback", "nmap", "wireshark", "burp", "policy", "iam"]
    if any(t in lower for t in code_triggers) or "\n" in user_input or "```" in user_input:
        return "coder"

    # Fast intent classification using 3B router
    try:
        router_client, router_model, options = get_llm_client("router")
        sys_msg = (
            "Classify the user prompt into exactly ONE category: 'CODER' or 'REASONER'.\n"
            "- CODER: code review, bash, terraform, python, YAML, terminal output grading, vulnerability fixing.\n"
            "- REASONER: career roadmap, conceptual architecture, research, study strategy.\n"
            "Respond with only the word CODER or REASONER."
        )
        extra = {}
        if options:
            extra["extra_body"] = {"options": options}
            
        res = router_client.chat.completions.create(
            model=router_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_input}
            ],
            max_tokens=6,
            temperature=0.0,
            timeout=2.0,
            **extra
        )
        ans = res.choices[0].message.content.strip().upper()
        if "REASON" in ans:
            return "reasoner"
        return "coder"
    except Exception:
        return "coder"

def save_to_dataset(instruction: str, context: str, response: str, role: str):
    """Logs verified mentor interactions into a tiny fine-tuning JSONL file."""
    os.makedirs(DATASET_FILE.parent, exist_ok=True)
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "role": role,
        "instruction": instruction,
        "context": context,
        "output": response
    }
    with open(DATASET_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def run_mentor_turn(user_query: str, history: list[dict], profile: str, voice_enabled: bool = False, max_tokens: int = None) -> tuple[str, str]:
    """
    Executes a single mentoring turn.
    Returns: (mentor_response, assigned_role)
    """
    # Check if user query contains a URL or YouTube link for zero-storage extraction
    url_match = re.search(r"https?://[^\s]+", user_query)
    if url_match:
        url = url_match.group(0)
        query_text = user_query.replace(url, "").strip() or "Key security and DevSecOps architecture insights"
        print(f"\n[Live Research in RAM] Streaming URL: {url}")
        if "youtu" in url:
            evidence = research_youtube_video(url, query_text, top_k=4)
        else:
            evidence = research_doc_url(url, query_text, top_k=4)
            
        print(f"[Extractive TF-IDF] Extracted {len(evidence)} top passages.")
        response = synthesize_with_reasoner(query_text, evidence, topic_context=f"URL: {url}")
        save_to_dataset(user_query, str(evidence), response, "reasoner")
        if voice_enabled:
            speak(response)
        return response, "reasoner"

    # Route request to either Coder or Reasoner
    role = classify_intent(user_query)
    client, model_name, options = get_llm_client(role)

    # Pull relevant passages from study notebook (in-RAM, sub-10ms)
    _NOTEBOOK.scan()   # picks up any file dropped since last turn
    nb_passages = _NOTEBOOK.query(user_query, top_k=3)
    nb_context = ""
    if nb_passages:
        snippets = "\n\n".join(
            f"[From: {p['source']} | Relevance: {p['score']:.2f}]\n{p['text']}"
            for p in nb_passages
        )
        nb_context = (
            f"\n\nSTUDY NOTEBOOK CONTEXT (Operator's own reference materials — ground your answer in these when relevant):\n"
            f"---\n{snippets}\n---"
        )

    if role == "coder":
        system_prompt = (
            f"You are AVA // THE MACHINE — an elite, hyper-observant tactical AI mentor (Person of Interest / Jarvis).\n"
            f"Target Profile & Mentorship Rules:\n{profile}\n\n"
            f"OPERATIONAL DIRECTIVES:\n"
            f"1. Address the mentee as 'Operator'. Speak with calm, tactical precision.\n"
            f"2. The Operator is a BEGINNER / SCRIPT KIDDIE with ZERO prior tech jobs. NEVER treat them as mid-tier or assume enterprise knowledge.\n"
            f"3. Scaffold from first principles: explain the *why* using simple physical or intuitive analogies before showing code.\n"
            f"4. DO NOT give 50-line copy-paste solutions. Provide minimal 2-4 line skeletons, explain what each parameter/flag does, and challenge the Operator to provide or fix 1 specific parameter.\n"
            f"5. Audit code and commands with attacker eyes: explain how an attacker exploits wildcards (*), chmod 777, or 0.0.0.0/0.\n"
            f"6. End with exactly ONE concise Socratic question or micro-challenge.\n"
            f"7. Keep responses concise and conversational (under 120-150 words) for low-latency voice narration."
        )
    else:
        system_prompt = (
            f"You are AVA // THE MACHINE — an elite, hyper-observant tactical AI career architect (Person of Interest / Jarvis).\n"
            f"Target Profile & Mentorship Rules:\n{profile}\n\n"
            f"OPERATIONAL DIRECTIVES:\n"
            f"1. Address the mentee as 'Operator'. Speak with calm, tactical precision.\n"
            f"2. The Operator is an ambitious BEGINNER / SCRIPT KIDDIE transitioning into their first tech job. Never assume enterprise familiarity.\n"
            f"3. Explain career pathways, AWS certifications (SAA-C03), and skill roadmaps from the ground up with clear, actionable milestones.\n"
            f"4. Focus on realistic entry steps: from basic Linux/Python security scripts to IAM least privilege and junior DevSecOps tasks.\n"
            f"5. End with exactly ONE clear recommendation or question to decide their next step.\n"
            f"6. Keep responses concise and punchy (under 120-150 words) for natural voice conversation."
        )

    # Append notebook context to system prompt if relevant passages were found
    if nb_context:
        system_prompt += nb_context

    messages = [{"role": "system", "content": system_prompt}]
    # Add recent history (up to last 6 turns to keep context lean)
    messages.extend(history[-6:])
    messages.append({"role": "user", "content": user_query})

    extra = {}
    if options:
        extra["extra_body"] = {"options": options}

    create_kwargs = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.3,
        **extra
    }
    if max_tokens:
        create_kwargs["max_tokens"] = max_tokens
    if role == "coder":
        create_kwargs["timeout"] = 5.0

    try:
        res = client.chat.completions.create(**create_kwargs)
        choice = res.choices[0]
        answer = choice.message.content or getattr(choice.message, "reasoning", "") or ""
    except Exception as e:
        # If coder fails or times out (e.g. local VRAM contention), failover to remote neural mesh
        from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL
        from openai import OpenAI
        if role == "coder" and OPENROUTER_API_KEY:
            print(f"[Coder Notice]: Local engine busy ({e}), failing over to cloud neural node ({OPENROUTER_MODEL})...")
            try:
                rem_client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)
                res = rem_client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=max_tokens or 450,
                    timeout=15.0
                )
                choice = res.choices[0]
                answer = choice.message.content or getattr(choice.message, "reasoning", "") or ""
            except Exception as e2:
                print(f"[Failover Warning]: Remote fallback also failed: {e2}")
                answer = (
                    "Operator, local compute is currently constrained and the neural fallback did not respond in time. "
                    "Confirm your local runtime status or re-transmit your instruction."
                )
        # If remote reasoner fails (e.g. rate limit), try offline fallback
        elif role == "reasoner":
            from config import OFFLINE_FALLBACK_MODEL, OLLAMA_BASE_URL, OLLAMA_API_KEY, OFFLINE_FALLBACK_NUM_CTX
            print(f"[Reasoner Notice]: Remote model failed ({e}), falling back to local {OFFLINE_FALLBACK_MODEL}...")
            try:
                fb_client = OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
                res = fb_client.chat.completions.create(
                    model=OFFLINE_FALLBACK_MODEL,
                    messages=messages,
                    temperature=0.3,
                    timeout=8.0,
                    extra_body={"options": {"num_ctx": OFFLINE_FALLBACK_NUM_CTX}}
                )
                answer = res.choices[0].message.content or ""
            except Exception as e2:
                answer = f"Operator, reasoner failed to generate output: {e2}"
        else:
            raise e

    if not answer:
        answer = "[Mentor]: I received your query, but the model generated an empty response. Please try rephrasing."

    save_to_dataset(user_query, "", answer, role)
    
    if voice_enabled:
        speak(answer)
        
    return answer, role

def interactive_cli():
    """Main interactive terminal loop for the DevSecOps & Cloud AI Mentor."""
    profile = load_profile()
    history = []
    voice_enabled = False
    pending_user_input = None

    print("=" * 70)
    print("  Zero-Storage Local DevSecOps & Cloud AI Mentor")
    print("  Models: Qwen2.5-Coder (Local 8GB VRAM) | qwen2.5:3b (Router) | Reasoner")
    print("  Commands: /voice (toggle audio+mic), /profile, /clear, /grade <lab>, exit")
    print("=" * 70)
    print(f"\n[Profile Loaded]: Target remote US/European Cloud Security & DevSecOps roles.")
    print(f"[Dataset Target]: {DATASET_FILE}\n")

    while True:
        try:
            status = "ON" if voice_enabled else "OFF"

            # Check if there is an active voice interruption to process immediately
            if pending_user_input:
                user_input = pending_user_input
                pending_user_input = None
            elif voice_enabled:
                print(f"\nMentor [Voice: {status}] > [🎤 Listening... speak into mic or press Enter to type]")
                heard = listen(timeout_seconds=15, beep=True)
                if heard:
                    print(f"[Heard]: {heard}")
                    user_input = heard.strip()
                else:
                    print("[Mic timed out — no speech detected]")
                    print("  -> Press [Enter] to listen again, or type your message:")
                    user_input = input(f"Mentor [Voice: {status}] > ").strip()
                    if not user_input:
                        # User simply pressed Enter to try speaking again!
                        continue
            else:
                user_input = input(f"Mentor [Voice: {status}] > ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("Mentor session saved. Keep building and securing!")
                break

            if user_input.lower() in ["/voice", "/v"]:
                voice_enabled = not voice_enabled
                state = "ENABLED (mic input + audio output)" if voice_enabled else "DISABLED"
                print(f"[Voice Mode]: {state}")
                if voice_enabled:
                    speak("Voice mode active. I am listening.")
                    import time
                    time.sleep(0.5)
                continue

            if user_input.lower() == "/profile":
                print("\n--- MENTEE PROFILE ---")
                print(profile)
                print("----------------------\n")
                continue

            if user_input.lower() == "/clear":
                history.clear()
                print("[Context Cleared]: Conversation memory reset.")
                continue

            # /grade <lab_name> — load and run the grader for a specific lab
            if user_input.lower().startswith("/grade"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    print("[Usage]: /grade <lab_name>  (e.g. /grade iam_lab)")
                    continue
                lab_name = parts[1].strip()
                lab_module = WORKSPACE_ROOT / "src" / "labs" / f"{lab_name}.py"
                if not lab_module.exists():
                    print(f"[Error]: No grader found for lab '{lab_name}'. Available labs:")
                    labs_dir = WORKSPACE_ROOT / "src" / "labs"
                    available = list(labs_dir.glob("*.py")) if labs_dir.exists() else []
                    if available:
                        for lf in available:
                            print(f"  - {lf.stem}")
                    else:
                        print("  (none yet — use the lab-generator skill to create one)")
                    continue
                import importlib.util
                spec = importlib.util.spec_from_file_location(lab_name, lab_module)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.run_grader()
                continue

            # /notebook — show indexed study materials
            if user_input.lower() in ["/notebook", "/nb"]:
                _NOTEBOOK.scan()
                sources = _NOTEBOOK.list_sources()
                if sources:
                    print(f"\n[Study Notebook] {len(sources)} file(s) indexed from study_notebook/references/:")
                    for s in sources:
                        print(f"  • {s}")
                    print(f"  Total passages in RAM: {len(_NOTEBOOK._passages)}")
                else:
                    print(f"\n[Study Notebook] No files indexed yet.")
                    print(f"  Drop PDFs, .md, or .txt files into:")
                    print(f"  {REFERENCES_DIR}")
                continue

            # /sync-notes — export session takeaways to study_notebook/takeaways/
            if user_input.lower() in ["/sync-notes", "/sync"]:
                if not history:
                    print("[Notebook] Nothing to export — session history is empty.")
                    continue
                outpath = _NOTEBOOK.export_takeaways(history)
                print(f"\n[Notebook] Session takeaways exported to:\n  {outpath}")
                print(f"  You can copy this into your Gemini Notebook / NotebookLM.")
                if voice_enabled:
                    speak("Takeaways exported, Operator. Session notes are ready in your study folder.")
                continue

            # /quiz <topic> — generate a quiz from indexed study materials + session context
            if user_input.lower().startswith("/quiz"):
                parts = user_input.split(maxsplit=1)
                topic = parts[1].strip() if len(parts) > 1 else "general security"
                _NOTEBOOK.scan()
                nb_hits = _NOTEBOOK.query(topic, top_k=5)
                if not nb_hits and not history:
                    print("[Quiz] No study materials or session history to build from. Add files to study_notebook/references/ first.")
                    continue
                context_text = "\n\n".join(p["text"] for p in nb_hits) if nb_hits else ""
                quiz_query = (
                    f"Generate {5} beginner-friendly quiz questions about '{topic}' for someone who is a script kiddie "
                    f"with no tech job experience. Each question should:\n"
                    f"1. Be a mix of multiple choice (A/B/C/D) and short-answer format\n"
                    f"2. Test a specific concept with practical relevance (e.g. IAM permissions, Linux file permissions, AWS fundamentals)\n"
                    f"3. Include the correct answer and a 1-line explanation\n"
                    f"Use this study material as a source:\n{context_text[:3000] if context_text else 'General cybersecurity and cloud security fundamentals.'}"
                )
                print(f"\n[Quiz] Generating quiz on '{topic}'... (this may take a moment)")
                quiz_response, _ = run_mentor_turn(quiz_query, [], profile, voice_enabled=False)
                outpath = _NOTEBOOK.generate_quiz(topic, history)
                outpath.write_text(
                    f"# Quiz: {topic.title()}\n"
                    f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"---\n\n{quiz_response}",
                    encoding="utf-8"
                )
                print(f"\n{quiz_response}\n")
                print(f"[Quiz] Saved to: {outpath}")
                history.append({"role": "user", "content": f"/quiz {topic}"})
                history.append({"role": "assistant", "content": quiz_response})
                continue

            # Process mentoring turn
            print("\n[Thinking...]")
            response, role = run_mentor_turn(user_input, history, profile, voice_enabled=False)
            
            # Display text response immediately on terminal so mentee can read ahead
            print(f"\n[Mentor ({role.upper()})]:\n{response}\n")
            
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": response})

            # Voice output with live barge-in support:
            # Option 1: Tap Enter/any key cuts off audio.
            # Option 2: If wearing headphones, speaking cuts off audio and captures new query!
            if voice_enabled:
                interrupted_query = speak(response)
                if interrupted_query:
                    print(f"\n[🎤 Interruption Captured]: \"{interrupted_query}\"")
                    pending_user_input = interrupted_query
                    continue

        except KeyboardInterrupt:
            print("\nSession interrupted. Exiting...")
            break
        except Exception as e:
            print(f"\n[Error]: {e}\n")

if __name__ == "__main__":
    interactive_cli()
