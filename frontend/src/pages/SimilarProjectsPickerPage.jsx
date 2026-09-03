import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import ThreadList from "../components/Inbox/ThreadList";
import { api } from "../api/client";

export default function SimilarProjectsPickerPage() {
  const navigate = useNavigate();
  const [threads, setThreads] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadThreads = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listThreads();
      setThreads(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  return (
    <div className="main-content">
      <ThreadList
        threads={threads}
        selectedId={null}
        onSelect={(id) => navigate(`/similar-projects/${id}`)}
        loading={loading}
        title="Select RFQ"
      />
      <div className="empty-state">Select an RFQ to find similar past projects</div>
    </div>
  );
}
