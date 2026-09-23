export async function api(path: string, token?: string, init?: RequestInit) {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("lawsathi_token");
}

export function setToken(token: string) {
  localStorage.setItem("lawsathi_token", token);
}
