# Report index

Start with `REPORT.md` for the full writeup. Start with `prof_onepager.md` for the short version. Everything else is evidence.

## Read these

- `REPORT.md` - full report. Results, methods, failures, next steps, repro steps.
- `prof_onepager.md` - one page summary.

## Charts

- `charts/retrieval_by_set.png` - retrieval pass rate by set. From `evals/retrieval_results.json`.
- `charts/generation_checks.png` - generation stub pass rate by check axis. From `evals/generation_results.json`.
- `charts/verifier_catch.png` - verifier catch rate bar. From `evals/verifier_results.json`.
- `charts/e2e_stub.png` - e2e stub offline pass rate. From `evals/e2e_stub_results.json`.
- `charts/live_golden_by_lang.png` - live golden pass by language. From `evals/live_golden_results.json`.
- `charts/live_verifier_catch.png` - live verifier catch rate bar. From `evals/live_verifier_results.json`.
- `charts/live_generation_judge.png` - live generation judge means, n=4. From `evals/live_generation_results.json`.
- `charts/live_failures.png` - live golden failure reason counts. From `evals/live_golden_results.json`.

Charts are made by `evals/make_charts.py` and `evals/make_live_charts.py`. Rerun them when the JSONs change.

## Eval results

- `evals/retrieval_results.json` - Phase A retrieval. n=82, passed=74.
- `evals/verifier_results.json` - Phase B verifier. n=20, catch=20.
- `evals/generation_results.json` - Phase C generation, stub mode. n=39, passed=1. Live judge deferred.
- `evals/e2e_stub_results.json` - Phase C e2e, stub mode. total 44, passed=35.
- `evals/live_retrieval_results.json` - Phase E1 live raw retrieval. n=8, passed=2.
- `evals/live_smoke_results.json` - Phase E1 live smoke. checked=3, verified 3.
- `evals/live_verifier_results.json` - Phase E1 live verifier. n=20, catch=20, 40 calls used.
- `evals/live_generation_results.json` - Phase E2 live generation sample. n=15, deterministic passed=8, judge scored=4.
- `evals/live_golden_results.json` - Phase E2 live golden, full set. n=23, passed=14 (60.9 percent).

## Dataset

- `dataset/golden_expanded.py` - 39 expanded questions, 20 verifier mutation pairs, 20 retrieval expectations.
- `dataset/README.md` - what the dataset covers and how it was built.

## Runners

- `evals/run_retrieval.py` - Phase A runner.
- `evals/run_verifier.py` - Phase B runner.
- `evals/run_generation.py` - Phase C generation runner.
- `evals/run_e2e_stub.py` - Phase C e2e runner.
- `evals/judge_prompts.py` - live judge prompts, used when keys are present.
- `evals/make_charts.py` - chart generator (offline).
- `evals/run_live_retrieval.py` - Phase E1 runner: live raw retrieval plus 3 live smoke calls. Writes `live_retrieval_results.json` and `live_smoke_results.json`.
- `evals/run_live_verifier.py` - Phase E1 runner: live verifier on 20 mutation pairs. Writes `live_verifier_results.json`.
- `evals/run_live_generation.py` - Phase E2 runner: live generation sample of 15 plus judge. Writes `live_generation_results.json`.
- `evals/run_live_golden.py` - Phase E2 runner: live golden, all 23 questions via run_agent. Writes `live_golden_results.json`.
- `evals/make_live_charts.py` - live chart generator. Writes the four `live_*.png` charts.

## Quick repro

```bash
PYTHONPATH=. python3 -m report.evals.run_retrieval
PYTHONPATH=. python3 -m report.evals.run_verifier
PYTHONPATH=. python3 -m report.evals.run_generation
PYTHONPATH=. python3 -m report.evals.run_e2e_stub
python3 report/evals/make_charts.py
PYTHONPATH=. python3 -m report.evals.run_live_retrieval
PYTHONPATH=. python3 -m report.evals.run_live_verifier
PYTHONPATH=. python3 -m report.evals.run_live_generation
PYTHONPATH=. python3 -m report.evals.run_live_golden
python3 report/evals/make_live_charts.py
```
