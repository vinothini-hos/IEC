const BASE = "/api";

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const res = await fetch(`${BASE}${path}`, {
    headers: isFormData ? {} : { "Content-Type": "application/json" },
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
  sendEmail: ({ to, cc, subject, body_text, thread_id, files }) => {
    const form = new FormData();
    form.append("to", to);
    form.append("cc", cc || "");
    form.append("subject", subject);
    form.append("body_text", body_text);
    if (thread_id) form.append("thread_id", thread_id);
    (files || []).forEach((f) => form.append("files", f));
    return request("/emails/send", { method: "POST", body: form });
  },
  attachmentDownloadUrl: (attachmentId) => `${BASE}/emails/attachments/${attachmentId}/download`,
  markRead: (emailId, isRead) =>
    request(`/emails/${emailId}/read`, {
      method: "PATCH",
      body: JSON.stringify({ is_read: isRead }),
    }),
};
