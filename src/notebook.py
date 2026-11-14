"""
AVA // THE MACHINE — Study Notebook Sync Module
================================================
Watches study_notebook/references/ for new files (PDF, Markdown, TXT).
Extracts text into RAM using PyMuPDF (PDF) or plain read (md/txt).
Indexes everything with the existing TF-IDF retriever — zero disk growth.
Exports takeaways from session history to study_notebook/takeaways/.

Supported file types:
  .pdf   — extracted via PyMuPDF (fitz), page-by-page into RAM
  .md    — raw markdown read
  .txt   — raw text read

Usage from mentor.py / ui_server.py:
  from notebook import NotebookIndex
  nb = NotebookIndex()
  nb.scan()                        # scan references/ on startup
  passages = nb.query("IAM least privilege", top_k=3)
  nb.export_takeaways(history)     # write today's session summary
"""

import re
import os
import math
from pathlib import Path
from datetime import datetime
from collections import Counter

import numpy as np
from scipy.sparse import csr_matrix

try:
    import fitz  # PyMuPDF
    _PYMUPDF = True
except ImportError:
    _PYMUPDF = False

try:
    from pypdf import PdfReader
    _PYPDF = True
except ImportError:
    _PYPDF = False

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_ROOT   = WORKSPACE_ROOT / "study_notebook"
REFERENCES_DIR  = NOTEBOOK_ROOT / "references"
TAKEAWAYS_DIR   = NOTEBOOK_ROOT / "takeaways"
QUIZZES_DIR     = NOTEBOOK_ROOT / "quizzes"

for d in [REFERENCES_DIR, TAKEAWAYS_DIR, QUIZZES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

README_PATH = NOTEBOOK_ROOT / "README.md"
if not README_PATH.exists():
    README_PATH.write_text(
        "# AVA // THE MACHINE — Study Notebook\n\n"
        "Drop any reference file into `references/` and Ava will index it in RAM:\n\n"
        "| Folder | Purpose |\n"
        "| :--- | :--- |\n"
        "| `references/` | Your study materials: PDFs, Markdown notes, TXT cheat-sheets |\n"
        "| `takeaways/` | Auto-generated session summaries exported by Ava |\n"
        "| `quizzes/` | Auto-generated quiz banks from your study materials |\n\n"
        "> Files are read into RAM only. Ava never modifies your references.\n",
        encoding="utf-8"
    )


# ─── Text extraction helpers ────────────────────────────────────────────────

def _extract_pdf(path: Path) -> str:
    """Extract all text from a PDF entirely into RAM."""
    if _PYMUPDF:
        try:
            doc = fitz.open(str(path))
            pages = [page.get_text() for page in doc]
            doc.close()
            return "\n".join(pages)
        except Exception as e:
            print(f"[Notebook][PyMuPDF] Failed on {path.name}: {e}")
    if _PYPDF:
        try:
            reader = PdfReader(str(path))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            print(f"[Notebook][pypdf] Failed on {path.name}: {e}")
    return ""


def _extract_text(path: Path) -> str:
    """Read any supported file into a RAM string."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[Notebook] Cannot read {path.name}: {e}")
        return ""


# ─── TF-IDF helpers (pure NumPy / SciPy, matches retriever.py) ─────────────

def _tokenize(text: str) -> list:
    return re.findall(r"\b[a-zA-Z0-9_]{2,}\b", text.lower())


def _build_tfidf_matrix(passages: list) -> tuple:
    """
    Returns (csr_matrix, idf_vector, vocab_dict, norms_vector).
    All allocated in RAM — garbage-collected when the index goes out of scope.
    """
    docs_tokens = [_tokenize(p) for p in passages]
    vocab: dict = {}
    df = Counter()
    for tokens in docs_tokens:
        for t in set(tokens):
            df[t] += 1
            if t not in vocab:
                vocab[t] = len(vocab)

    n = len(passages)
    idf = np.zeros(len(vocab), dtype=np.float32)
    for term, idx in vocab.items():
        idf[idx] = math.log((n + 1) / (df[term] + 1)) + 1.0

    rows, cols, vals = [], [], []
    for r, tokens in enumerate(docs_tokens):
        tf = Counter(tokens)
        for term, count in tf.items():
            c = vocab.get(term)
            if c is not None:
                rows.append(r)
                cols.append(c)
                vals.append((1.0 + math.log(count)) * idf[c])

    if not rows:
        return csr_matrix((n, len(vocab)), dtype=np.float32), idf, vocab, np.ones(n)

    mat = csr_matrix((vals, (rows, cols)), shape=(n, len(vocab)), dtype=np.float32)
    norms = np.sqrt(mat.multiply(mat).sum(axis=1)).A1 + 1e-9
    return mat, idf, vocab, norms


# ─── Main Notebook Index ─────────────────────────────────────────────────────

class NotebookIndex:
    """
    Maintains an in-RAM TF-IDF index over all files in references/.
    Rebuilds automatically whenever scan() detects new or changed files.
    """

    def __init__(self):
        self._passages: list[dict] = []   # [{text, source, page}]
        self._mat = None
        self._idf = None
        self._vocab: dict = {}
        self._norms = None
        self._file_mtimes: dict = {}      # path → mtime for change detection
        self._indexed = False

    # ── Public API ────────────────────────────────────────────────────────

    def scan(self, chunk_size: int = 800) -> int:
        """
        Scans references/ for new or changed files and rebuilds the index.
        Returns the number of passages currently indexed.
        """
        supported = [".pdf", ".md", ".txt", ".rst"]
        changed = False

        for path in sorted(REFERENCES_DIR.iterdir()):
            if path.suffix.lower() not in supported:
                continue
            mtime = path.stat().st_mtime
            if self._file_mtimes.get(str(path)) == mtime:
                continue
            # New or modified file — extract and chunk
            self._file_mtimes[str(path)] = mtime
            raw = _extract_text(path)
            if not raw.strip():
                continue
            # Remove existing passages from this file, then re-add
            self._passages = [p for p in self._passages if p["source"] != path.name]
            for i, start in enumerate(range(0, len(raw), chunk_size)):
                chunk = raw[start:start + chunk_size].strip()
                if chunk:
                    self._passages.append({
                        "text": chunk,
                        "source": path.name,
                        "page": i + 1
                    })
            changed = True
            print(f"[Notebook] Indexed: {path.name} ({len(raw):,} chars)")

        if changed or not self._indexed:
            if self._passages:
                texts = [p["text"] for p in self._passages]
                self._mat, self._idf, self._vocab, self._norms = _build_tfidf_matrix(texts)
            self._indexed = True

        return len(self._passages)

    def query(self, query: str, top_k: int = 3, min_score: float = 0.08) -> list[dict]:
        """
        Returns the top-k most relevant passages from the indexed study materials.
        Each result: {text, source, page, score}
        Returns [] if no materials have been indexed.
        """
        if not self._passages or self._mat is None:
            return []

        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        q_vec = np.zeros(len(self._vocab), dtype=np.float32)
        q_tf = Counter(q_tokens)
        for term, count in q_tf.items():
            c = self._vocab.get(term)
            if c is not None:
                q_vec[c] = (1.0 + math.log(count)) * self._idf[c]

        q_norm = float(np.linalg.norm(q_vec)) + 1e-9
        scores = self._mat.dot(q_vec) / (self._norms * q_norm)
        top_idx = np.argsort(scores)[::-1][:top_k]

        results = []
        for i in top_idx:
            if scores[i] >= min_score:
                entry = dict(self._passages[i])
                entry["score"] = float(scores[i])
                results.append(entry)
        return results

    def list_sources(self) -> list[str]:
        """Returns the names of all currently indexed reference files."""
        seen = []
        for p in self._passages:
            if p["source"] not in seen:
                seen.append(p["source"])
        return seen

    def export_takeaways(self, history: list[dict], session_label: str = "") -> Path:
        """
        Writes a dated Markdown takeaways file from the current conversation history.
        Returns the path of the written file.
        """
        if not history:
            return None

        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
        label = session_label or date_str
        outpath = TAKEAWAYS_DIR / f"session_{label}.md"

        lines = [
            f"# AVA // THE MACHINE — Session Takeaways",
            f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
        ]

        q_num = 1
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "").strip()
            if not content:
                continue
            if role == "user":
                lines.append(f"### Q{q_num} — Operator")
                lines.append(f"> {content}")
                lines.append("")
            elif role == "assistant":
                lines.append(f"**AVA Response:**")
                lines.append(content)
                lines.append("")
                lines.append("---")
                lines.append("")
                q_num += 1

        outpath.write_text("\n".join(lines), encoding="utf-8")
        print(f"[Notebook] Takeaways exported → {outpath.name}")
        return outpath

    def generate_quiz(self, topic: str, history: list[dict], n_questions: int = 5) -> Path:
        """
        Asks Ava to generate a quiz from indexed materials and recent session history.
        Saves it to study_notebook/quizzes/. Returns the file path.
        (Full LLM integration wired via mentor.py's /quiz command.)
        """
        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
        outpath = QUIZZES_DIR / f"quiz_{topic.replace(' ', '_')}_{date_str}.md"
        # Actual generation is done via LLM in mentor.py's /quiz handler.
        # This method just returns the reserved output path.
        return outpath


# Module-level singleton — shared across mentor.py and ui_server.py
_GLOBAL_INDEX = NotebookIndex()


def get_notebook() -> NotebookIndex:
    """Returns the shared in-process notebook index singleton."""
    return _GLOBAL_INDEX
