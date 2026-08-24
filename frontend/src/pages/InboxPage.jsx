import { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ThreadList from "../components/Inbox/ThreadList";
import ThreadView from "../components/Thread/ThreadView";
import { api } from "../api/client";

export default function InboxPage() {
  const { threadId } = useParams();
  const navigate = useNavigate();

  const [threads, setThreads] = useState([]);
  const [threadDetail, setThreadDetail] = useState(null);
  const [loadingList, setLoadingList] = useState(true);

  const loadThreads = useCallback(async () => {
    setLoadingList(true);
    try {
      const data = await api.listThreads();
      setThreads(data);
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  useEffect(() => {
    if (!threadId) {
      setThreadDetail(null);
      return;
    }
    api.getThread(threadId).then(setThreadDetail);
  }, [threadId]);

  // Backend auto-syncs with Gmail in the background; poll here so new
  // mail shows up in the UI without a manual page reload.
  useEffect(() => {
    const interval = setInterval(() => {
      loadThreads();
      if (threadId) api.getThread(threadId).then(setThreadDetail);
    }, 20000);
    return () => clearInterval(interval);
  }, [threadId, loadThreads]);

  const handleSelect = (id) => navigate(`/threads/${id}`);

  const handleThreadUpdated = (updated) => {
    setThreadDetail(updated);
    loadThreads(); // refresh snippet/unread counts in the list
  };

  return (
    <div className="main-content">
      <ThreadList
        threads={threads}
        selectedId={threadId}
        onSelect={handleSelect}
        loading={loadingList}
      />
      <ThreadView thread={threadDetail} onThreadUpdated={handleThreadUpdated} />
    </div>
  );
}
