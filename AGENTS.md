## Agent skills

### Issue tracker

Issues live in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five canonical labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout. See `docs/agents/domain.md`.

## Currently Used Models (for reference)

- **Embedding**: `intfloat/multilingual-e5-small` (Qdrant Cloud Inference, server-side)
- **Groq LLM**: `openai/gpt-oss-120b` (primary), fallbacks: `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`
- **OpenRouter fallback**: `meta-llama/llama-3.3-70b-instruct`
- **OpenCode Zen last-resort**: `space-bunny-free`
- **Sarvam STT**: `saaras:v4`, fallback: `whisper-large-v3-turbo`

## Open items (index)

- **Code of Civil Procedure, 1908 = 1823 chunks (~20% of `law_saathi`).** Tagged `topic=civil_procedure`, so filterable, but it may crowd out family acts on unfiltered queries. Trim option: keep only s.9, s.10, s.24, s.25 and Order 32 (minors).
- **CrPC 1973 intentionally not added:** absent from vaquill, and its successor BNSS 2023 s.144 (maintenance) is already indexed. Historical coverage would need an India Code scrape marked `kind: "repealed_statute"`.
- **Muslim maintenance acts still missing** (not in vaquill): Muslim Family Laws Act 1963, Muslim (Guardianship and Maintenance) Act 1926, Muslim Inheritance (Succession to Property) Act 1926.
