export async function api(
  path: string,
  opts: { stackToken?: string; init?: RequestInit } = {},
) {
  const res = await fetch(`/api${path}`, {
    ...opts.init,
    headers: {
      "Content-Type": "application/json",
      ...(opts.stackToken ? { "x-stack-access-token": opts.stackToken } : {}),
      ...(opts.init?.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export async function stackTokenOf(app: {
  getUser: () => Promise<{ getAuthJson: () => Promise<{ accessToken: string | null }> } | null>;
}): Promise<string> {
  const user = await app.getUser();
  if (!user) throw new Error("Not signed in");
  const { accessToken } = await user.getAuthJson();
  if (!accessToken) throw new Error("No access token");
  return accessToken;
}
