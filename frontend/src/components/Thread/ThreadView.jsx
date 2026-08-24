import { useEffect, useRef, useState } from "react";
import EmailBubble from "./EmailBubble";
import ReplyBox from "./ReplyBox";
import { api } from "../../api/client";

export default function ThreadView({ thread, onThreadUpdated }) {
  const [sending, setSending] = useState(false);
  const timelineRef = useRef(null);
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

  useEffect(() => {
    if (timelineRef.current) {
      timelineRef.current.scrollTop = timelineRef.current.scrollHeight;
    }
  }, [thread]);

  if (!thread) {
    return <div className="empty-state">Select a thread to view it</div>;
  }

  const handleSend = async (bodyText) => {
    const last = thread.emails[thread.emails.length - 1];
    setSending(true);
    try {
      const updated = await api.sendEmail({
        thread_id: thread.id,
        to: last?.sender || "",
        subject: thread.subject.startsWith("Re:")
          ? thread.subject
          : `Re: ${thread.subject}`,
        body_text: bodyText,
      });
      onThreadUpdated(updated);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="thread-view">
      <div className="thread-view-header">
        <h2>{thread.subject || "(no subject)"}</h2>
        <div className="participants">{thread.participants}</div>
      </div>

      <div className="thread-timeline" ref={timelineRef}>
        {thread.emails.map((email) => (
          <EmailBubble key={email.id} email={email} />
        ))}
      </div>

      <ReplyBox onSend={handleSend} sending={sending} />
    </div>
  );
}
