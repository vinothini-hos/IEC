"""
Takes the new incoming project's spec text plus a shortlist of candidate past
projects (already narrowed down by vector similarity search) and asks Claude
to produce a refined 0-100 relevance score and a one-sentence justification
for each — comparing field-by-field rather than relying on embedding
similarity alone.
"""

import sys
import json

SYSTEM_PROMPT = """You are a technical engineering assistant helping an engineer find past project
specifications that are relevant reference points for a new incoming project, for the same type of
equipment. You will be given the NEW project's specification and a list of PAST candidate project
specifications (already pre-filtered as plausibly similar). Your task is to score how relevant each
past project is to the new one, and explain why.

=== SCORING CRITERIA ===
Compare the NEW project against each CANDIDATE project on the specification fields and notes
actually present in both. Relevance should reflect genuine engineering similarity, e.g.:
- Close or matching design capacity / duty
- Similar inlet/outlet pressure and temperature requirements
- Same or compatible heating source / utility availability
- Similar materials of construction or corrosion requirements
- Similar installation context (indoor/outdoor, area classification, skid vs bare equipment)
- Similar scale (number of tonners/cylinders, pipeline length, etc.)

Score 0-100:
- 90-100: Near-identical specification — would serve as a strong direct reference
- 70-89: Very similar — most key parameters match closely
- 40-69: Partially similar — some parameters match, others differ meaningfully
- 10-39: Weakly related — same equipment type but most parameters differ
- 0-9: Not meaningfully relevant despite being the same equipment type

Base every score and justification ONLY on the specification data actually given below — never
invent details about either project that aren't stated.

=== NEW PROJECT SPECIFICATION ===
{new_project_text}

=== CANDIDATE PAST PROJECTS ===
{candidates_text}

=== OUTPUT FORMAT ===
Return ONLY a valid JSON array, no markdown fences, no explanations outside the JSON, in this exact
structure — one entry per candidate given above, in any order:

[
  {{
    "project_id": "",
    "relevance_score": 0,
    "justification": ""
  }}
]

"justification" must be ONE concise sentence naming the specific parameters that matched or
differed (e.g. "Matches on 50 kg/hr capacity and electric heating, but differs on installation —
this candidate is indoor while the new project requires outdoor."). Every candidate given above
must appear exactly once in the output.
"""


def rerank_candidates(new_project_text: str, candidates: list, model: str = "claude-sonnet-4-6") -> list:
    """
    candidates: list of dicts, each with "project_id" and "source_text".
    Returns: list of {"project_id", "relevance_score", "justification"} dicts,
             one per candidate, unsorted (caller sorts/truncates).
    """
    import anthropic

    client = anthropic.Anthropic()

    candidates_text = "\n\n".join(
        f"--- Candidate: {c['project_id']} ---\n{c['source_text']}"
        for c in candidates
    )

    prompt = SYSTEM_PROMPT.format(
        new_project_text=new_project_text,
        candidates_text=candidates_text,
    )

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=prompt,
        messages=[{"role": "user", "content": "Score and justify each candidate as instructed."}],
    )

    raw_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()

    cleaned = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        results = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print("WARNING: Failed to parse reranker output as JSON.", file=sys.stderr)
        print("Raw output was:\n", raw_text, file=sys.stderr)
        raise e

    return results
