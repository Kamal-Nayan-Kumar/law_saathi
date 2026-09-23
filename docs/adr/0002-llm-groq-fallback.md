# ADR-0002 — Groq gpt-oss-120b primary, OpenRouter fallback

Status: accepted.

Context: Need fast free-tier LLM for demo; single-provider outage kills viva.

Decision: Groq `gpt-oss-120b` primary; OpenRouter (Llama-class) fallback on error/rate-limit.

Consequences: Two keys to manage; response-agent code must handle provider switch + log which model answered.
