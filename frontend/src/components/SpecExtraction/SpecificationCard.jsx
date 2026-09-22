import SpecificationField from "./SpecificationField";

export default function SpecificationCard({ fields, completion }) {
  const entries = Object.entries(fields || {});

  return (
    <div className="card spec-card">
      <div className="spec-card-header">
        <h2>Extracted specification</h2>
        {completion && (
          <span className="spec-completion-pill">
            {completion.filled} of {completion.total} fields · {completion.percent}% complete
          </span>
        )}
      </div>
      <div className="spec-field-grid">
        {entries.map(([key, field]) => (
          <SpecificationField
            key={key}
            label={field.label}
            value={field.value}
            status={field.status}
            source={field.source}
          />
        ))}
      </div>
    </div>
  );
}
