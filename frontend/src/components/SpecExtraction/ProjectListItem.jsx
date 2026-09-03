import { formatTimestamp } from "../../utils/format";

const STATUS_LABEL = {
  extracted: "Extracted",
  waiting_for_customer_response: "Waiting on customer",
};

export default function ProjectListItem({ thread, onClick }) {
  return (
    <div className="thread-item" onClick={onClick}>
      <div className="thread-item-top">
        <span className="thread-item-participants">{thread.participants || "Unknown sender"}</span>
        <span className="thread-item-time">{formatTimestamp(thread.last_message_at)}</span>
      </div>
      <div className="thread-item-subject">{thread.subject || "(no subject)"}</div>
      <div className="project-list-item-footer">
        {thread.classification_summary && (
          <span className="project-list-item-classification">{thread.classification_summary}</span>
        )}
        <span className={`project-status-pill project-status-${thread.extraction_status}`}>
          {STATUS_LABEL[thread.extraction_status] || thread.extraction_status}
        </span>
      </div>
    </div>
  );
}
