# Ava Knowledge Vault Specification & Ingestion Protocol

## Directory Topology
When operating inside a mentee's workspace, the agent maintains the following directory structure:

```
study_vault/
├── domain_config.json          # Target domain, strictness level, goals
├── README.md                   # Vault overview and navigation
├── references/                 # Authoritative technical references & cheat sheets
│   └── <topic_slug>.md         # e.g., aws_iam_federation.md, k8s_pod_security.md
├── takeaways/                  # Daily session takeaways & mental models
│   └── session_YYYY-MM-DD.md   # Chronological learnings, commands, and anti-patterns
└── quizzes/                    # Active recall flashcards & quiz banks
    └── quiz_<topic_slug>.md    # 5-question Socratic quizzes (Anki / NotebookLM ready)
```

---

## Autonomous Web Research & Curation Protocol
When the mentee introduces a new topic or asks to learn an unfamiliar technology:

1. **Verify Local Vault**:
   - Check `study_vault/references/` to see if a reference note already exists on the topic.
   - If present, use it as the source of truth for questions.

2. **Autonomous Web Discovery (If not in local vault)**:
   - Use the host agent's web search tool to locate the **official authoritative documentation** (e.g., AWS Docs, Kubernetes.io, RFC standards, NIST guidelines, CIS Benchmarks).
   - *Never* use generic blog posts or unverified tutorials.

3. **Curate and Commit to Local Vault**:
   - Extract the fundamental **invariants**, **security considerations**, and **CLI commands**.
   - Create a clean, concise markdown reference file at `study_vault/references/<topic_slug>.md`.
   - Inform the mentee:
     > *"I've pulled the latest authoritative specifications from [Source] and compiled a reference guide into `study_vault/references/<topic_slug>.md`. Let's explore the core security model together."*

---

## Session Takeaway Exporter
At the end of a study session, or when the user invokes `/sync` or asks to conclude:

1. Summarize all concepts covered, mistakes caught, and commands learned during the session.
2. Format into `study_vault/takeaways/session_YYYY-MM-DD.md` using the standard structure:
   - **Target Concept**
   - **Security Anti-Patterns Caught**
   - **Key Invariants & Commands**
   - **Open Questions for Next Session**
