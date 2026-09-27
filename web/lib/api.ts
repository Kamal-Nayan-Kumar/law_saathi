export async function api(path: string, init?: RequestInit, timeoutMs = 150000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`/api/bff${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    if (res.status === 204) return null;
    return res.json();
  } catch (e: any) {
    if (e?.name === "AbortError") {
      throw new Error("The answer is taking too long. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
