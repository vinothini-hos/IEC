import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import ProjectListItem from "./ProjectListItem";
import { api } from "../../api/client";

/**
 * Full-page list of the RFQs a module has already worked on (like the Spec
 * Extraction picker): `include(thread)` picks them, `status(thread)` gives
 * each one's pill ({ label, className }), clicking opens `${basePath}/<id>`.
 */
export default function ProjectList({ title, include, status, basePath, emptyText }) {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listThreads();
      setProjects(data.filter(include));
    } finally {
      setLoading(false);
    }
  }, [include]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  return (
    <div className="project-list-page">
      <div className="thread-list-header">{title}</div>
      {loading && <div className="empty-state">Loading…</div>}
      {!loading && projects.length === 0 && <div className="empty-state">{emptyText}</div>}
      {projects.map((t) => (
        <ProjectListItem
          key={t.id}
          thread={t}
          status={status(t)}
          onClick={() => navigate(`${basePath}/${t.id}`)}
        />
      ))}
    </div>
  );
}
