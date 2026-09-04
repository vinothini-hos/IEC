"""
Stage 2: template consolidation (Spec Extraction module).

Given the requested_equipments list produced by extraction.py (stage 1), fill
in the predefined SO2/CL2 requirement template fields for each entry — using
only the info already captured in that entry (equipment_definition, count,
mentioned_in) — classify each field's status, and build a ready-to-send
clarification email draft when mandatory info is missing.
"""

import json
import sys
from pathlib import Path

from .config import settings
from .llm_client import call_llm

# ---------------------------------------------------------------------------
# Template field definitions
# ---------------------------------------------------------------------------

SO2_TEMPLATE_FIELDS = [
    ("design_capacity_kg_hr", "Design Capacity - kg/hr"),
    ("system_bolt_down_location", "System bolt down location"),
    ("winter_min_max_temperature", "Minimum and Maximum temperature during winter season"),
    ("source_of_so2", "Source of SO2"),
    ("inlet_liquid_so2_temperature_c", "Inlet Liquid SO2 Temperature - deg C"),
    ("inlet_liquid_so2_pressure_barg", "Inlet Liquid SO2 Pressure - bar (g)"),
    ("so2_pressure_at_vaporizer_outlet_reactor_inlet_barg",
     "SO2 Pressure required @ vaporizer gas outlet / Reactor inlet - bar (g)"),
    ("so2_temperature_at_vaporizer_outlet_reactor_inlet_c",
     "SO2 Temperature required @ vaporizer gas outlet / Reactor inlet - deg C"),
    ("so2_carrier_pipeline_length",
     "Approximate Length of SO2 carrier pipeline from SO2 shed to process"),
    ("vaporizer_heat_source_available", "Vaporizer Heat Source available"),
    ("available_inlet_steam_pressure", "Available inlet Steam pressure"),
    ("no_of_tonners_connected", "No. of tonners connected to the vaporizer system"),
    ("instrument_specification", "Instrument Specification (FLP or Non-FLP)"),
    ("electrical_panel_specification", "Electrical Panel Specification (FLP or Non-FLP)"),
    ("installation_indoor_outdoor", "Installation - Indoor or Outdoor?"),
    ("scope_bare_or_complete_skid",
     "Bare vaporizer / Complete skid system with all instruments & Controls"),
    ("site_layout_provided", "Provide Site layout"),
    ("tentative_finalization_month_year", "Tentative Month / Year of Finalization"),
]

CL2_TEMPLATE_FIELDS = [
    ("design_capacity_kg_hr", "Design Capacity - kg/hr"),
    ("system_bolt_down_location", "System bolt down location"),
    ("winter_min_max_temperature", "Minimum and Maximum temperature during winter season"),
    ("source_of_cl2", "Source of Cl2"),
    ("inlet_liquid_cl2_temperature_c", "Inlet Liquid Cl2 Temperature - deg C"),
    ("inlet_liquid_cl2_pressure_barg", "Inlet Liquid Cl2 Pressure - bar (g)"),
    ("cl2_pressure_at_vaporizer_outlet_reactor_inlet_barg",
     "Cl2 Pressure required @ vaporizer gas outlet / Reactor inlet - bar (g)"),
    ("cl2_temperature_at_vaporizer_outlet_reactor_inlet_c",
     "Cl2 Temperature required @ vaporizer gas outlet / Reactor inlet - deg C"),
    ("cl2_carrier_pipeline_length",
     "Approximate Length of Cl2 carrier pipeline from Cl2 shed to process"),
    ("vaporizer_heat_source_available", "Vaporizer Heat Source available"),
    ("available_inlet_steam_pressure", "Available inlet Steam pressure"),
    ("no_of_tonners_connected", "No. of tonners connected to the vaporizer system"),
    ("instrument_specification", "Instrument Specification (FLP or Non-FLP)"),
    ("electrical_panel_specification", "Electrical Panel Specification (FLP or Non-FLP)"),
    ("installation_indoor_outdoor", "Installation - Indoor or Outdoor?"),
    ("scope_bare_or_complete_skid",
     "Bare vaporizer / Complete skid system with all instruments & Controls"),
    ("site_layout_provided", "Provide Site layout"),
    ("tentative_finalization_month_year", "Tentative Month / Year of Finalization"),
    ("cl2_scrubber_required", "Cl2 Gas Scrubber required (Yes/No)"),
    ("cl2_purity_moisture_spec", "Chlorine purity / moisture content specification"),
]


def get_template_fields(equipment_name: str):
    normalized = (equipment_name or "").lower()

    if "cl2" in normalized or "chlorine" in normalized:
        return CL2_TEMPLATE_FIELDS, "CL2"
    if "so2" in normalized or "sulfur dioxide" in normalized or "sulphur dioxide" in normalized:
        return SO2_TEMPLATE_FIELDS, "SO2"

    return None, None


# ---------------------------------------------------------------------------
# LLM field fill
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """You are a technical data extraction assistant. You are given ONE
requested-equipment entry (already extracted from an enquiry email and its attachments) and a
predefined set of template fields. Your task is to extract a value for each field and classify
its status, using ONLY the information contained in this entry.

=== EQUIPMENT ENTRY ===
Equipment Name: {equipment_name}
Equipment Configuration (specific details captured for this item): {equipment_definition}
Quantity Requested: {count}
Source References: {mentioned_in_text}

=== TEMPLATE FIELDS TO FILL ===
{field_list}

=== RULES ===
1. Extract each field's value ONLY from the "Equipment Configuration" text (and quantity/source
   reference context) above. Do not use outside/general knowledge about SO2 or CL2 vaporizers, and
   do not invent or assume values that are not stated in this entry.
2. Classify each field's "status" as exactly one of:
   - "confirmed": a clear, usable value is stated for this field.
   - "needs_review": a value is stated but it is ambiguous, an unexplained code/abbreviation, or
     otherwise unclear enough that an engineer should double-check it before using it (e.g. a
     cryptic abbreviation instead of a real figure or description).
   - "needs_clarification": the field is critical to sizing/building the equipment (e.g. capacity,
     pressures, temperatures, source gas, tonner count, site/installation conditions) and no usable
     value was given — this should be asked of the customer.
   - "missing": the field was not mentioned and is not the kind of detail that needs to go back to
     the customer (e.g. an internal scope/commercial choice) — leave it for the internal team, don't
     flag it for customer clarification.
3. "value": the extracted text for "confirmed"/"needs_review" fields, or the literal stated
   (but unclear) text for "needs_review". For "needs_clarification"/"missing", set value to JSON
   null unless the source literally contains an unclear stand-in value (e.g. an abbreviation like
   "VTS" that doesn't answer the question) — in that case keep that text as the value AND mark the
   status "needs_clarification", since the customer needs to clarify what it means.
4. "source": a short label for where this came from (e.g. "specification.xlsx", "Email Body"), or
   null if the field has no value.
5. Match field intent even if the entry's wording differs from the field label (e.g. "Design
   Capacity - kg/hr" may appear in the entry as "50 kg/hr capacity" or similar phrasing).
6. Keep each value concise — a short phrase, figure with units, or Yes/No — unless the field
   inherently requires short descriptive text (e.g. "Source of SO2").
7. Return ONLY a valid JSON object, no markdown fences, no explanations, in this exact structure:

   {{
     "fields": {{
       "<field_key>": {{"value": "<text>" | null, "status": "<status>", "source": "<text>" | null}},
       ...
     }}
   }}

   Every field key listed above must be present under "fields".
"""


def fill_template_fields(equipment: dict, field_defs: list) -> dict:
    field_list_str = "\n".join(f"- {key}: {label}" for key, label in field_defs)

    mentioned_in = equipment.get("mentioned_in", [])
    mentioned_in_text = "; ".join(
        f"{m.get('document_name', '')} ({m.get('document_location', '')})" for m in mentioned_in
    ) or "(none provided)"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        equipment_name=equipment.get("equipment_name", ""),
        equipment_definition=equipment.get("equipment_definition", ""),
        count=equipment.get("count", ""),
        mentioned_in_text=mentioned_in_text,
        field_list=field_list_str,
    )

    raw_text = call_llm(system_prompt, "Extract the field values and statuses as instructed.")
    cleaned = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print("WARNING: Failed to parse template-fill output as JSON.", file=sys.stderr)
        print("Raw output was:\n", raw_text, file=sys.stderr)
        raise e

    field_values = result.get("fields", {})
    for key, _ in field_defs:
        field_values.setdefault(key, {"value": None, "status": "missing", "source": None})

    return field_values


# ---------------------------------------------------------------------------
# Clarification email draft (deterministic — no extra LLM call)
# ---------------------------------------------------------------------------


def _get_reply_recipient(thread) -> str:
    """Same "reply to the other party" logic as ThreadView.jsx's getReplyRecipient."""
    emails_sorted = sorted(thread.emails, key=lambda e: e.sent_at)
    for email in reversed(emails_sorted):
        direction = getattr(email.direction, "value", email.direction)
        if direction == "incoming":
            return email.sender
    last = emails_sorted[-1] if emails_sorted else None
    if not last:
        return ""
    return last.recipient or last.sender or ""


def _build_clarification_draft(thread, equipment_name: str, needs_clarification_labels: list) -> dict:
    if not needs_clarification_labels:
        return None

    recipient = _get_reply_recipient(thread)
    subject = f"Clarification needed: {equipment_name} enquiry"

    count = len(needs_clarification_labels)
    intro = "one clarification" if count == 1 else f"{count} clarifications"
    bullet_list = "\n".join(f"- {label}" for label in needs_clarification_labels)

    body = (
        f"Dear Customer,\n\n"
        f"Thanks for your enquiry for the {equipment_name}.\n\n"
        f"We have reviewed the specification and require {intro}:\n\n"
        f"{bullet_list}\n\n"
        f"Please confirm the required configuration.\n\n"
        f"Regards,\n{settings.email_signature_name}"
    )

    return {"recipient": recipient, "subject": subject, "body": body}


# ---------------------------------------------------------------------------
# Output shaping + disk write
# ---------------------------------------------------------------------------


def _safe_filename(text: str, max_len: int = 60) -> str:
    keep = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in text)
    keep = "_".join(keep.split())
    return keep[:max_len] or "equipment"


def _classification_label(equipment_name: str, fields: dict) -> str:
    parts = [equipment_name]
    heat = fields.get("vaporizer_heat_source_available", {}).get("value")
    if heat:
        # Field values are often a full sentence with parenthetical detail
        # (e.g. "Steam (existing header available near...)") — only use it
        # for the short classification tag if it reduces to a short phrase.
        heat_str = heat.split("(")[0].split(",")[0].split(";")[0].strip()
        if heat_str and len(heat_str) <= 25:
            if "heat" not in heat_str.lower():
                heat_str = f"{heat_str}-heated"
            parts.append(heat_str)
    return " · ".join(parts)


def run_data_extraction_for_thread(thread, requested_equipments: list) -> list:
    """For each requested_equipment entry, fill its template, classify field
    statuses, build a clarification draft if needed, and write it to
    storage/data_extraction/{thread_id}/<idx>_<type>_<desc>.json.

    Returns the "equipment_items" list stored on Thread.extraction_result.
    """
    out_dir = Path(settings.data_extraction_storage_dir) / str(thread.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    equipment_items = []
    for idx, equipment in enumerate(requested_equipments, start=1):
        equipment_name = equipment.get("equipment_name", "Unknown Equipment")
        field_defs, type_label = get_template_fields(equipment_name)
        if field_defs is None:
            continue

        field_values = fill_template_fields(equipment, field_defs)

        fields = {}
        filled = 0
        needs_clarification_labels = []
        for key, label in field_defs:
            entry = field_values.get(key) or {"value": None, "status": "missing", "source": None}
            status = entry.get("status", "missing")
            fields[key] = {
                "label": label,
                "value": entry.get("value"),
                "status": status,
                "source": entry.get("source"),
            }
            if status == "confirmed":
                filled += 1
            if status == "needs_clarification":
                needs_clarification_labels.append(label)

        total = len(field_defs)
        item = {
            "equipment_name": equipment_name,
            "type_label": type_label,
            "classification_label": _classification_label(equipment_name, fields),
            "count": equipment.get("count", 1),
            "fields": fields,
            "completion": {
                "filled": filled,
                "total": total,
                "percent": round(filled / total * 100) if total else 0,
            },
            "clarification_draft": _build_clarification_draft(
                thread, equipment_name, needs_clarification_labels
            ),
        }
        equipment_items.append(item)

        filename = (
            f"{idx:02d}_{type_label}_"
            f"{_safe_filename(equipment.get('equipment_definition', equipment_name))}.json"
        )
        (out_dir / filename).write_text(json.dumps(item, indent=2))

    return equipment_items
