# ADR-0004 — Qdrant Cloud for vectors, Neon for app data

Status: accepted.

Context: Need semantic search + structured history without self-hosting.

Decision: Qdrant Cloud = vectors + provenance; Neon Postgres = users, sessions, messages, memory, logs.

Consequences: Two free-tier quotas to watch; ingestion must write Qdrant point IDs back to Neon for audit.
