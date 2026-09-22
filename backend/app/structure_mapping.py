"""
Deterministic Excel cell-structure mapping.

Two-stage, LLM-free pipeline that turns one sheet's RAW_DATA (as written by
sheet_consolidation.py: a flat list of non-empty cells with coordinate,
row/col, cached value, formula, and merge_range) into a human-readable
STRUCTURED JSON:

    RAW_DATA -> CELL_STRUCTURE -> STRUCTURED JSON

Stage 1 (build_cell_structure) discovers row labels, column/row group
headers, subheader tiers, and sections purely from row/col/merge_range
facts, and expresses the relationships between them as cell references
only (never values) — ported from deterministic_structure_builder.py.

Stage 2 (resolve_cell_structure) mechanically resolves every cell
reference in CELL_STRUCTURE to its cached value from RAW_DATA — a plain
dict-walk with no judgement calls, so it needs no LLM either. It
implements the four value forms described in structure_relationship_prompt.txt:
plain cell ref, "<context>:<value>" colon path, an array of either, and
nested objects at any depth.
"""

import re
from collections import defaultdict


def col_letters_to_num(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def parse_ref(ref: str):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    col = col_letters_to_num(m.group(1))
    row = int(m.group(2))
    return row, col


def parse_merge_range(merge_range: str):
    start, end = merge_range.split(":")
    r1, c1 = parse_ref(start)
    r2, c2 = parse_ref(end)
    return min(r1, r2), max(r1, r2), min(c1, c2), max(c1, c2)


# ---------------------------------------------------------------------------
# Stage 1: RAW_DATA -> CELL_STRUCTURE (cell references only, no values)
# ---------------------------------------------------------------------------


def build_cell_structure(raw_data: dict):
    """Returns (cell_structure_dict, diagnostics_dict)."""
    cells = raw_data["cells"]
    warnings = []

    if not cells:
        return {}, {"total_raw_cells": 0, "represented_cells": 0,
                     "unaccounted_cells": [], "warnings": []}

    by_cell = {c["cell"]: c for c in cells}
    by_row = defaultdict(list)
    for c in cells:
        by_row[c["row"]].append(c)
    max_row_in_sheet = max(c["row"] for c in cells)

    def merge_span(cell_ref):
        rc = by_cell[cell_ref]
        mr = rc.get("merge_range")
        if not mr:
            return None
        return parse_merge_range(mr)  # (min_row, max_row, min_col, max_col)

    # ---- Step 1: classify merges (sheet-wide - these are raw geometric facts) ----
    wide_row_merges = []   # (row, min_col, max_col, cell_ref) - spans >1 col, 1 row
    tall_col_merges = []   # (col, min_row, max_row, cell_ref) - spans >1 row, 1 col

    for c in cells:
        mr = c.get("merge_range")
        if not mr:
            continue
        min_row, max_row, min_col, max_col = parse_merge_range(mr)
        if min_row == max_row and max_col > min_col:
            wide_row_merges.append((min_row, min_col, max_col, c["cell"]))
        elif min_col == max_col and max_row > min_row:
            tall_col_merges.append((min_col, min_row, max_row, c["cell"]))
        elif max_row > min_row and max_col > min_col:
            warnings.append(
                f"{c['cell']}: merge_range {mr} spans both multiple rows and "
                f"multiple columns - ambiguous, not classified as a group or section."
            )

    # ---- Step 2: sections (row-group merges) - sheet-wide, self-scoping by
    # their own row range, so no "pick one" ambiguity exists here. ----
    section_by_row = {}
    section_cells = []
    for col, min_row, max_row, ref in tall_col_merges:
        section_cells.append(ref)
        for r in range(min_row, max_row + 1):
            section_by_row[r] = ref
    section_anchor_cells = set(section_cells)

    # ---- Step 3: partition the sheet into independent REGIONS. A row with
    # >=2 sibling wide-row merges is a group-header CANDIDATE - but an
    # ordinary data row can coincidentally have the same shape. What
    # distinguishes a genuine new table from a coincidental repeat is
    # whether its merges cover a DIFFERENT set of columns than the table
    # already in progress. ----
    merges_by_row = defaultdict(list)
    for row, min_col, max_col, ref in wide_row_merges:
        merges_by_row[row].append((min_col, max_col, ref))

    candidate_rows = sorted(
        row for row, entries in merges_by_row.items() if len(entries) >= 2
    )

    def signature(row):
        return frozenset((mc, xc) for mc, xc, _ in merges_by_row[row])

    populated_rows = set(by_row.keys())

    group_header_rows = []
    last_signature = None
    for row in candidate_rows:
        sig = signature(row)
        if sig == last_signature:
            continue
        if group_header_rows and (row - 1) in populated_rows:
            continue
        group_header_rows.append(row)
        last_signature = sig

    regions = []
    if group_header_rows:
        first_header = group_header_rows[0]
        if first_header > 1:
            regions.append({"start": 1, "end": first_header - 1,
                             "header_row": None, "groups": []})
        for i, header_row in enumerate(group_header_rows):
            end = (group_header_rows[i + 1] - 1) if i + 1 < len(group_header_rows) \
                else max_row_in_sheet
            groups = [{"cell": ref, "min_col": mc, "max_col": xc}
                      for mc, xc, ref in sorted(merges_by_row[header_row])]
            regions.append({"start": header_row, "end": end,
                             "header_row": header_row, "groups": groups})
    else:
        regions.append({"start": 1, "end": max_row_in_sheet, "header_row": None, "groups": []})
        warnings.append(
            "No group-header row found anywhere (need >=2 sibling multi-column, "
            "single-row merges on the same row) - treating the whole sheet as one "
            "no-group region."
        )

    structure = {}
    used_cells = set()

    def _place(path, label_ref, value):
        node = structure
        for key in path:
            node = node.setdefault(key, {})
        node[label_ref] = value

    for region in regions:
        start, end = region["start"], region["end"]
        header_row = region["header_row"]
        groups = region["groups"]
        group_owned_cols = {c for g in groups for c in range(g["min_col"], g["max_col"] + 1)}

        def group_for_col(col, groups=groups):
            for g in groups:
                if g["min_col"] <= col <= g["max_col"]:
                    return g
            return None

        subheader_row = None
        subheader_by_col = {}
        if groups:
            for r in range(header_row + 1, end + 1):
                row_cells = by_row.get(r, [])
                counts = defaultdict(int)
                per_group_cells = defaultdict(list)
                for rc in row_cells:
                    if rc.get("merge_range"):
                        continue
                    g = group_for_col(rc["col"])
                    if g is not None:
                        counts[g["cell"]] += 1
                        per_group_cells[g["cell"]].append(rc)
                groups_with_multi = [g for g, n in counts.items() if n >= 2]
                if len(groups_with_multi) >= 2:
                    subheader_row = r
                    for g_cell, rcs in per_group_cells.items():
                        for rc in rcs:
                            subheader_by_col[rc["col"]] = rc["cell"]
                    break

        context_applies = defaultdict(bool)  # key: (section_ref_or_None, group_cell)
        if groups and subheader_row is not None:
            for r in range(subheader_row + 1, end + 1):
                row_cells = by_row.get(r, [])
                sect = section_by_row.get(r)
                for g in groups:
                    unmerged_in_group = [
                        rc for rc in row_cells
                        if g["min_col"] <= rc["col"] <= g["max_col"] and not rc.get("merge_range")
                    ]
                    if len(unmerged_in_group) >= 2:
                        context_applies[(sect, g["cell"])] = True

        def resolve_value_ref(rc, group, section_ref,
                               subheader_row=subheader_row,
                               subheader_by_col=subheader_by_col,
                               context_applies=context_applies):
            cell_ref = rc["cell"]
            row = rc["row"]

            if subheader_row is None or row <= subheader_row:
                return cell_ref

            if not context_applies.get((section_ref, group["cell"]), False):
                return cell_ref

            span = merge_span(cell_ref)
            if span is not None:
                _, _, min_col, max_col = span
                distinct_subheader_cols = {
                    col for col in range(min_col, max_col + 1) if col in subheader_by_col
                }
                if len(distinct_subheader_cols) >= 2:
                    return cell_ref

            ctx = subheader_by_col.get(rc["col"])
            return f"{ctx}:{cell_ref}" if ctx else cell_ref

        structural_rows = {header_row, subheader_row} - {None}

        for r in range(start, end + 1):
            if r in structural_rows:
                continue
            row_cells = by_row.get(r, [])
            if not row_cells:
                continue

            non_structural = [
                rc for rc in row_cells
                if rc["col"] not in group_owned_cols and rc["cell"] not in section_anchor_cells
            ]
            if not non_structural:
                continue

            non_structural.sort(key=lambda rc: rc["col"])
            label_rc = non_structural[0]
            label_ref = label_rc["cell"]
            other_non_group = non_structural[1:]
            section_ref = section_by_row.get(r)

            matched_any_group = False
            for g in groups:
                data_cells = [
                    rc for rc in row_cells
                    if g["min_col"] <= rc["col"] <= g["max_col"]
                ]
                if not data_cells:
                    continue
                matched_any_group = True
                data_cells.sort(key=lambda rc: rc["col"])
                refs = [resolve_value_ref(dc, g, section_ref) for dc in data_cells]
                value = refs[0] if len(refs) == 1 else refs

                path = [g["cell"]]
                if section_ref is not None:
                    path.append(section_ref)
                _place(path, label_ref, value)

                used_cells.add(label_ref)
                for dc in data_cells:
                    used_cells.add(dc["cell"])

            if not matched_any_group:
                if len(other_non_group) == 0:
                    warnings.append(
                        f"{label_ref} (row {r}, col {label_rc['col']}): no other "
                        f"populated, non-structural cell found on this row to pair "
                        f"it with - omitted from CELL_STRUCTURE."
                    )
                    continue
                refs = [rc["cell"] for rc in other_non_group]
                value = refs[0] if len(refs) == 1 else refs
                structure[label_ref] = value
                used_cells.add(label_ref)
                for rc in other_non_group:
                    used_cells.add(rc["cell"])

    # ---- Coverage audit ----
    def collect_refs(node, acc):
        if isinstance(node, dict):
            for k, v in node.items():
                acc.add(k)
                collect_refs(v, acc)
        elif isinstance(node, list):
            for item in node:
                collect_refs(item, acc)
        elif isinstance(node, str):
            if ":" in node:
                a, b = node.split(":", 1)
                acc.add(a)
                acc.add(b)
            else:
                acc.add(node)

    all_raw_refs = {c["cell"] for c in cells}
    referenced = set()
    collect_refs(structure, referenced)
    represented = all_raw_refs & referenced
    unaccounted = sorted(all_raw_refs - referenced, key=lambda ref: parse_ref(ref))

    for ref in unaccounted:
        rc = by_cell[ref]
        warnings.append(
            f"{ref} (row {rc['row']}, col {rc['col']}): populated cell was not "
            f"confidently classified - omitted from CELL_STRUCTURE."
        )

    diagnostics = {
        "total_raw_cells": len(all_raw_refs),
        "represented_cells": len(represented),
        "unaccounted_cells": unaccounted,
        "warnings": warnings,
    }

    return structure, diagnostics


# ---------------------------------------------------------------------------
# Stage 2: CELL_STRUCTURE + RAW_DATA -> final human-readable STRUCTURED JSON
# ---------------------------------------------------------------------------


def resolve_cell_structure(raw_data: dict, cell_structure: dict) -> dict:
    """Mechanically resolve every cell reference in cell_structure to its
    cached value from raw_data, per the four value forms: plain ref,
    "<context>:<value>" colon path, an array of either, or a nested dict."""
    by_cell = {c["cell"]: c for c in raw_data["cells"]}

    def resolve_ref(ref: str):
        rc = by_cell.get(ref)
        return rc["value"] if rc is not None else None

    def resolve_scalar(v: str):
        if ":" in v:
            ctx_ref, val_ref = v.split(":", 1)
            return {resolve_ref(ctx_ref): resolve_ref(val_ref)}
        return resolve_ref(v)

    def resolve_array(arr: list):
        merged = {}
        unlabeled = []
        for elem in arr:
            if isinstance(elem, str) and ":" in elem:
                ctx_ref, val_ref = elem.split(":", 1)
                merged[resolve_ref(ctx_ref)] = resolve_ref(val_ref)
            elif isinstance(elem, str):
                unlabeled.append(resolve_ref(elem))
            else:
                unlabeled.append(resolve_node(elem))

        if merged and unlabeled:
            # Rare fallback: an array mixing context:value paths with a bare
            # ref that has no subheader context of its own. There's no label
            # for it, so it can't become its own key - keep it visible under
            # a clearly-synthetic bucket rather than silently dropping it.
            merged["_unlabeled"] = unlabeled if len(unlabeled) > 1 else unlabeled[0]
            return merged
        if merged:
            return merged
        return unlabeled if len(unlabeled) > 1 else unlabeled[0]

    def resolve_node(node):
        if isinstance(node, dict):
            result = {}
            for k, v in node.items():
                resolved_key = resolve_ref(k)
                if isinstance(v, dict):
                    result[resolved_key] = resolve_node(v)
                elif isinstance(v, list):
                    result[resolved_key] = resolve_array(v)
                elif isinstance(v, str):
                    result[resolved_key] = resolve_scalar(v)
                else:
                    result[resolved_key] = None
            return result
        return None

    return resolve_node(cell_structure) if cell_structure else {}


def build_structured_sheet(raw_data: dict):
    """Convenience wrapper: RAW_DATA -> (STRUCTURED JSON, diagnostics)."""
    cell_structure, diagnostics = build_cell_structure(raw_data)
    structured = resolve_cell_structure(raw_data, cell_structure)
    return structured, diagnostics
