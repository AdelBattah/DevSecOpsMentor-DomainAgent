import re
import math
from collections import Counter
import httpx
import numpy as np
from scipy.sparse import csr_matrix

def clean_html(raw_html: str) -> str:
    """Strips HTML tags, styles, scripts, and normalizes whitespace in RAM."""
    if not raw_html:
        return ""
    text = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", " ", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z0-9#]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def stream_text_from_url(url: str, max_chars: int = 150000) -> str:
    """Streams documentation text directly into RAM without saving any files to disk."""
    chunks = []
    total = 0
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DevSecOps-Mentor-Agent/1.0"
    }
    with httpx.stream("GET", url, timeout=15.0, follow_redirects=True, headers=headers) as r:
        r.raise_for_status()
        for chunk in r.iter_text():
            chunks.append(chunk)
            total += len(chunk)
            if total >= max_chars:
                break
    raw_content = "".join(chunks)
    if "<html" in raw_content.lower() or "<body" in raw_content.lower() or "<div" in raw_content.lower():
        return clean_html(raw_content)
    return raw_content.strip()

def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-zA-Z0-9_]{2,}\b", text.lower())

def extract_top_passages(raw_text: str, query: str, top_k: int = 5, chunk_size: int = 600) -> list[dict]:
    """Sub-20ms CPU extractive retrieval using pure NumPy + SciPy sparse matrices in RAM."""
    if not raw_text or not query:
        return []

    passages = [raw_text[i:i+chunk_size].strip() for i in range(0, len(raw_text), chunk_size) if raw_text[i:i+chunk_size].strip()]
    if not passages:
        return []

    docs_tokens = [_tokenize(p) for p in passages]
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    vocab = {}
    df = Counter()
    for tokens in docs_tokens:
        unique_t = set(tokens)
        for t in unique_t:
            df[t] += 1
            if t not in vocab:
                vocab[t] = len(vocab)

    n_docs = len(passages)
    idf = np.zeros(len(vocab), dtype=np.float32)
    for term, idx in vocab.items():
        idf[idx] = math.log((n_docs + 1) / (df[term] + 1)) + 1.0

    rows, cols, vals = [], [], []
    for r, tokens in enumerate(docs_tokens):
        tf = Counter(tokens)
        for term, count in tf.items():
            c = vocab[term]
            rows.append(r)
            cols.append(c)
            vals.append((1.0 + math.log(count)) * idf[c])

    doc_mat = csr_matrix((vals, (rows, cols)), shape=(n_docs, len(vocab)), dtype=np.float32)
    norms = np.sqrt(doc_mat.multiply(doc_mat).sum(axis=1)).A1 + 1e-9

    q_vec = np.zeros(len(vocab), dtype=np.float32)
    q_tf = Counter(query_tokens)
    for term, count in q_tf.items():
        if term in vocab:
            c = vocab[term]
            q_vec[c] = (1.0 + math.log(count)) * idf[c]

    q_norm = np.linalg.norm(q_vec) + 1e-9
    scores = (doc_mat.dot(q_vec)) / (norms * q_norm)

    top_indices = np.argsort(scores)[::-1][:top_k]
    return [{"score": float(scores[idx]), "text": passages[idx]} for idx in top_indices if scores[idx] > 0]
