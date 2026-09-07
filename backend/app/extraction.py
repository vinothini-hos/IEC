"""
Equipment specification extraction.

Ports the standalone equipment_extractor.py / llm_extractor.py scripts into the
mailbox backend: given a thread already synced from Gmail (body_text on each
Email row, downloaded attachments on disk via Attachment.local_path), extract
the SO2/CL2 equipment requests mentioned across the whole conversation via a
local Ollama model (see llm_client.py).
"""

import json
import sys
from pathlib import Path

from .config import settings
from .llm_client import call_llm

# ---------------------------------------------------------------------------
# Attachment text extraction (PDF / DOCX / XLSX / CSV)
# ---------------------------------------------------------------------------


def extract_text_from_pdf(path: str) -> str:
    import pdfplumber

    text_chunks = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            text_chunks.append(f"--- Page {i} ---\n{page_text}")

            tables = page.extract_tables()
            for t_idx, table in enumerate(tables, start=1):
                table_str = "\n".join(
                    " | ".join(str(cell) if cell is not None else "" for cell in row)
                    for row in table
                )
                text_chunks.append(f"--- Page {i} Table {t_idx} ---\n{table_str}")
    return "\n\n".join(text_chunks)


def extract_text_from_docx(path: str) -> str:
    import docx

    doc = docx.Document(path)
    chunks = []

    for i, para in enumerate(doc.paragraphs, start=1):
        if para.text.strip():
            chunks.append(f"[Paragraph {i}] {para.text}")

    for t_idx, table in enumerate(doc.tables, start=1):
        rows = [" | ".join(cell.text for cell in row.cells) for row in table.rows]
        chunks.append(f"--- Table {t_idx} ---\n" + "\n".join(rows))

    return "\n".join(chunks)


def extract_text_from_excel(path: str) -> str:
    import pandas as pd

    chunks = []
    ext = Path(path).suffix.lower()

    if ext == ".csv":
        df = pd.read_csv(path)
        chunks.append(f"--- Sheet: CSV ---\n{df.to_string(index=True)}")
    else:
        xls = pd.ExcelFile(path)
        for sheet_name in xls.sheet_names:
            df = xls.parse(sheet_name)
            chunks.append(f"--- Sheet: {sheet_name} ---\n{df.to_string(index=True)}")

    return "\n\n".join(chunks)


def extract_text_from_attachment(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    elif ext == ".docx":
        return extract_text_from_docx(path)
    elif ext in (".xlsx", ".xlsm", ".xls", ".csv"):
        return extract_text_from_excel(path)
    elif ext == ".txt":
        return Path(path).read_text(errors="ignore")
    else:
        raise ValueError(f"Unsupported attachment type: {ext} ({path})")


# ---------------------------------------------------------------------------
# Equipment knowledge base + prompts
# ---------------------------------------------------------------------------

EQUIPMENT_KNOWLEDGE_BASE = """
Equipment Name: SO2
Equipment Definition:
An SO2 vaporizer is a heat-exchange device that converts liquid Sulfur Dioxide into gaseous SO2 for
controlled downstream use.
- It typically operates using a water bath or electric heating jacket to supply latent heat of
  vaporization to liquid SO2.
- SO2 vaporizers are commonly installed in pulp and paper mills, sugar refineries, and dechlorination
  stations at water treatment plants.
- The vaporizer receives liquid SO2 from ton containers or cylinders and discharges vapor-phase SO2
  to a feed/dosing system.
- Temperature control is critical, usually maintained between 60-85°C, to ensure stable vaporization
  without decomposition or pressure spikes.
- SO2 vaporizers include pressure relief valves, low-liquid-level cutoffs, and vacuum-operated
  regulators for safe operation.
- Materials of construction often include steel or corrosion-resistant alloys due to SO2's reaction
  with moisture to form sulfurous acid.
- These vaporizers are frequently paired with sulfonation, bleaching, or antimicrobial dosing systems
  in food and beverage processing.
- Instrumentation on SO2 vaporizers includes pressure gauges, thermometers, and interlocks tied to
  SO2-specific gas detection systems.
- Any reference to "sulfonator feed," "SO2 gas generator," "dechlorination vaporizer," or "sulfite
  vaporization" indicates this is an SO2 vaporizer.

Equipment Name: CL2
Equipment Definition:
A CL2 vaporizer is a heat-exchange device that converts liquid Chlorine into gaseous chlorine for
controlled downstream feeding.
- It typically uses a hot water bath, steam jacket, or electric heater to vaporize liquid chlorine
  drawn from containers.
- CL2 vaporizers are commonly installed in municipal water treatment plants, wastewater facilities,
  and large-scale chlorination systems.
- The vaporizer receives liquid chlorine from ton containers or tank cars and supplies gas-phase
  chlorine to chlorinators.
- Temperature control is critical, usually maintained around 70-90°C, to prevent liquid chlorine
  carryover into the gas feed lines.
- CL2 vaporizers include safety features like high-temperature cutoffs, low-liquid-level alarms, and
  pressure relief devices for chlorine service.
- Materials of construction are chlorine-compatible, often Monel, Hastelloy, or specially lined
  steel, resistant to hydrochloric/hypochlorous acid formation.
- These vaporizers are essential for high-capacity chlorination systems where gas cylinders alone
  cannot meet dosing demand.
- Instrumentation on CL2 vaporizers includes pressure transmitters, temperature sensors, and
  interlocks linked to chlorine leak detection systems.
- Any reference to "chlorine gas evaporator," "ton container vaporizer," "chlorinator feed system,"
  or "liquid chlorine converter" indicates this is a CL2 vaporizer.
"""

SYSTEM_PROMPT = """You are an equipment request extraction system. You will be given the content of
an email thread (body text of every message in the thread) and its attachments (PDF, DOCX, Excel —
already converted to text/table form). Your task is to identify all EQUIPMENT REQUESTS mentioned
across the thread and attachments, using the equipment knowledge base below to correctly classify
and understand what is being requested.

=== EQUIPMENT KNOWLEDGE BASE ===
{knowledge_base}

=== EXTRACTION RULES ===

1. Scan the thread body AND all attachment content (PDF/DOCX/Excel text) for mentions of equipment
   matching the knowledge base definitions above — including indirect/synonym references (e.g.
   "sulfonator feed unit" maps to SO2, "chlorinator feed system" maps to CL2).

2. TREAT AS THE SAME requested_equipment ONLY IF:
   - The equipment name/type matches, AND
   - No distinguishing configuration/spec is mentioned (e.g. capacity, temperature range,
     material of construction, mounting type, feed rate, model number).

3. TREAT AS A SEPARATE requested_equipment IF:
   - A different configuration, capacity, spec, or model is mentioned for the same equipment type.
   - Example: "SO2 vaporizer - 500 kg/hr" and "SO2 vaporizer - 1000 kg/hr" are two DIFFERENT
     requested_equipments, even though both are SO2 vaporizers.

4. COUNT = number of units requested for that exact equipment + configuration combination
   (sum across all mentions of the same configuration, whether in body or attachments — but do not
   double count the same single line item referenced twice).

5. TRACK every location where each equipment (with that configuration) is mentioned — each email in
   the thread counts as a "document" (use document_name like "Email: <subject/sender/date>").

6. If quantity is not explicitly stated, default count to 1 per distinct mention.

7. Do not infer or hallucinate equipment that is not explicitly supported by text evidence matching
   the knowledge base definitions.

8. RECENCY WHEN VALUES CONFLICT: attachments and email bodies are labeled with their send date/time,
   ordered oldest to newest, and the single most recent attachment (if any) is explicitly marked
   "MOST RECENT ATTACHMENT". A thread often starts with a rough enquiry, gets a clarification request,
   and ends with the customer's revised/filled-in spec sheet — later documents supersede earlier ones.
   If two documents state DIFFERENT values for the same parameter of the same equipment item, use the
   value from the more recent document (by send date/time) and ignore the older, now-outdated value.
   Only fall back to an older document's value for a parameter if no later document mentions that
   parameter at all.

=== OUTPUT FORMAT ===

Return ONLY a valid JSON array, no explanations, no markdown fences, in this exact structure. Write
the fields in this exact order for each item — "equipment_definition" is the longest field, so write
it LAST, after "count" and "mentioned_in" are already filled in, so those are never left out:

[
  {{
    "equipment_name": "",
    "count": 0,
    "mentioned_in": [
      {{"document_name": "", "document_location": ""}}
    ],
    "equipment_definition": ""
  }}
]

FIELD DEFINITIONS:
- "equipment_name": the canonical equipment type from the knowledge base (e.g. "SO2 Vaporizer",
  "CL2 Vaporizer").
- "equipment_definition": an EXHAUSTIVE paragraph covering EVERY piece of technical detail stated
  in the source document(s) for THIS particular requested item — not a summary, not just the
  "distinguishing" details. This is NOT the generic knowledge-base description — do not copy the
  knowledge base text here.
  COMPLETENESS REQUIREMENT: if the source is a specification/datasheet with a parameter table (e.g.
  "Service", "Medium", "Vaporization Capacity", "Heating Method", "Inlet Pressure", "Inlet
  Temperature", "Outlet Pressure", "Outlet Temperature", "Material of Construction",
  "Instrumentation", "Safety Provisions", "Process Connections", "Applicable Standards", vendor
  information requested, notes, etc.), EVERY ROW that actually APPEARS in that table must be
  represented somewhere in this paragraph — including rows whose value is a placeholder like "To be
  confirmed", "Vendor to recommend", or "Vendor to specify". Do not silently drop a parameter just
  because its value is non-specific — state that it was left open/to-be-confirmed/vendor-to-decide,
  since that is itself a fact about the requirement. Treat this field as a lossless prose
  transcription of the source spec, not a highlights reel: after writing it, mentally check every
  row/field/label in the source attachment for this item and confirm each one appears in the
  paragraph in some form.
  DO NOT DO THIS FOR PARAMETERS THAT NEVER APPEAR IN THE SOURCE AT ALL: the completeness requirement
  above applies only to rows/fields that are actually present in the source (even if their value is
  blank or "TBC"). If a parameter is not mentioned anywhere in the email or attachments — no row, no
  label, no reference to it at all — do not invent a status for it (e.g. do not write "no scrubber
  is required" or "purity spec to be confirmed by vendor" when the source never brings up a scrubber
  or purity at all). Simply omit any parameter that has zero textual evidence in the source; do not
  fill silence with an assumed "not required" or "to be confirmed".
  FORMAT: always write this as flowing prose in plain sentences — even if the source data appears
  as a table, spec sheet, or row/column layout in the attachment. Convert tabular fields into
  natural sentences (e.g. a table row like "Capacity: 1000 kg/hr | MOC: Monel | Type: Water bath"
  becomes "This unit has a capacity of 1000 kg/hr, is constructed of Monel, and uses a water bath
  heating type."). Never output raw key-value pairs, bullet points, or pipe/table-style formatting
  in this field. It is fine (expected, for a detailed spec sheet) for this paragraph to run several
  sentences long in order to cover every parameter.
  If no configuration detail is mentioned at all, write a short sentence such as "No specific
  configuration was mentioned for this item." rather than leaving it blank or inserting the
  generic definition.
"""

USER_PROMPT_TEMPLATE = """=== EMAIL THREAD ===
{email_body}

=== ATTACHMENTS ===
{attachments_text}
"""


def call_claude_for_extraction(email_body: str, attachments: list) -> list:
    blocks = []
    for i, att in enumerate(attachments):
        is_most_recent = i == len(attachments) - 1
        tag = " — MOST RECENT ATTACHMENT" if is_most_recent else ""
        blocks.append(
            f"### Attachment: {att['filename']} (sent {att['sent_at']}{tag}) ###\n{att['text']}"
        )
    attachments_text = "\n\n".join(blocks) or "(no attachments)"

    user_prompt = USER_PROMPT_TEMPLATE.format(
        email_body=email_body or "(empty)",
        attachments_text=attachments_text,
    )
    system_prompt = SYSTEM_PROMPT.format(knowledge_base=EQUIPMENT_KNOWLEDGE_BASE)

    raw_text = call_llm(system_prompt, user_prompt)
    cleaned = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print("WARNING: Failed to parse model output as JSON.", file=sys.stderr)
        print("Raw output was:\n", raw_text, file=sys.stderr)
        raise e

    for item in parsed:
        item.setdefault("count", 1)
        item.setdefault("mentioned_in", [])
        item.setdefault("equipment_definition", "")

    # The model's array order isn't guaranteed to be stable across runs —
    # sort deterministically so re-extracting the same thread doesn't
    # reshuffle the equipment list/fields order shown in the UI.
    parsed.sort(key=lambda item: item.get("equipment_name", ""))
    return parsed


# ---------------------------------------------------------------------------
# Thread-level entry point
# ---------------------------------------------------------------------------


def _format_email_for_prompt(email) -> str:
    return (
        f"--- {email.direction.value.upper()} | {email.sent_at} ---\n"
        f"From: {email.sender}\nTo: {email.recipient}\nSubject: {email.subject}\n\n"
        f"{email.body_text or ''}"
    )


def extract_specification_for_thread(thread) -> list:
    """Given a Thread ORM object (with .emails and .emails[*].attachments loaded),
    concatenate every message + downloaded attachment and run the Claude extraction."""
    emails_sorted = sorted(thread.emails, key=lambda e: e.sent_at)
    email_body = "\n\n".join(_format_email_for_prompt(e) for e in emails_sorted)

    attachments = []
    for email in emails_sorted:
        for attachment in email.attachments:
            if not attachment.local_path:
                continue
            try:
                text = extract_text_from_attachment(attachment.local_path)
            except Exception as e:
                text = f"[ERROR extracting content: {e}]"
            attachments.append({
                "filename": attachment.filename,
                "sent_at": email.sent_at,
                "text": text,
            })

    return call_claude_for_extraction(email_body, attachments)


def save_specification_result(thread_id, result: list) -> str:
    out_dir = Path(settings.specification_storage_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{thread_id}.json"
    out_path.write_text(json.dumps(result, indent=2))
    return str(out_path)
