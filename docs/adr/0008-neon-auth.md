# ADR-0008 — Neon Managed Better Auth via Next.js BFF

Status: accepted.

Context: New Neon projects get Managed Better Auth (Better Auth-based), not Stack Auth — there are no Stack keys to fetch, only an Auth URL + JWKS URL. The browser can't call FastAPI directly (session lives in httpOnly cookies), and custom JWT duplicated the auth system.

Decision: `@neondatabase/auth` in Next.js (auth proxy routes + middleware + email signup/signin). Browser calls FastAPI only through `/api/bff/*` routes, which verify the session server-side and forward with `INTERNAL_API_SECRET` + `x-user-id`. FastAPI trusts the BFF header and auto-provisions `users` by `external_id`. Custom JWT and Stack code deleted.

Consequences: One extra local hop per API call (fine for MVP). Needs `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET`, shared `INTERNAL_API_SECRET` in env. FastAPI is unreachable without the BFF secret.
