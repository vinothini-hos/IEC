import { formatTimestamp } from "../../utils/format";

export default function ThreadListItem({ thread, selected, onClick }) {
  const isUnread = thread.unread_count > 0;

  return (
    <div
      className={
        "thread-item" +
        (selected ? " selected" : "") +
        (isUnread ? " unread" : "")
      }
      onClick={onClick}
    >
      <div className="thread-item-top">
        <span className="thread-item-participants">
          {isUnread && <span className="thread-item-unread-dot" />}
          {thread.participants || "Unknown sender"}
        </span>
        <span className="thread-item-time">
          {formatTimestamp(thread.last_message_at)}
        </span>
      </div>
      <div className="thread-item-subject">{thread.subject || "(no subject)"}</div>
      <div className="thread-item-snippet">{thread.latest_snippet}</div>
    </div>
  );
}
