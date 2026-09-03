"""
Fills the blank SO2/CL2 query-sheet templates with the extracted spec values,
for attaching to the clarification email. Row layout must stay in sync with
SO2_TEMPLATE_FIELDS / CL2_TEMPLATE_FIELDS in template_consolidation.py — both
templates list the same 18/20 fields in the same order, starting at row 5,
with the value going in column D ("Client Input").
"""

import io
import re

from .config import settings
from .template_consolidation import get_template_fields

TEMPLATE_PATHS = {
    "SO2": lambda: settings.so2_template_path,
    "CL2": lambda: settings.cl2_template_path,
}

FIRST_ROW = 5
VALUE_COLUMN = 4  # column D
CLIENT_NAME_CELL = "B1"


def _client_name(recipient: str) -> str:
    """"N VINOTHINI <nvinothin21@gmail.com>" -> "N VINOTHINI"."""
    if not recipient:
        return ""
    match = re.match(r'^"?([^"<]+)"?\s*<.*>$', recipient.strip())
    return match.group(1).strip() if match else recipient.strip()


def fill_template_workbook(equipment_name: str, type_label: str, fields: dict, recipient: str):
    """Returns (filename, bytes) for the filled workbook, or (None, None) if
    there's no template for this equipment type."""
    import openpyxl

    path_fn = TEMPLATE_PATHS.get(type_label)
    if not path_fn:
        return None, None

    field_defs, _ = get_template_fields(equipment_name)
    if not field_defs:
        return None, None

    wb = openpyxl.load_workbook(path_fn())
    ws = wb.active

    ws[CLIENT_NAME_CELL] = _client_name(recipient)

    for offset, (key, _label) in enumerate(field_defs):
        value = (fields.get(key) or {}).get("value")
        ws.cell(row=FIRST_ROW + offset, column=VALUE_COLUMN, value=value if value else "-")

    buf = io.BytesIO()
    wb.save(buf)

    filename = f"IEC Queries - {type_label} template (filled).xlsx"
    return filename, buf.getvalue()