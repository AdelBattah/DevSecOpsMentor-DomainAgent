#!/usr/bin/env python3
"""
init_vault.py - Bootstrapper for Ava Socratic Mentor Study Vault
Creates a standardized local Markdown vault in any workspace for persistent study.
"""

import sys
from pathlib import Path
from datetime import datetime

VAULT_STRUCTURE = [
    "study_vault/references",
    "study_vault/takeaways",
    "study_vault/quizzes",
]

VAULT_README = """# Local Study Vault & Knowledge Base

Managed autonomously by **Ava (Socratic Domain Mentor)**.

## Structure
- `references/`: Curated official technical documentation, architecture invariants, and cheat sheets pulled from live web research.
- `takeaways/`: Daily structured session takeaways, commands learned, and mental models exported at the conclusion of every study turn.
- `quizzes/`: Active recall question banks and spaced-repetition flashcard sets formatted for Anki / Google NotebookLM.

## Customization
Define your target domain in `domain_config.json` or tell Ava directly:
`Ava, set target domain to: <Your Domain>`
"""

DOMAIN_CONFIG = """{
  "target_domain": "Cloud Security & DevSecOps",
  "pedagogy": "socratic_anti_copilot",
  "strictness": "high",
  "allow_boilerplate": false,
  "created_at": "%s"
}
""" % datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def bootstrap_vault(target_dir: Path):
    print(f"[*] Initializing Ava Knowledge Vault in: {target_dir}")
    for folder in VAULT_STRUCTURE:
        p = target_dir / folder
        p.mkdir(parents=True, exist_ok=True)
        print(f"  [+] Created directory: {folder}")
    
    readme_path = target_dir / "study_vault" / "README.md"
    if not readme_path.exists():
        readme_path.write_text(VAULT_README, encoding="utf-8")
        print("  [+] Created: study_vault/README.md")
        
    config_path = target_dir / "study_vault" / "domain_config.json"
    if not config_path.exists():
        config_path.write_text(DOMAIN_CONFIG, encoding="utf-8")
        print("  [+] Created: study_vault/domain_config.json")
        
    print("[✔] Vault initialized successfully. Ready for Socratic mentoring.")

if __name__ == "__main__":
    target = Path.cwd() if len(sys.argv) < 2 else Path(sys.argv[1])
    bootstrap_vault(target)
