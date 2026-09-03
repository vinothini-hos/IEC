// Headline fields to pull into the one-line query summary, per equipment
// type — order matters, values are shown as-is (never reworded/abbreviated).
const HEADLINE_FIELD_KEYS = {
  SO2: [
    "design_capacity_kg_hr",
    "vaporizer_heat_source_available",
    "installation_indoor_outdoor",
    "instrument_specification",
    "source_of_so2",
  ],
  CL2: [
    "design_capacity_kg_hr",
    "vaporizer_heat_source_available",
    "installation_indoor_outdoor",
    "instrument_specification",
    "source_of_cl2",
  ],
};

export default function QuerySummaryCard({ equipmentItem }) {
  if (!equipmentItem) return null;

  const keys = HEADLINE_FIELD_KEYS[equipmentItem.type_label] || [];
  const parts = [equipmentItem.equipment_name];
  for (const key of keys) {
    const value = equipmentItem.fields?.[key]?.value;
    if (value) parts.push(value);
  }

  return (
    <div className="card query-summary-card">
      <div className="query-summary-label">Query summary</div>
      <div className="query-summary-line">{parts.join(" · ")}</div>
    </div>
  );
}
