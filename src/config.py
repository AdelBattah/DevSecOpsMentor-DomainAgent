import os
from pathlib import Path
from openai import OpenAI
import httpx

# Workspace root
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

# Standard library .env loader (zero external dependencies)
def _load_env_file(path: Path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key not in os.environ:
                        os.environ[key] = val

_load_env_file(WORKSPACE_ROOT / ".env")

# Local Ollama default endpoints
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")

# 8 GB VRAM-optimized parameters
ROUTER_MODEL = "qwen2.5:3b"
ROUTER_NUM_CTX = 16384  # Fast intent router (1.9 GB model, 16k context fits easily in 8 GB VRAM)

CODER_MODEL = "Qwen2.5-Coder:latest"
CODER_NUM_CTX = 8192    # Code & Lab Mentor (4.7 GB model, 8k context stays 100% inside 8 GB VRAM)

# Heavy Reasoner configuration: OpenRouter Free tier with offline local fallback
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Free-tier model chain: nemotron-ultra (550B, 1M ctx) → openrouter/free (auto-routes)
# Both are $0.00 — no credits required
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
OPENROUTER_MODEL_FALLBACK = "openrouter/free"   # auto-routes to best available free model

OFFLINE_FALLBACK_MODEL = "qwen3.5:9b-q4_K_M"
OFFLINE_FALLBACK_NUM_CTX = 4096

if OPENROUTER_API_KEY:
    REASONER_MODEL = OPENROUTER_MODEL
    REASONER_MODEL_FALLBACK = OPENROUTER_MODEL_FALLBACK
    REASONER_BASE_URL = OPENROUTER_BASE_URL
    REASONER_API_KEY = OPENROUTER_API_KEY
    REASONER_IS_REMOTE = True
    REASONER_NUM_CTX = 32768          # nemotron-ultra supports 1M ctx; cap at 32k for speed
else:
    REASONER_MODEL = OFFLINE_FALLBACK_MODEL
    REASONER_MODEL_FALLBACK = OFFLINE_FALLBACK_MODEL
    REASONER_BASE_URL = OLLAMA_BASE_URL
    REASONER_API_KEY = OLLAMA_API_KEY
    REASONER_IS_REMOTE = False
    REASONER_NUM_CTX = OFFLINE_FALLBACK_NUM_CTX


def get_llm_client(role: str = "coder"):
    """
    Returns an (OpenAI client, model_name, options_dict) tuple tailored for 8 GB VRAM.
    Uses official local Ollama endpoint for coder/router, and OpenRouter for heavy reasoning.
    """
    if role == "router":
        return (
            OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY),
            ROUTER_MODEL,
            {"num_ctx": ROUTER_NUM_CTX}
        )

    elif role == "coder":
        return (
            OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY),
            CODER_MODEL,
            {"num_ctx": CODER_NUM_CTX}
        )

    elif role == "reasoner":
        if REASONER_IS_REMOTE:
            return (
                OpenAI(
                    base_url=REASONER_BASE_URL,
                    api_key=REASONER_API_KEY,
                    default_headers={
                        "HTTP-Referer": "https://github.com/domain-agent",
                        "X-Title": "DevSecOps-Mentor",
                    },
                ),
                REASONER_MODEL,
                {}
            )
        else:
            return (
                OpenAI(base_url=REASONER_BASE_URL, api_key=REASONER_API_KEY),
                REASONER_MODEL,
                {"num_ctx": REASONER_NUM_CTX}
            )

    raise ValueError(f"Unknown role: {role}")
