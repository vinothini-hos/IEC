"""
Thin wrapper around a local Ollama server, used in place of the Claude API
by extraction.py, template_consolidation.py, and rag_reranker.py. Each of
those builds a system prompt + one user message and expects raw text back
(usually JSON, which the caller parses) — this centralizes the actual
call so swapping models/providers only means changing this one file.
"""

import requests

from .config import settings

# Qwen3 reasons before answering. Ollama sometimes returns that reasoning in
# a separate "thinking" field, but on this server it comes back inline in
# "content" — and not always with a matching opening <think> tag (the "think"
# request option is not fully honored by this model/Ollama build). The one
# thing that's consistent: the real answer is whatever comes after the last
# "</think>" marker, if one is present at all.
DEFAULT_MAX_TOKENS = 8000


def call_llm(system_prompt: str, user_message: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """Sends a system + user message to the configured Ollama model and
    returns just the final answer text (reasoning stripped)."""
    response = requests.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "think": False,
            "options": {"num_predict": max_tokens},
        },
        timeout=300,
    )
    response.raise_for_status()
    text = response.json()["message"]["content"]
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    return text.strip()
