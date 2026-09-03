const STATUS_ICON = {
  confirmed: "✓",
  needs_review: "⚠",
  needs_clarification: "⚠",
  missing: "—",
};

export default function SpecificationField({ label, value, status, source }) {
  return (
    <div className={`spec-field spec-field-${status}`} title={source ? `Source: ${source}` : undefined}>
      <span className="spec-field-label">{label}</span>
      <span className="spec-field-value">{value || "—"}</span>
      <span className="spec-field-icon">{STATUS_ICON[status] || "—"}</span>
    </div>
  );
}