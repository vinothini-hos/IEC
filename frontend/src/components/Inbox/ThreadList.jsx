import ThreadListItem from "./ThreadListItem";

export default function ThreadList({ threads, selectedId, onSelect, loading, title = "RFQ Inbox" }) {
  return (
    <div className="thread-list">
      <div className="thread-list-header">{title}</div>
      {loading && <div className="empty-state">Loading…</div>}
      {!loading && threads.length === 0 && (
        <div className="empty-state">No emails yet</div>
      )}
      {threads.map((t) => (
        <ThreadListItem
          key={t.id}
          thread={t}
          selected={t.id === selectedId}
          onClick={() => onSelect(t.id)}
        />
      ))}
    </div>
  );
}
