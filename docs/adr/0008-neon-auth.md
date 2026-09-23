# ADR-0008 — Neon Auth (Stack Auth), custom JWT removed

Status: accepted.

Context: T1 shipped custom JWT login, but the project uses Neon Auth. Two login systems would confuse users and the viva.

Decision: Stack Auth everywhere. Frontend: `@stackframe/stack` (StackProvider + handler routes + SignIn). Backend: verify the Stack access token locally via JWKS (ES256, audience = project ID), auto-provision `users` by `external_id` (Stack sub). Custom `/auth/register|login`, bcrypt, and `AUTH_SECRET` deleted; `users.email` nullable (access tokens carry only `sub`).

Consequences: Needs 3 Stack keys (project ID, publishable key, secret key) in env. No password code to maintain; login/signup/OAuth come from Stack.
