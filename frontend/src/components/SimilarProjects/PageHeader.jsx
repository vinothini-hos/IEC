export default function PageHeader({
  closeMatches,
  partialMatches,
  hasResults,
  onSearch,
  searching,
  onUseTopMatch,
}) {
  return (
    <div className="spec-page-header">
      <div>
        <h1>Similar Project Discovery</h1>
        {hasResults && (
          <div className="spec-classification">
            {closeMatches} close match{closeMatches === 1 ? "" : "es"} · {partialMatches} partial
            match{partialMatches === 1 ? "" : "es"} · ranked by capacity, MOC, application,
            customer segment
          </div>
        )}
      </div>
      <div className="spec-header-actions">
        <button type="button" className="btn-secondary" disabled={searching} onClick={onSearch}>
          {searching ? "Searching…" : hasResults ? "Search again" : "Search Similar Projects"}
        </button>
        <button
          type="button"
          className="btn-primary"
          disabled={!hasResults}
          onClick={onUseTopMatch}
        >
          Use top match → generate BOQ
        </button>
      </div>
    </div>
  );
}
