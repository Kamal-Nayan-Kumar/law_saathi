# ADR-0007 — Landing + chat + admin portals, family-law theme

Status: accepted.

Context: Real app needs public landing → login/signup → chat; solo admin needs ingestion control; campus_saathi already solved both portal patterns.

Decision: Three surfaces: public landing page, user chat portal, admin portal (upload/list/delete docs, Firecrawl crawl, chunk counts). Reuse campus_saathi patterns: dot-grid thread background (`radial-gradient` 1px dots), chat bubbles, thinking indicator, sources/citation box, admin dropzone + confirm-before-ingest modal. Theme: Indian family-law feel (deep maroon/slate + marigold accents, serif display font). WhatsApp/other integrations: out of scope.

Consequences: Frontend work grows (T12, T13), but admin self-service replaces manual ingestion scripts and the viva demo has a clear landing → chat → citations story.
