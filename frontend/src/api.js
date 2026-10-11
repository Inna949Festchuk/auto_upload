async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Ошибка ${res.status}`);
  }
  return data;
}

export const api = {
  tokenStatus: () => request("/api/token/"),
  saveToken: (token) => request("/api/token/", { method: "POST", body: JSON.stringify({ token }) }),
  deleteToken: () => request("/api/token/", { method: "DELETE" }),
  oauthUrl: () => request("/api/oauth-url/"),
  browse: (path) => request(`/api/disk/browse/?path=${encodeURIComponent(path)}`),
  tasks: () => request("/api/tasks/"),
  createTask: (dest, items) =>
    request("/api/tasks/", { method: "POST", body: JSON.stringify({ dest, items }) }),
  cancelTask: (id) => request(`/api/tasks/${id}/cancel/`, { method: "POST" }),
  deleteTask: (id) => request(`/api/tasks/${id}/`, { method: "DELETE" }),
};
