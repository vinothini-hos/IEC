import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import EmailBubble from "./EmailBubble";
import ReplyBox from "./ReplyBox";
import { api } from "../../api/client";

// Who a reply should go to: the sender of the most recent incoming email,
// or — if we've only sent messages and haven't gotten a reply yet — the
// recipient of our last outgoing one, so we keep addressing the other
// party instead of ourselves.
function getReplyRecipient(emails) {
  for (let i = emails.length - 1; i >= 0; i--) {
    if (emails[i].direction === "incoming") return emails[i].sender;
  }
  const last = emails[emails.length - 1];
  return last?.recipient || last?.sender || "";
}

export default function ThreadView({ thread, onThreadUpdated }) {
  const navigate = useNavigate();
  const [sending, setSending] = useState(false);
  const markedRef = useRef(new Set());

  // Mark unread incoming emails as read once the thread is open.
  useEffect(() => {
    if (!thread) return;
    thread.emails
      .filter((e) => e.direction === "incoming" && !e.is_read)
      .forEach((e) => {
        if (markedRef.current.has(e.id)) return;
        markedRef.current.add(e.id);
        api.markRead(e.id, true).catch(() => {});
      });
  }, [thread]);

  if (!thread) {
    return <div className="empty-state">Select a thread to view it</div>;
  }

  const handleSend = async (bodyText, files) => {
    setSending(true);
    try {
      const updated = await api.sendEmail({
        thread_id: thread.id,
        to: getReplyRecipient(thread.emails),
        subject: thread.subject.startsWith("Re:")
          ? thread.subject
          : `Re: ${thread.subject}`,
        body_text: bodyText,
        files,
      });
      onThreadUpdated(updated);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="thread-view">
      <div className="thread-view-header">
        <div className="thread-view-header-top">
          <div>
            <h2>{thread.subject || "(no subject)"}</h2>
            <div className="participants">{thread.participants}</div>
          </div>
          <button
            type="button"
            className="extract-spec-btn"
            onClick={() => navigate(`/spec-extraction/${thread.id}`)}
          >
            Extract Specification
          </button>
        </div>
      </div>

      <div className="thread-timeline">
        {[...thread.emails].reverse().map((email) => (
          <EmailBubble key={email.id} email={email} />
        ))}
      </div>

      <ReplyBox onSend={handleSend} sending={sending} />
    </div>
  );
}
