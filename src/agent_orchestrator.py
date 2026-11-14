import json
import os
from datetime import datetime
from openai import OpenAI
from config import OLLAMA_BASE_URL, OLLAMA_API_KEY, ROUTER_MODEL, REASONER_MODEL
from retriever import stream_text_from_url, extract_top_passages

client = OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)

def run_domain_agent(query: str, source_url: str, save_training_pair: bool = True):
    print(f"[1/3] Streaming source into RAM from: {source_url}")
    raw_text = stream_text_from_url(source_url)
    
    print("[2/3] Extracting exact passages on CPU...")
    evidence = extract_top_passages(raw_text, query, top_k=4)
    context_block = "\n\n".join([f"[Citation {i+1} | Score {e['score']:.2f}]: {e['text']}" for i, e in enumerate(evidence)])
    
    print(f"[3/3] Reasoning with {REASONER_MODEL}...")
    system_prompt = (
        "You are a strict domain-specific agent. Answer ONLY using the provided citations. "
        "Quote exact phrases and cite [Citation X]. If the answer is not in the citations, say so."
    )
    response = client.chat.completions.create(
        model=REASONER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context_block}\n\nQuestion: {query}"}
        ],
        temperature=0.1
    )
    answer = response.choices[0].message.content
    
    if save_training_pair and evidence:
        os.makedirs("training_logs", exist_ok=True)
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "instruction": query,
            "context": context_block,
            "output": answer
        }
        with open("training_logs/domain_dataset.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
    return answer

if __name__ == "__main__":
    print("Agent pipeline initialized and ready.")
