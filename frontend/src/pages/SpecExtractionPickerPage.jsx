import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import ProjectListItem from "../components/SpecExtraction/ProjectListItem";
import { api } from "../api/client";

export default function SpecExtractionPickerPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listThreads();
      setProjects(data.filter((t) => t.extraction_status));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  return (
    <div className="main-content">
      <div className="thread-list">
        <div className="thread-list-header">Extracted Specifications</div>
        {loading && <div className="empty-state">Loading…</div>}
        {!loading && projects.length === 0 && (
          <div className="empty-state">
            No specifications extracted yet. Open an RFQ from the inbox and click "Extract
            Specification" to get started.
          </div>
        )}
        {projects.map((t) => (
          <ProjectListItem key={t.id} thread={t} onClick={() => navigate(`/spec-extraction/${t.id}`)} />
        ))}
      </div>
      <div className="empty-state">Select a project to view its extracted specification</div>
    </div>
  );
}
