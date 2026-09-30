const STATUS_ICON = {
  confirmed: "✓",
  needs_clarification: "⚠",
  missing: "—",
};

function formatValue(value, status) {
  if (status === "missing") return "-";
  if (status === "needs_clarification") return "Not specified";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return value || "-";
}

export default function SpecificationField({ label, value, status, source, reason }) {
  const title = reason ? `Why: ${reason}` : source ? `Source: ${source}` : undefined;
  return (
    <div className={`spec-field spec-field-${status}`} title={title}>
      <span className="spec-field-label">{label}</span>
      <span className="spec-field-value">{formatValue(value, status)}</span>
      <span className="spec-field-icon">{STATUS_ICON[status] || "—"}</span>
    </div>
  );
}
