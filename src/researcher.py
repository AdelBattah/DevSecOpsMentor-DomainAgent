import re
from typing import Optional
import httpx
from retriever import stream_text_from_url, extract_top_passages
from config import get_llm_client, REASONER_IS_REMOTE, REASONER_MODEL_FALLBACK, REASONER_BASE_URL, REASONER_API_KEY

def extract_video_id(url_or_id: str) -> str:
    """Extracts the 11-character YouTube video ID from various URL formats or raw ID."""
    clean_input = url_or_id.strip()
    patterns = [
        r"(?:v=|\/embed\/|\/v\/|youtu\.be\/|\/watch\?v=|\/shorts\/)([0-9A-Za-z_-]{11})",
        r"^([0-9A-Za-z_-]{11})$"
    ]
    for pattern in patterns:
        match = re.search(pattern, clean_input)
        if match:
            return match.group(1)
    return clean_input

def fetch_youtube_transcript(url_or_id: str) -> str:
    """
    Fetches transcript text for a YouTube video directly in RAM without saving any files.
    Gracefully handles disabled captions, private videos, and network timeouts.
    """
    video_id = extract_video_id(url_or_id)
    if not video_id or len(video_id) != 11:
        return f"[Notice: Invalid YouTube Video ID: '{video_id}']"

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return "[Notice: youtube-transcript-api library is not installed]"

    try:
        # Check if legacy static method or modern instance method
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            return " ".join([item.get("text", "") for item in transcript_data if item.get("text")])
        else:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id)
            return " ".join([snippet.text for snippet in fetched if snippet.text])
    except Exception as e:
        try:
            # Fallback: list transcripts and find any available language
            api = YouTubeTranscriptApi()
            t_list = api.list(video_id) if hasattr(api, "list") else YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = next(iter(t_list))
            data = transcript.fetch()
            snippets = [s.text if hasattr(s, "text") else s.get("text", "") for s in data]
            return " ".join(snippets).strip() or f"[Notice: Transcript was empty for {video_id}]"
        except Exception:
            return f"[Notice: Captions are disabled, private, or unavailable for video {video_id}]"

def research_doc_url(url: str, query: str, top_k: int = 5) -> list[dict]:
    """
    Streams official AWS, GCP, Linux, or DevSecOps documentation into RAM
    and returns top-scoring passages using pure NumPy/SciPy TF-IDF.
    """
    try:
        raw_text = stream_text_from_url(url)
        if not raw_text or raw_text.startswith("[Notice") or raw_text.startswith("[Error"):
            return [{"score": 0.0, "text": f"Documentation could not be retrieved from {url}"}]
        passages = extract_top_passages(raw_text, query, top_k=top_k)
        if not passages:
            # Return first segment of cleaned text if TF-IDF found no direct keyword overlap
            return [{"score": 0.1, "text": raw_text[:800]}]
        return passages
    except Exception as e:
        return [{"score": 0.0, "text": f"Error accessing {url}: {str(e)}"}]

def research_youtube_video(url_or_id: str, query: str, top_k: int = 5) -> list[dict]:
    """
    Fetches YouTube video transcript in RAM and returns the top-scoring passages.
    """
    raw_text = fetch_youtube_transcript(url_or_id)
    if not raw_text or raw_text.startswith("[Notice"):
        return [{"score": 0.0, "text": raw_text}]
    passages = extract_top_passages(raw_text, query, top_k=top_k)
    if not passages:
        return [{"score": 0.1, "text": raw_text[:800]}]
    return passages

def synthesize_with_reasoner(query: str, evidence: list[dict], topic_context: str = "") -> str:
    """
    Synthesizes extracted passages using the Reasoner LLM (OpenRouter free tier or local Qwen-9B).
    """
    client, model_name, options = get_llm_client("reasoner")
    
    context_blocks = "\n\n".join([
        f"[Citation {i+1} | Relevance {e['score']:.2f}]:\n{e['text']}"
        for i, e in enumerate(evidence)
    ])
    
    system_prompt = (
        "You are an Elite Cloud Security & DevSecOps Research Architect. "
        "Analyze the provided citations from documentation or technical transcripts. "
        "Extract actionable security controls, architecture trade-offs, and synthesis. "
        "If citations state that captions or content were unavailable, answer using your core "
        "DevSecOps and AWS/Linux knowledge while clearly stating that live captions were bypassed."
    )
    
    user_prompt = f"Topic/Source: {topic_context}\n\nQuestion: {query}\n\nEvidence Extracted:\n{context_blocks}"
    
    extra = {}
    if options:
        extra["extra_body"] = {"options": options}

    def _call(c, m):
        return c.chat.completions.create(
            model=m,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            **extra
        ).choices[0].message.content

    try:
        return _call(client, model_name)
    except Exception as primary_err:
        # If remote rate-limited (429) or any error, fall back to openrouter/free
        if REASONER_IS_REMOTE:
            try:
                from openai import OpenAI as _OAI
                fb_client = _OAI(
                    base_url=REASONER_BASE_URL,
                    api_key=REASONER_API_KEY,
                    default_headers={"HTTP-Referer": "https://github.com/domain-agent", "X-Title": "DevSecOps-Mentor"},
                )
                print(f"[Reasoner]: Primary model rate-limited, falling back to {REASONER_MODEL_FALLBACK}")
                return _call(fb_client, REASONER_MODEL_FALLBACK)
            except Exception as fb_err:
                return f"[Reasoner Synthesis Notice]: Both primary and fallback failed: {primary_err} | {fb_err}"
        return f"[Reasoner Synthesis Notice]: Query could not be synthesized: {primary_err}"
