"""
Explains an ALREADY-RANKED shortlist of past projects — the ranking itself
now comes from the dense+BM25+RRF+field-match pipeline in rag_service.py,
not from this LLM call. This module's only job is to put into words why
each of the final top candidates is a good (or partial) match, referencing
the specific parameters that lined up.

(Formerly rag_reranker.py, which also assigned the 0-100 relevance score
itself — that scoring now happens deterministically upstream.)
"""

import sys
import json

from .llm_client import call_llm

SYSTEM_PROMPT = """You are a technical engineering assistant helping an engineer understand why past
project specifications were surfaced as relevant reference points for a new incoming project, for the
same type of equipment. You will be given the NEW project's specification and a list of PAST candidate
project specifications, already ranked most-to-least relevant by an upstream retrieval pipeline. Your
task is ONLY to explain why each candidate is (or isn't strongly) similar — do not re-score or
re-order them.

=== NEW PROJECT SPECIFICATION ===
{new_project_text}

=== CANDIDATE PAST PROJECTS (already ranked, most relevant first) ===
{candidates_text}

=== OUTPUT FORMAT ===
Return ONLY a valid JSON array, no markdown fences, no explanations outside the JSON, in this exact
structure — one entry per candidate given above, in any order:

[
  {{
    "project_id": "",
    "justification": ""
  }}
]

"justification" must be ONE concise sentence naming the specific parameters that matched or differed
(e.g. "Matches on 50 kg/hr capacity and electric heating, but differs on installation — this candidate
is indoor while the new project requires outdoor."). Base it ONLY on the specification data actually
given below — never invent details about either project that aren't stated. Every candidate given
above must appear exactly once in the output.
"""


def generate_justifications(new_project_text: str, ranked_candidates: list) -> dict:
    """
    ranked_candidates: list of dicts, each with "project_id" and
    "source_text", already in final rank order (best first).
    Returns {project_id: justification_text}.
    """
    candidates_text = "\n\n".join(
        f"--- Candidate {i} (rank {i}): {c['project_id']} ---\n{c['source_text']}"
        for i, c in enumerate(ranked_candidates, start=1)
    )

    prompt = SYSTEM_PROMPT.format(
        new_project_text=new_project_text,
        candidates_text=candidates_text,
    )

    raw_text = call_llm(prompt, "Explain each candidate's relevance as instructed.")
    cleaned = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        results = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print("WARNING: Failed to parse justification output as JSON.", file=sys.stderr)
        print("Raw output was:\n", raw_text, file=sys.stderr)
        raise e

    justifications = {}
    for entry in results:
        if isinstance(entry, dict) and entry.get("project_id"):
            justifications[entry["project_id"]] = entry.get("justification", "")
    return justifications
