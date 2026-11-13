// Typed fetch wrapper for the Shelfcraft API (same-origin /api → FastAPI via Next rewrites).
export class ApiError extends Error {
  status: number;
  code?: string;
  data?: unknown;
  constructor(message: string, status: number, code?: string, data?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.data = data;
  }
}

function token(): string | null {
  try {
    return localStorage.getItem("shelfcraft-token");
  } catch {
    return null;
  }
}

function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && "message" in d) return String((d as { message: unknown }).message);
  }
  if (status === 502 || status === 504 || status === 500)
    return status === 500 ? "The server hit an unexpected error." : "Can't reach the Shelfcraft backend. Is it running?";
  return `Request failed (${status})`;
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const t = token();
  if (t) headers.set("X-Shelfcraft-Token", t);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...init, headers, body });
  } catch {
    throw new ApiError("Can't reach the Shelfcraft backend. Is it running?", 0, "network");
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("application/json") ? await res.json().catch(() => null) : null;
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status, data?.code, data);
  return (data ?? (await res.text())) as T;
}

export const get = <T,>(path: string) => api<T>(path);
export const post = <T,>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const patch = <T,>(path: string, json: unknown) => api<T>(path, { method: "PATCH", json });
export const put = <T,>(path: string, json: unknown) => api<T>(path, { method: "PUT", json });
export const del = (path: string) => api<void>(path, { method: "DELETE" });

export async function upload<T>(path: string, files: File[] | File, field = "files", extra?: Record<string, string>): Promise<T> {
  const fd = new FormData();
  const list = Array.isArray(files) ? files : [files];
  for (const f of list) fd.append(field, f);
  for (const [k, v] of Object.entries(extra ?? {})) fd.append(k, v);
  return api<T>(path, { method: "POST", body: fd });
}

/** Download a binary response (ZIP/CSV/PNG) and save it with the server-provided filename. */
export async function download(path: string, init: RequestInit & { json?: unknown } = {}, fallbackName = "download") {
  const headers = new Headers(init.headers);
  const t = token();
  if (t) headers.set("X-Shelfcraft-Token", t);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`/api${path}`, { ...init, headers, body });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(errorMessage(data, res.status), res.status);
  }
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const m = /filename="?([^";]+)"?/i.exec(cd);
  const name = m?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  return { name, size: blob.size, width: res.headers.get("x-export-width"), height: res.headers.get("x-export-height") };
}
