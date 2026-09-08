import { useEffect } from "react";

function scoreTier(score) {
  if (score == null) return "low";
  if (score >= 70) return "high";
  if (score >= 40) return "medium";
  return "low";
}

export default function ProjectDetailModal({ result, onClose }) {
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  if (!result) return null;

  const tier = scoreTier(result.relevance_score);
  const fieldEntries = Object.entries(result.fields || {});
  const keyPoints = result.key_points || [];
  const customer = result.customer_details;
  const boq = result.boq || [];

  return (
    <div className="project-modal-backdrop" onClick={onClose}>
      <div className="project-modal" onClick={(e) => e.stopPropagation()}>
        <div className="project-modal-header">
          <h2>{result.project_id}</h2>
          <button type="button" className="project-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="project-modal-body">
          <div className="card project-detail-summary">
            <div className={`project-score-badge project-score-${tier}`}>
              <div className="project-score-value">
                {result.relevance_score != null ? `${result.relevance_score}%` : "—"}
              </div>
              <div className="project-score-label">MATCH</div>
            </div>
            <div className="project-detail-summary-text">
              <div className="project-detail-justification">{result.justification}</div>
              {result.vector_similarity != null && (
                <div className="project-card-vector">
                  Vector similarity: {result.vector_similarity}
                </div>
              )}
            </div>
          </div>

          {customer && (
            <div className="card">
              <div className="project-detail-key-points-label">Customer details</div>
              <div className="project-detail-note">
                Illustrative sample data — not a real customer.
              </div>
              <div className="project-detail-fields">
                <div className="project-detail-field">
                  <span className="project-detail-field-label">Customer</span>
                  <span className="project-detail-field-value">{customer.customer_name}</span>
                </div>
                <div className="project-detail-field">
                  <span className="project-detail-field-label">Location</span>
                  <span className="project-detail-field-value">{customer.location}</span>
                </div>
                <div className="project-detail-field">
                  <span className="project-detail-field-label">Contact person</span>
                  <span className="project-detail-field-value">{customer.contact_person}</span>
                </div>
                <div className="project-detail-field">
                  <span className="project-detail-field-label">Contact email</span>
                  <span className="project-detail-field-value">{customer.contact_email}</span>
                </div>
                <div className="project-detail-field">
                  <span className="project-detail-field-label">Enquiry reference</span>
                  <span className="project-detail-field-value">{customer.enquiry_reference}</span>
                </div>
              </div>
            </div>
          )}

          {boq.length > 0 && (
            <div className="card">
              <div className="project-detail-key-points-label">Bill of quantities</div>
              <div className="project-detail-note">
                Illustrative sample pricing — not a real quotation.
              </div>
              <table className="project-detail-boq-table">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Qty</th>
                    <th>Unit</th>
                    <th>Unit price (₹)</th>
                    <th>Total (₹)</th>
                  </tr>
                </thead>
                <tbody>
                  {boq.map((line, i) => (
                    <tr key={i} className={line.quantity == null ? "boq-total-row" : undefined}>
                      <td>{line.item}</td>
                      <td>{line.quantity ?? ""}</td>
                      <td>{line.unit ?? ""}</td>
                      <td>
                        {line.unit_price_inr != null
                          ? line.unit_price_inr.toLocaleString("en-IN")
                          : ""}
                      </td>
                      <td>
                        {line.total_price_inr != null
                          ? line.total_price_inr.toLocaleString("en-IN")
                          : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="card">
            {fieldEntries.length > 0 ? (
              <div className="project-detail-fields">
                {fieldEntries.map(([key, f]) => (
                  <div className="project-detail-field" key={key}>
                    <span className="project-detail-field-label">{f.label}</span>
                    <span className="project-detail-field-value">{f.value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p>No field data available for this project.</p>
            )}

            {keyPoints.length > 0 && (
              <div className="project-detail-key-points">
                <div className="project-detail-key-points-label">Additional notes</div>
                <ul>
                  {keyPoints.map((point, i) => (
                    <li key={i}>{point}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
