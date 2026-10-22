# Web Search Fallback Architecture

## Overview
Web search in Law Saathi is a fallback mechanism used when statutory provisions in the vector index do not cover an emerging issue, when recent Supreme Court or High Court jurisprudence is needed, or during verifier retries.

The previous Firecrawl integration broke when API credits were exhausted (`PaymentRequiredError: Insufficient credits to perform this request`). To guarantee zero-cost operation for this college project, a multi-provider fallback engine was implemented in `api/app/agent.py`.

## Provider Chain

1. **Indian Kanoon (`kanoon`)** — Primary
   - Specialized search over Indian judicial decisions from the Supreme Court of India and all State High Courts.
   - Cost: $0, requires no API key, requires no sign-up or credit card.
   - Filters out irrelevant foreign case law automatically by querying Indian court records directly.
   - Returns full case titles, dates, court names, and direct URLs (`https://indiankanoon.org/doc/...`).

2. **DuckDuckGo Lite (`ddg`)** — Secondary
   - Clean, lightweight HTML endpoint (`https://lite.duckduckgo.com/lite/`).
   - Cost: $0, requires no API key.
   - Sanitizes and drops non-Indian or non-legal domains (e.g., US state court sites, social media).

3. **Firecrawl (`firecrawl`)** — Tertiary
   - Only invoked if `FIRECRAWL_API_KEY` is configured and has active credits.

## Configuration

Configure the active search chain via the `LAWSAATHI_WEB_SEARCH` environment variable in `api/.env`:

```bash
# Default: Try Indian Kanoon first, then DuckDuckGo Lite, then Firecrawl
LAWSAATHI_WEB_SEARCH=kanoon,ddg,firecrawl

# Disable web search entirely:
LAWSAATHI_WEB_SEARCH=off
```
