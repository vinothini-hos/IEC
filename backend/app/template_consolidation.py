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
    ("description", "Description"),
    ("qty", "Qty - No's"),
    ("location_installation", "Location (Installation)"),
    ("system_bolt_down_location", "System bolt down location - Site Location"),
    ("winter_min_max_temperature", "Minimum and Maximum temperature during winter season? - deg C"),
    ("application", "Application"),
    ("orientation", "Orientation"),
    ("design_capacity_kg_hr", "Design Capacity - kg/hr"),
    ("source_of_so2", "Source of SO2"),
    ("inlet_liquid_so2_temperature_c", "Inlet Liquid SO2 Temperature - deg C"),
    ("inlet_liquid_so2_pressure_barg", "Inlet Liquid SO2 Pressure - bar (g)"),
    ("so2_pressure_at_vaporizer_outlet_barg",
     "SO2 Pressure required @ vaporizer gas outlet - bar (g)"),
    ("so2_temperature_at_vaporizer_outlet_c",
     "SO2 Temperature required @ vaporizer gas outlet - deg C"),
    ("heating_media", "Heating media"),
    ("heating_fluid", "Heating Fluid"),
    ("no_of_tonners_connected", "No. of tonners connected to the vaporizer system"),
    ("tonner_manifold_arrangement_required", "Tonner Manifold arrangement required / Not required"),
    ("tonner_manifold_working_standby_count",
     "If required provide No. of tonners working & standby"),
    ("instrument_specification", "Instrument Specification (FLP or Non-FLP)"),
    ("electrical_panel_specification", "Electrical Panel Specification (FLP or Non-FLP)"),
    ("area_classification", "Area classification - Hazardous or Non-Hazardous?"),
    ("scope_bare_or_complete_skid",
     "Bare vaporizer / Complete skid system with all instruments & Controls"),
    ("site_layout_provided", "Provide site layout / Flow Scheme"),
    ("tentative_finalization_month_year", "Tentative Month / Year of Finalization"),
]

CL2_TEMPLATE_FIELDS = [
    ("description", "Description"),
    ("qty", "Qty - No's"),
    ("location_installation", "Location (Installation)"),
    ("system_bolt_down_location", "System bolt down location - Site Location"),
    ("winter_min_max_temperature", "Minimum and Maximum temperature during winter season? - deg C"),
    ("application", "Application"),
    ("orientation", "Orientation"),
    ("design_capacity_kg_hr", "Design Capacity - kg/hr"),
    ("source_of_cl2", "Source of Chlorine"),
    ("inlet_liquid_cl2_temperature_c", "Inlet Liquid Chlorine Temperature - deg C"),
    ("inlet_liquid_cl2_pressure_barg", "Inlet Liquid Chlorine Pressure - bar (g)"),
    ("cl2_pressure_at_vaporizer_outlet_barg",
     "Chlorine Pressure required @ vaporizer gas outlet - bar (g)"),
    ("cl2_temperature_at_vaporizer_outlet_c",
     "Chlorine Temperature required @ vaporizer gas outlet - deg C"),
    ("heating_media", "Heating media"),
    ("heating_fluid", "Heating Fluid"),
    ("no_of_tonners_connected", "No. of tonners connected to the vaporizer system"),
    ("tonner_manifold_arrangement_required", "Tonner Manifold arrangement required / Not required"),
    ("tonner_manifold_working_standby_count",
     "If required provide No. of tonners working & standby"),
    ("instrument_specification", "Instrument Specification (FLP or Non-FLP)"),
    ("electrical_panel_specification", "Electrical Panel Specification (FLP or Non-FLP)"),
    ("area_classification", "Area classification - Hazardous or Non-Hazardous?"),
    ("scope_bare_or_complete_skid",
     "Bare vaporizer / Complete skid system with all instruments & Controls"),
    ("site_layout_provided", "Provide site layout / Flow Scheme"),
    ("tentative_finalization_month_year", "Tentative Month / Year of Finalization"),
]


# Per-field guidance for the LLM extraction prompt only — not shown to users
# and not used by spec_template.py's row-fill (which relies on field order,
# not this text). Clarifies what counts as an answer for fields whose label
# alone is ambiguous, to cut down on the local model skipping or
# misinterpreting them.
FIELD_HINTS = {
    # "description" is deliberately absent — it's set directly from
    # equipment_name in fill_template_fields(), never sent to the LLM.
    "qty": "How many units of this equipment are needed.",
    "location_installation": "Whether the equipment will be installed indoor or outdoor.",
    "system_bolt_down_location": "The site/area name where the equipment will be bolted down.",
    "winter_min_max_temperature": "The minimum and maximum ambient temperature expected during the winter season.",
    "application": "The name of the chemical/process this vaporizer is used for.",
    "orientation": "The equipment's orientation, e.g. bayonet (vertical) or horizontal.",
    "design_capacity_kg_hr": "The equipment's rated design capacity.",
    "source_of_so2": "Where the SO2 comes from — tonner or cylinder.",
    "source_of_cl2": "Where the chlorine comes from — tonner or cylinder.",
    "inlet_liquid_so2_temperature_c": "The inlet liquid SO2 temperature — may be stated as ambient / "
        "room temperature / normal, or as an explicit figure in the attachment or email body.",
    "inlet_liquid_cl2_temperature_c": "The inlet liquid chlorine temperature — may be stated as ambient / "
        "room temperature / normal, or as an explicit figure in the attachment or email body.",
    "inlet_liquid_so2_pressure_barg": "The inlet liquid SO2 pressure — based on the source pressure or a "
        "controlled/regulated pressure.",
    "inlet_liquid_cl2_pressure_barg": "The inlet liquid chlorine pressure — based on the source pressure or a "
        "controlled/regulated pressure.",
    "so2_pressure_at_vaporizer_outlet_barg": "The output gas pressure required from the vaporizer.",
    "cl2_pressure_at_vaporizer_outlet_barg": "The output gas pressure required from the vaporizer.",
    "so2_temperature_at_vaporizer_outlet_c": "The output gas temperature required from the vaporizer.",
    "cl2_temperature_at_vaporizer_outlet_c": "The output gas temperature required from the vaporizer.",
    "heating_media": "The vaporizer's heat source method, e.g. steam or electric heater.",
    "heating_fluid": "The heating fluid used, e.g. steam, water, or oil.",
    "no_of_tonners_connected": "The number of tonners connected to the vaporizer system.",
    "tonner_manifold_arrangement_required": "Whether a tonner manifold arrangement is required or not.",
    "tonner_manifold_working_standby_count": "If a manifold arrangement is required, the number of tonners "
        "working vs. on standby.",
    "instrument_specification": "Whether instruments must be FLP (flame-proof) or Non-FLP.",
    "electrical_panel_specification": "Whether the electrical panel must be FLP (flame-proof) or Non-FLP.",
    "area_classification": "Whether the installation area is Hazardous or Non-Hazardous.",
    "scope_bare_or_complete_skid": "Whether the scope is a bare vaporizer, or a complete skid system with all "
        "instruments & controls.",
    "site_layout_provided": "Whether a site layout / flow scheme has been provided (Yes/No).",
    "tentative_finalization_month_year": "The tentative month/year by which the order is expected to be "
        "finalized.",
}


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
   - "confirmed": a clear, usable value is stated for this field. A DEFINITE NEGATIVE ANSWER COUNTS
     AS CONFIRMED, not missing — e.g. "site layout is not provided", "no scrubber required", "zero
     tonners connected" are all real, usable answers (value = the stated negative, e.g. "Not
     provided" / "No" / "0"). Only use "missing" when the topic is never addressed at all — never
     for a topic the source explicitly answers with "no"/"not provided"/"none".
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
7. WATCH FOR TWIN-VALUE SENTENCES: a single sentence often states two related but DIFFERENT values
   for two DIFFERENT fields, e.g. "the inlet pressure is 56 bar(g) and the outlet pressure is 67
   bar(g)" answers TWO separate fields (inlet AND outlet), each with its own number. Do not assign
   only the second number and leave the first field blank — read the full sentence and match each
   clause to its own field.
8. COMPLETENESS CHECK (do this before writing your final answer): the "Equipment Configuration"
   text is a long paragraph that states a fact for almost every template field, including facts
   near the middle/end of the paragraph — do not stop reading partway through. Go through the
   paragraph sentence by sentence and match each sentence to the template field(s) it answers. A
   field must only be marked "needs_clarification" or "missing" if, after this full read-through,
   you confirm the paragraph truly never states a value for it — not because the fact appeared
   later in a long paragraph and was skipped.
9. Return ONLY a valid JSON object, no markdown fences, no explanations, in this exact structure:

   {{
     "fields": {{
       "<field_key>": {{"value": "<text>" | null, "status": "<status>", "source": "<text>" | null}},
       ...
     }}
   }}

   Every field key listed above must be present under "fields".
"""


# Fields per LLM call — a smaller batch means the model has fewer fields to
# track at once against the (still-full) equipment_definition text, which
# cuts down on fields getting skipped near the end of a long paragraph.
FIELD_BATCH_SIZE = 6


def _fill_template_fields_batch(equipment: dict, field_defs_batch: list) -> dict:
    field_list_str = "\n".join(
        f"- {key}: {label}" + (f" ({FIELD_HINTS[key]})" if key in FIELD_HINTS else "")
        for key, label in field_defs_batch
    )

    # The local Qwen3/Ollama extraction model doesn't always follow the
    # nested {"document_name", "document_location"} schema as reliably as
    # Claude did — sometimes returning a plain string per entry instead.
    # Handle both shapes rather than assuming dicts.
    mentioned_in = equipment.get("mentioned_in", [])
    mentioned_in_parts = []
    for m in mentioned_in:
        if isinstance(m, dict):
            mentioned_in_parts.append(f"{m.get('document_name', '')} ({m.get('document_location', '')})")
        else:
            mentioned_in_parts.append(str(m))
    mentioned_in_text = "; ".join(mentioned_in_parts) or "(none provided)"

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

    # The local Qwen3/Ollama model sometimes shortcuts the requested
    # {"value", "status", "source"} object and returns a bare string/number
    # for a field instead — normalize so every entry is the expected shape
    # before it reaches _has_real_value() and friends.
    raw_field_values = result.get("fields", {})
    field_values = {}
    for key, _ in field_defs_batch:
        entry = raw_field_values.get(key)
        if isinstance(entry, dict):
            field_values[key] = entry
        elif entry not in (None, ""):
            field_values[key] = {"value": str(entry), "status": "confirmed", "source": None}
        else:
            field_values[key] = {"value": None, "status": "missing", "source": None}

    return field_values


def fill_template_fields(equipment: dict, field_defs: list) -> dict:
    field_values = {}

    # "description" always means the equipment's name, which is already
    # known directly from stage-1 extraction — set it deterministically
    # instead of asking the LLM, which tended to copy the whole
    # equipment_definition paragraph in instead of just the name.
    llm_field_defs = []
    for key, label in field_defs:
        if key == "description":
            equipment_name = equipment.get("equipment_name") or None
            field_values["description"] = {
                "value": equipment_name,
                "status": "confirmed" if equipment_name else "missing",
                "source": None,
            }
        else:
            llm_field_defs.append((key, label))

    for i in range(0, len(llm_field_defs), FIELD_BATCH_SIZE):
        batch = llm_field_defs[i : i + FIELD_BATCH_SIZE]
        field_values.update(_fill_template_fields_batch(equipment, batch))
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
    heat = fields.get("heating_media", {}).get("value")
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


def _has_real_value(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    return entry.get("status") in ("confirmed", "needs_review") and entry.get("value") not in (
        None,
        "",
    )


def run_data_extraction_for_thread(thread, requested_equipments: list) -> list:
    """For each requested_equipment entry, fill its template, classify field
    statuses, build a clarification draft if needed, and write it to
    storage/data_extraction/{thread_id}/<idx>_<type>_<name>.json — one
    stable file per equipment item, updated in place on every re-extraction
    rather than replaced wholesale: a field only overwrites its previous
    value when this run actually found one, so a run where the model
    temporarily misses a field doesn't erase a previously confirmed value.

    Returns the "equipment_items" list stored on Thread.extraction_result.
    """
    out_dir = Path(settings.data_extraction_storage_dir) / str(thread.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    equipment_items = []
    written_filenames = set()
    for idx, equipment in enumerate(requested_equipments, start=1):
        equipment_name = equipment.get("equipment_name", "Unknown Equipment")
        field_defs, type_label = get_template_fields(equipment_name)
        if field_defs is None:
            continue

        field_values = fill_template_fields(equipment, field_defs)

        filename = f"{idx:02d}_{type_label}_{_safe_filename(equipment_name)}.json"
        out_path = out_dir / filename
        previous_fields = {}
        if out_path.exists():
            try:
                previous_fields = json.loads(out_path.read_text()).get("fields", {})
            except (json.JSONDecodeError, OSError):
                previous_fields = {}

        fields = {}
        filled = 0
        needs_clarification_labels = []
        for key, label in field_defs:
            entry = field_values.get(key) or {"value": None, "status": "missing", "source": None}
            if not _has_real_value(entry) and _has_real_value(previous_fields.get(key)):
                entry = previous_fields[key]
            status = entry.get("status", "missing")
            fields[key] = {
                "label": label,
                "value": entry.get("value"),
                "status": status,
                "source": entry.get("source"),
            }
            if status == "confirmed":
                filled += 1
            if status in ("needs_clarification", "missing"):
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
        out_path.write_text(json.dumps(item, indent=2))
        written_filenames.add(filename)

    # Remove files for equipment that no longer appears in this run's
    # extraction (genuinely dropped, not just temporarily missed).
    for old_file in out_dir.glob("*.json"):
        if old_file.name not in written_filenames:
            old_file.unlink()

    return equipment_items
