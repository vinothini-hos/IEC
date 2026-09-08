function scoreTier(score) {
  if (score == null) return "low";
  if (score >= 70) return "high";
  if (score >= 40) return "medium";
  return "low";
}

export default function ProjectCard({ result, onSelect }) {
  const tier = scoreTier(result.relevance_score);

  return (
    <div
      className={`card project-card project-card-${tier}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onSelect();
      }}
    >
      <div className="project-card-main">
        <div className="project-card-id">{result.project_id}</div>
        <div className="project-card-justification">{result.justification}</div>
        {result.vector_similarity != null && (
          <div className="project-card-vector">Vector similarity: {result.vector_similarity}</div>
        )}
      </div>
      <div className={`project-score-badge project-score-${tier}`}>
        <div className="project-score-value">
          {result.relevance_score != null ? `${result.relevance_score}%` : "—"}
        </div>
        <div className="project-score-label">MATCH</div>
      </div>
    </div>
  );
}
