import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

# Ensure src is on sys.path
SRC_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SRC_DIR.parent
sys.path.insert(0, str(SRC_DIR))

from config import (
    ROUTER_MODEL, ROUTER_NUM_CTX,
    CODER_MODEL, CODER_NUM_CTX,
    REASONER_MODEL, REASONER_IS_REMOTE,
    get_llm_client
)
from mentor import run_mentor_turn, load_profile, DATASET_FILE
from voice import detect_audio_playback_device, listen, speak
from notebook import get_notebook, REFERENCES_DIR, TAKEAWAYS_DIR

UI_DIR = WORKSPACE_ROOT / "ui"

# In-memory session state
HISTORY = []

# Boot-time notebook scan
_NB = get_notebook()
try:
    _n = _NB.scan()
    if _n:
        print(f"[Notebook] {_n} passages loaded from study_notebook/references/")
except Exception as e:
    print(f"[Notebook] Scan skipped: {e}")

class MachineDevSecOpsHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.send_json_response(self.get_system_status())
        elif parsed.path == "/api/profile":
            self.send_json_response({"profile": load_profile()})
        elif parsed.path == "/api/dataset_count":
            count = 0
            if DATASET_FILE.exists():
                with open(DATASET_FILE, "r", encoding="utf-8") as f:
                    count = sum(1 for _ in f)
            self.send_json_response({"count": count})
        elif parsed.path == "/api/notebook/status":
            _NB.scan()
            sources = _NB.list_sources()
            self.send_json_response({
                "sources": sources,
                "passage_count": len(_NB._passages),
                "references_dir": str(REFERENCES_DIR),
                "takeaways_dir": str(TAKEAWAYS_DIR),
            })
        elif parsed.path in ["/", "/index.html"]:
            self.path = "/index.html"
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        
        try:
            data = json.loads(post_body)
        except Exception:
            data = {}

        if parsed.path == "/api/chat":
            query = data.get("query", "").strip()
            voice_out = data.get("voice", False)
            if not query:
                self.send_json_response({"error": "Empty query"}, status=400)
                return

            profile = load_profile()
            response, role = run_mentor_turn(query, HISTORY, profile, voice_enabled=False)
            HISTORY.append({"role": "user", "content": query})
            HISTORY.append({"role": "assistant", "content": response})

            # Check dataset count
            count = 0
            if DATASET_FILE.exists():
                with open(DATASET_FILE, "r", encoding="utf-8") as f:
                    count = sum(1 for _ in f)

            self.send_json_response({
                "response": response,
                "role": role,
                "dataset_count": count
            })

        elif parsed.path == "/api/listen":
            # Trigger STT via Windows System.Speech
            timeout = int(data.get("timeout", 15))
            heard = listen(timeout_seconds=timeout, beep=True)
            self.send_json_response({"text": heard or ""})

        elif parsed.path == "/api/speak":
            text = data.get("text", "")
            if text:
                interrupted = speak(text)
                self.send_json_response({"status": "ok", "interrupted": interrupted or ""})
            else:
                self.send_json_response({"status": "empty"})

        elif parsed.path == "/api/clear":
            HISTORY.clear()
            self.send_json_response({"status": "cleared"})

        elif parsed.path == "/api/notebook/sync":
            # Export current session as takeaways Markdown
            if not HISTORY:
                self.send_json_response({"status": "empty", "message": "No session history to export."})
                return
            outpath = _NB.export_takeaways(HISTORY)
            self.send_json_response({
                "status": "ok",
                "file": outpath.name,
                "path": str(outpath),
            })

        else:
            self.send_json_response({"error": "Not Found"}, status=404)

    def send_json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def get_system_status(self):
        is_hp, dev_name = detect_audio_playback_device()
        total, used, free = shutil.disk_usage("C:\\")
        
        # Dataset records
        count = 0
        if DATASET_FILE.exists():
            with open(DATASET_FILE, "r", encoding="utf-8") as f:
                count = sum(1 for _ in f)

        return {
            "system_state": "ONLINE",
            "gpu": "NVIDIA GeForce RTX 5060 Laptop (8 GB VRAM)",
            "gpu_vram_limit": "8.0 GB",
            "models": {
                "router": f"{ROUTER_MODEL} (16k ctx)",
                "coder": f"{CODER_MODEL} (8k ctx, Local 8GB)",
                "reasoner": f"{REASONER_MODEL} ({'Cloud Free 1M' if REASONER_IS_REMOTE else 'Offline Local'})"
            },
            "audio": {
                "device": dev_name,
                "is_headphones": is_hp,
                "barge_in": "FULL DUPLEX VOICE + KEY" if is_hp else "KEYBOARD TAP (ENTER)"
            },
            "disk_free_gb": f"{free / (1024**3):.2f} GB",
            "dataset_count": count
        }

def start_ui_server(port=8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), MachineDevSecOpsHandler)
    print("=" * 65)
    print("  DEVSECOPS OPS-CENTER & THE MACHINE HUD ACTIVE")
    print(f"  Target URL: http://127.0.0.1:{port}")
    print("  Press Ctrl+C to stop the UI server.")
    print("=" * 65)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nUI Server shutdown.")
        server.server_close()

if __name__ == "__main__":
    start_ui_server()
