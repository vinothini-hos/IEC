"""
Turns a project's spec data into a single normalized text blob — used both
when indexing past projects and when embedding a new incoming project, so
the two are always represented the same way.

Accepts data in the "flat" DATA_EXTRACTION shape used by the historical
project files: {"fields": {field_key: value_or_None}, "key_points": [...]}.
"""


def build_source_text(data_extraction: dict, field_labels: dict) -> str:
    lines = []

    fields = data_extraction.get("fields", {})
    for field_key, value in fields.items():
        if value is None:
            continue
        label = field_labels.get(field_key, field_key)
        lines.append(f"{label}: {value}")

    key_points = data_extraction.get("key_points", [])
    if key_points:
        lines.append("Additional notes: " + "; ".join(key_points))

    return "\n".join(lines) if lines else "(no specification details available)"
