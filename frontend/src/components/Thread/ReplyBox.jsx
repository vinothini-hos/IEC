import { useState } from "react";

export default function ReplyBox({ onSend, sending }) {
  const [text, setText] = useState("");

  const handleSend = () => {
    if (!text.trim()) return;
    onSend(text);
    setText("");
  };

  return (
    <div className="reply-box">
      <textarea
        placeholder="Write a reply…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend();
        }}
      />
      <div className="reply-box-actions">
        <button
          className="btn-primary"
          onClick={handleSend}
          disabled={sending || !text.trim()}
        >
          {sending ? "Sending…" : "Send reply"}
        </button>
      </div>
    </div>
  );
}
