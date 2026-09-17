"""
Thin wrapper around a local Ollama server, used in place of the Claude API
by extraction.py, template_consolidation.py, and rag_justification.py. Each of
those builds a system prompt + one user message and expects raw text back
(usually JSON, which the caller parses) — this centralizes the actual
call so swapping models/providers only means changing this one file.
"""

from datetime import datetime
from pathlib import Path

import requests

from .config import settings

# Qwen3 reasons before answering. Ollama sometimes returns that reasoning in
# a separate "thinking" field, but on this server it comes back inline in
# "content" — and not always with a matching opening <think> tag (the "think"
# request option is not fully honored by this model/Ollama build). The one
# thing that's consistent: the real answer is whatever comes after the last
# "</think>" marker, if one is present at all.
DEFAULT_MAX_TOKENS = 16000
# Context window big enough to hold a long email thread + attachments
# (input) plus the full JSON response (output) without either getting
# silently truncated by Ollama.
DEFAULT_NUM_CTX = 32768


def _log_llm_call(
    label, system_prompt: str, user_message: str, response_text: str, user_prompt_parts: dict = None
) -> None:
    """Writes one timestamped folder for a single call — input.txt (system
    prompt), output.txt (final response), and the user prompt under
    llm_calls_storage_dir. The user prompt is written as a single
    user_prompt.txt unless user_prompt_parts is given, in which case each
    {name: text} entry is written as its own <name>.txt instead (e.g.
    email_body.txt + attachments.txt) so the pieces that made up the prompt
    can be inspected separately. Logging failures never break the actual
    LLM call."""
    try:
        prefix = f"{label}-" if label else ""
        out_dir = Path(settings.llm_calls_storage_dir) / f"{prefix}{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "input.txt").write_text(system_prompt, encoding="utf-8")
        if user_prompt_parts:
            for name, text in user_prompt_parts.items():
                (out_dir / f"{name}.txt").write_text(text, encoding="utf-8")
        else:
            (out_dir / "user_prompt.txt").write_text(user_message, encoding="utf-8")
        (out_dir / "output.txt").write_text(response_text, encoding="utf-8")
    except (OSError, UnicodeError):
        pass


def call_llm(
    system_prompt: str,
    user_message: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    log_label: str = None,
    log_user_prompt_parts: dict = None,
) -> str:
    """Sends a system + user message to the configured Ollama model and
    returns just the final answer text (reasoning stripped). Logs the
    prompt and response for every call — see _log_llm_call. log_label is
    just a human-readable tag for the log folder name, e.g. "specification".
    log_user_prompt_parts optionally splits the logged user prompt into
    separate named files (e.g. {"email_body": ..., "attachments": ...})
    instead of one combined user_prompt.txt — the model still receives the
    full user_message as usual; this only affects what gets logged."""
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
            # temperature 0 + a fixed seed make extraction deterministic —
            # without this, the model samples a different (sometimes
            # contradictory) answer to the same factual question on every
            # run, even given identical source text.
            "options": {
                "num_predict": max_tokens,
                "num_ctx": DEFAULT_NUM_CTX,
                "temperature": 0,
                "seed": 42,
            },
        },
        timeout=300,
    )
    response.raise_for_status()
    text = response.json()["message"]["content"]
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    text = text.strip()

    # Logging is opt-in via log_label — only callers that pass one get
    # saved to disk (currently just extraction.py's "specification" call).
    # template_consolidation.py and rag_justification.py don't pass a label,
    # so their calls aren't logged for now.
    if log_label:
        _log_llm_call(log_label, system_prompt, user_message, text, log_user_prompt_parts)

    return text
