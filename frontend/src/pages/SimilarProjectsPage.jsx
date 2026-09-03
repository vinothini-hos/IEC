import { useEffect, useState, useCallback } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/SimilarProjects/PageHeader";
import QuerySummaryCard from "../components/SimilarProjects/QuerySummaryCard";
import ProjectCard from "../components/SimilarProjects/ProjectCard";

export default function SimilarProjectsPage() {
  const { threadId } = useParams();
  const [searchParams] = useSearchParams();
  const equipmentIndex = Number(searchParams.get("equipment_index") || 0);

  const [equipmentItem, setEquipmentItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [similarResult, setSimilarResult] = useState(null);
  const [selectedProjectId, setSelectedProjectId] = useState(null);

  const runSearch = useCallback(async () => {
    setSearching(true);
    setSearchError(null);
    try {
      const result = await api.findSimilarProjects(threadId, equipmentIndex);
      setSimilarResult(result);
      setSelectedProjectId(null);
    } catch (err) {
      setSearchError(err.message);
    } finally {
      setSearching(false);
    }
  }, [threadId, equipmentIndex]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSimilarResult(null);
    setSelectedProjectId(null);
    setSearchError(null);

    (async () => {
      const specData = await api.getSpecification(threadId);
      const item = specData.result?.equipment_items?.[equipmentIndex] || null;
      if (cancelled) return;
      setEquipmentItem(item);

      if (!item) {
        setLoading(false);
        return;
      }

      const cached = await api.getSimilarProjects(threadId, equipmentIndex);
      if (cancelled) return;
      setLoading(false);

      if (cached.result) {
        setSimilarResult(cached.result);
      } else {
        runSearch();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [threadId, equipmentIndex, runSearch]);

  const results = similarResult?.results || [];
  const closeMatches = results.filter((r) => (r.relevance_score ?? 0) >= 70).length;
  const partialMatches = results.filter(
    (r) => (r.relevance_score ?? 0) >= 40 && (r.relevance_score ?? 0) < 70
  ).length;

  const handleUseTopMatch = () => {
    if (results.length === 0) return;
    setSelectedProjectId(results[0].project_id);
  };

  if (loading) {
    return <div className="empty-state">Loading…</div>;
  }

  if (!equipmentItem) {
    return (
      <div className="spec-extraction-page">
        <div className="card spec-empty-card">
          <p>No extracted specification found for this RFQ yet — run Spec Extraction first.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="spec-extraction-page">
      <PageHeader
        closeMatches={closeMatches}
        partialMatches={partialMatches}
        hasResults={results.length > 0}
        onSearch={runSearch}
        searching={searching}
        onUseTopMatch={handleUseTopMatch}
      />

      <QuerySummaryCard equipmentItem={equipmentItem} />

      {searchError && <div className="clarification-error">{searchError}</div>}

      {searching && !similarResult && (
        <div className="card spec-empty-card">
          <p>Searching past projects…</p>
        </div>
      )}

      {!searching && similarResult && results.length === 0 && (
        <div className="card spec-empty-card">
          <p>{similarResult.message || "No similar past projects found."}</p>
        </div>
      )}

      {results.length > 0 && (
        <div className="project-results-list">
          {results.map((r) => (
            <ProjectCard
              key={r.project_id}
              result={r}
              selected={r.project_id === selectedProjectId}
              onSelect={() => setSelectedProjectId(r.project_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
