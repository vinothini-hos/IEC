export function formatTimestamp(iso) {
  const date = new Date(iso);
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();

  if (sameDay) {
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function formatFullTimestamp(iso) {
  const date = new Date(iso);
  return date.toLocaleString([], {
    month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

export function initialsOrEmail(addr) {
  return addr || "Unknown";
}

// Splits a plain-text email body into the new content and the quoted
// reply history beneath it, so the UI can collapse the quoted part behind
// a "Read more". Looks for Gmail's "On <date>, <name> wrote:" marker,
// falling back to the first line starting with "> ".
export function splitQuotedReply(text) {
  if (!text) return { main: "", quoted: "" };

  const onWroteMatch = text.match(/^On .{0,300}wrote:\s*$/m);
  if (onWroteMatch) {
    return {
      main: text.slice(0, onWroteMatch.index).trimEnd(),
      quoted: text.slice(onWroteMatch.index).trim(),
    };
  }

  const lines = text.split("\n");
  const quoteStart = lines.findIndex((l) => l.trimStart().startsWith(">"));
  if (quoteStart > 0) {
    return {
      main: lines.slice(0, quoteStart).join("\n").trimEnd(),
      quoted: lines.slice(quoteStart).join("\n").trim(),
    };
  }

  return { main: text, quoted: "" };
}
