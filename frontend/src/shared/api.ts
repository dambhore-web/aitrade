// Shared fetch helpers -- every module's API calls should go through these
// rather than calling fetch() directly, so the base URL and error handling
// have one seam.

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Plain fetch() never times out -- if the backend hangs (it has, once: a
// dead geckodriver froze the whole process), a button reads "Saving..."
// forever with no error and no way to tell the difference from "still
// working". Every call below aborts after this and surfaces a clear error
// instead.
const DEFAULT_TIMEOUT_MS = 20000;

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON -- keep statusText
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

async function timedFetch(path: string, init?: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${API_BASE_URL}${path}`, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`No response after ${Math.round(timeoutMs / 1000)}s -- is the backend running/stuck?`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function apiGet<T>(path: string, timeoutMs?: number): Promise<T> {
  const res = await timedFetch(path, undefined, timeoutMs);
  return handle<T>(res);
}

export async function apiPost<T>(path: string, body?: unknown, timeoutMs?: number): Promise<T> {
  const res = await timedFetch(
    path,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    },
    timeoutMs
  );
  return handle<T>(res);
}

export async function apiPut<T>(path: string, body: unknown, timeoutMs?: number): Promise<T> {
  const res = await timedFetch(
    path,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    timeoutMs
  );
  return handle<T>(res);
}

export async function apiDelete<T>(path: string, timeoutMs?: number): Promise<T> {
  const res = await timedFetch(path, { method: "DELETE" }, timeoutMs);
  return handle<T>(res);
}
