import { useState } from "react";

export default function ReplyBox({ onSend, sending }) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState([]);
  const [error, setError] = useState(null);

  const handleSend = async () => {
    if (!text.trim()) return;
    setError(null);
    try {
      await onSend(text, files);
      setText("");
      setFiles([]);
    } catch (err) {
      setError(err.message || "Failed to send");
    }
  };

  const handleFilesChosen = (e) => {
    setFiles((prev) => [...prev, ...Array.from(e.target.files)]);
    e.target.value = "";
  };

  const removeFile = (index) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
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
      {error && <div className="reply-box-error">{error}</div>}
      {files.length > 0 && (
        <div className="reply-box-attachments">
          {files.map((f, i) => (
            <span className="attachment-chip" key={`${f.name}-${i}`}>
              📎 {f.name}
              <button
                type="button"
                className="attachment-chip-remove"
                onClick={() => removeFile(i)}
                aria-label={`Remove ${f.name}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="reply-box-actions">
        <label className="btn-secondary attach-btn">
          Attach
          <input type="file" multiple onChange={handleFilesChosen} hidden />
        </label>
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
