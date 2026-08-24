import { formatFullTimestamp } from "../../utils/format";
import { api } from "../../api/client";

export default function EmailBubble({ email }) {
  return (
    <div className={`email-bubble ${email.direction}`}>
      <div className="email-bubble-meta">
        <span>
          <span className={`direction-tag ${email.direction}`}>
            {email.direction === "incoming" ? "Received" : "Sent"}
          </span>
        </span>
        <span>{formatFullTimestamp(email.sent_at)}</span>
      </div>
      <div className="email-bubble-meta" style={{ marginBottom: 10 }}>
        <span>
          <span className="from">{email.sender}</span>
          {" → "}
          {email.recipient}
          {email.cc ? ` (cc: ${email.cc})` : ""}
        </span>
      </div>
      <div className="email-bubble-body">{email.body_text}</div>
      {email.attachments?.length > 0 && (
        <div className="email-bubble-attachments">
          {email.attachments.map((a) =>
            a.has_download ? (
              <a
                className="attachment-chip attachment-chip-link"
                key={a.id}
                href={api.attachmentDownloadUrl(a.id)}
                target="_blank"
                rel="noreferrer"
              >
                📎 {a.filename}
              </a>
            ) : (
              <span className="attachment-chip" key={a.id} title="Not downloadable yet">
                📎 {a.filename}
              </span>
            )
          )}
        </div>
      )}
    </div>
  );
}
