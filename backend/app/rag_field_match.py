"""
Weighted field-by-field similarity between the new project and one
historical candidate — complements the RRF-fused rank (which only reflects
overall text similarity) with an explicit check on the fields that actually
matter most for engineering relevance.

Weight tiers reflect the explicit priority order given for the 24-field
SO2/CL2 template in template_consolidation.py:
  1. Description, Application
  2. Design Capacity
  3. SO2/Chlorine Temperature required @ vaporizer gas outlet
  4. Heating media, Heating Fluid
  5. Bare vaporizer / Complete skid system with all instruments & Controls
  All other fields: one uniform (lower) priority.
"""

import re

PRIORITY_WEIGHTS = [6.0, 5.0, 4.0, 3.0, 2.0]  # priority 1..5, highest first
DEFAULT_WEIGHT = 1.0  # "rest of all are same priority"

FIELD_WEIGHTS = {
    # Priority 1
    "description": PRIORITY_WEIGHTS[0],
    "application": PRIORITY_WEIGHTS[0],
    # Priority 2
    "design_capacity_kg_hr": PRIORITY_WEIGHTS[1],
    # Priority 3 — same field for both gases, so it applies whichever
    # equipment type (SO2 or CL2) the search is running for
    "so2_temperature_at_vaporizer_outlet_c": PRIORITY_WEIGHTS[2],
    "cl2_temperature_at_vaporizer_outlet_c": PRIORITY_WEIGHTS[2],
    # Priority 4
    "heating_media": PRIORITY_WEIGHTS[3],
    "heating_fluid": PRIORITY_WEIGHTS[3],
    # Priority 5
    "scope_bare_or_complete_skid": PRIORITY_WEIGHTS[4],
}
# Every other field (qty, location_installation, system_bolt_down_location,
# winter_min_max_temperature, orientation, source_of_so2/cl2, the inlet
# temperature/pressure fields, the outlet pressure fields, tonner fields,
# instrument/electrical specs, area_classification, site_layout_provided,
# tentative_finalization_month_year) falls back to DEFAULT_WEIGHT.

_NUMBER_RE = re.compile(r"-?\d+(\.\d+)?")


def _first_number(value) -> float:
    match = _NUMBER_RE.search(str(value))
    return float(match.group()) if match else None


def _field_similarity(value_a, value_b) -> float:
    num_a, num_b = _first_number(value_a), _first_number(value_b)
    if num_a is not None and num_b is not None:
        denom = max(abs(num_a), abs(num_b), 1e-6)
        return max(0.0, 1.0 - abs(num_a - num_b) / denom)

    text_a, text_b = str(value_a).strip().lower(), str(value_b).strip().lower()
    if not text_a or not text_b:
        return 0.0
    if text_a == text_b:
        return 1.0

    tokens_a, tokens_b = set(text_a.split()), set(text_b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def field_match_score(new_fields: dict, candidate_fields: dict) -> float:
    """new_fields / candidate_fields: {field_key: value_or_None} (the flat
    shape — see rag_service._flatten_fields). Returns a weighted [0,1]
    score over fields with a real value on both sides; 0.5 (neutral) if
    there's no overlapping field to compare."""
    weighted_sum = 0.0
    weight_total = 0.0

    for key, new_value in (new_fields or {}).items():
        if new_value is None:
            continue
        candidate_value = (candidate_fields or {}).get(key)
        if candidate_value is None:
            continue

        weight = FIELD_WEIGHTS.get(key, DEFAULT_WEIGHT)
        weighted_sum += weight * _field_similarity(new_value, candidate_value)
        weight_total += weight

    if weight_total == 0:
        return 0.5
    return weighted_sum / weight_total
