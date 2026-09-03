export default function ClarificationCard({
  item, sending, sent, error, onSend,
}) {
  const needsClarification = Object.entries(item.fields || {}).filter(
    ([, f]) => f.status === "needs_clarification"
  );

  if (needsClarification.length === 0) return null;

  const draft = item.clarification_draft;

  return (
    <div className="card clarification-card">
      <h2>⚠ Clarification needed</h2>
      <p className="clarification-count">
        {needsClarification.length} field{needsClarification.length === 1 ? "" : "s"} require
        {needsClarification.length === 1 ? "s" : ""} clarification
      </p>

      <div className="clarification-field-list">
        {needsClarification.map(([key, f]) => (
          <div className="clarification-field" key={key}>
            <div className="clarification-field-label">{f.label}</div>
            <div className="clarification-field-value">
              Current value: {f.value || "—"}
            </div>
            <div className="clarification-field-status">Status: Needs clarification</div>
          </div>
        ))}
      </div>

      {draft && (
        <div className="clarification-email">
          <div className="clarification-email-header">
            {sent
              ? "Clarification email sent"
              : "Auto-generated clarification email · ready to send"}
          </div>
          <div className="clarification-email-meta">
            <div><strong>To:</strong> {draft.recipient}</div>
            <div><strong>Subject:</strong> {draft.subject}</div>
          </div>
          <pre className="clarification-email-body">{draft.body}</pre>

          {error && <div className="clarification-error">{error}</div>}

          {!sent && (
            <button type="button" className="btn-primary" disabled={sending} onClick={onSend}>
              {sending ? "Sending…" : "Send clarification"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}