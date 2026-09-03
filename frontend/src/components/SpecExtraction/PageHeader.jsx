export default function PageHeader({
  title,
  classificationLabel,
  hasClarificationNeeded,
  onSendClarification,
  sendingClarification,
  onExtract,
  extracting,
  onFindSimilarProjects,
}) {
  return (
    <div className="spec-page-header">
      <div>
        <h1>
          Spec Extraction
          {title && (
            <>
              {" "}
              · <span className="spec-title-accent">{title}</span>
            </>
          )}
        </h1>
        {classificationLabel && (
          <div className="spec-classification">
            Enquiry classified as: <strong>{classificationLabel}</strong>
          </div>
        )}
      </div>
      <div className="spec-header-actions">
        <button
          type="button"
          className="btn-secondary"
          disabled={extracting}
          onClick={onExtract}
          title="Re-runs over the full thread, including any new replies/attachments"
        >
          {extracting ? "Extracting…" : "Extract Specification"}
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={!hasClarificationNeeded || sendingClarification}
          onClick={onSendClarification}
        >
          {sendingClarification ? "Sending…" : "Send clarification"}
        </button>
        <button type="button" className="btn-primary" onClick={onFindSimilarProjects}>
          Find similar projects →
        </button>
      </div>
    </div>
  );
}