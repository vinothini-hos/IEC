const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed: ${res.status} ${text}`);
  }
  return res.json();
}

export const api = {
  listThreads: () => request("/threads"),
  getThread: (id) => request(`/threads/${id}`),
  syncThreads: () => request("/threads/sync", { method: "POST" }),
  sendEmail: (payload) =>
    request("/emails/send", { method: "POST", body: JSON.stringify(payload) }),
  markRead: (emailId, isRead) =>
    request(`/emails/${emailId}/read`, {
      method: "PATCH",
      body: JSON.stringify({ is_read: isRead }),
    }),
};
