// Single shared API client for the whole platform frontend.
// Every page imports get/post/put/del from here instead of hand-rolling fetch.
// - Always sends cookies (credentials: 'include') for the session.
// - Always parses JSON.
// - On a non-2xx response throws an ApiError carrying status + the backend's
//   error body so callers can show a useful message.

const BASE = "/api";

export class ApiError extends Error {
  constructor(status, body, url) {
    const msg =
      (body && (body.error || body.detail || body.message)) ||
      `请求失败 (${status})`;
    super(typeof msg === "string" ? msg : JSON.stringify(msg));
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.url = url;
  }
}

async function request(method, path, { body, query, signal, headers } = {}) {
  let url = path.startsWith("/api") || path.startsWith("http") ? path : BASE + path;
  if (query && typeof query === "object") {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }

  const init = {
    method,
    credentials: "include",
    cache: "no-store",
    headers: { ...(headers || {}) },
    signal,
  };
  if (body !== undefined) {
    const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
    if (isFormData) {
      init.body = body;
    } else {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
  }

  const res = await fetch(url, init);
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) throw new ApiError(res.status, data, url);
  return data;
}

export const get = (path, opts) => request("GET", path, opts);
export const post = (path, body, opts) => request("POST", path, { ...opts, body });
export const put = (path, body, opts) => request("PUT", path, { ...opts, body });
export const del = (path, opts) => request("DELETE", path, opts);

// Auth helpers used by nav and pages.
export const auth = {
  me: () => get("/auth/me"),
  login: (identifier, password) => post("/auth/login", { username: identifier, password }),
  register: (email, password) => post("/auth/register", { email, password }),
  verifyEmail: (token) => post("/auth/verify-email", { token }),
  resendVerification: (email) => post("/auth/resend-verification", { email }),
  logout: () => post("/auth/logout"),
};

export const meta = {
  health: () => get("/health"),
};

// Typed-ish resource helpers.
export const robots = {
  list: () => get("/robots"),
  get: (id) => get(`/robots/${encodeURIComponent(id)}`),
  update: (id, payload) => put(`/robots/${encodeURIComponent(id)}`, payload),
  delete: (id) => del(`/robots/${encodeURIComponent(id)}`),
  deduplicate: () => post("/robots/deduplicate"),
  inspectStepAssembly: (payload, opts) => post("/robots/urdf/step/inspect", payload, opts),
  exportStepAssemblyUrdf: (payload) => post("/robots/urdf/step/assembly", payload),
  exportStepUrdf: (payload) => post("/robots/urdf/step", payload),
  exportStepFolderUrdf: (payload) => post("/robots/urdf/step-folder", payload),
  uploadUrdf: (payload) => post("/robots/urdf/upload", payload),
  uploadUrdfFolder: (payload) => post("/robots/urdf/folder", payload),
};

export const algorithms = {
  list: () => get("/algorithms"),
  get: (id) => get(`/algorithms/${encodeURIComponent(id)}`),
  register: (payload) => post("/algorithms", payload),
};

export const runs = {
  list: (query) => get("/runs", { query }),
  get: (id) => get(`/runs/${encodeURIComponent(id)}`),
  create: (payload, idempotencyKey = "") => post("/runs", payload, {
    headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
  }),
  cancel: (id) => post(`/runs/${encodeURIComponent(id)}/cancel`),
  resume: (id, payload = {}, idempotencyKey = "") => post(
    `/runs/${encodeURIComponent(id)}/resume`,
    payload,
    { headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {} },
  ),
  events: (id, after) => get(`/runs/${encodeURIComponent(id)}/events`, { query: { after } }),
  metrics: (id, after) => get(`/runs/${encodeURIComponent(id)}/metrics`, { query: { after } }),
};

export const play = {
  config: (runId) => get(`/play/${encodeURIComponent(runId)}`),
  latest: () => get("/play/latest"),
  demos: () => get("/play/demos"),
};

export const ops = {
  preflight: () => get("/ops/preflight"),
  artifacts: () => get("/ops/artifacts"),
  artifactCleanupPlan: () => get("/ops/artifacts/cleanup-plan"),
  cleanupLocalArtifacts: (payload = {}) => post("/ops/artifacts/cleanup-local", payload),
  cleanupRemoteCheckpoints: (payload = {}) => post("/ops/artifacts/cleanup-remote-checkpoints", payload),
  algorithms: () => get("/ops/algorithms"),
  queue: () => get("/ops/queue"),
  markOrphanedRuns: () => post("/ops/runs/mark-orphans"),
};

export const billing = {
  pricing: () => get("/billing/pricing"),
  me: (limit = 20) => get("/billing/me", { query: { limit } }),
  users: () => get("/billing/users"),
  topup: (username, amount_cents, note = "") =>
    post("/billing/topup", { username, amount_cents, note }),
};

export const payments = {
  wechat: {
    config: () => get("/payments/wechat/config"),
    createNative: (amount_cents) => post("/payments/wechat/native", { amount_cents }),
    orders: (limit = 20) => get("/payments/wechat/orders", { query: { limit } }),
    order: (id) => get(`/payments/wechat/orders/${encodeURIComponent(id)}`),
  },
};
