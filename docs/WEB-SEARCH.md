# Web Search Architecture (Firecrawl)

## Overview
Web search in Law Saathi is powered exclusively by **Firecrawl** (`https://api.firecrawl.dev/v1/search`), configured via `FIRECRAWL_API_KEY`. It is invoked for:
- Local legal representation queries (family law advocates, District Legal Services Authority clinics, family court locations).
- Recent Supreme Court and High Court jurisprudence not yet codified into bare Act statutory text.
- Post-2023 legal developments and amendments.
- Verifier retry rounds when initial bare Act retrieval indicates missing judicial interpretations.

## Configuration
Web search requires `FIRECRAWL_API_KEY` in `api/.env`:

```bash
FIRECRAWL_API_KEY=fc-...
LAWSAATHI_WEB_SEARCH=firecrawl
```

To disable web search entirely during isolated testing:
```bash
LAWSAATHI_WEB_SEARCH=off
```
