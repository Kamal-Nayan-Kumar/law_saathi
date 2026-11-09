"""Live charts from live_* JSON artifacts only. matplotlib only, Agg backend."""
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent.parent  # report/
EVALS = BASE / "evals"
CHARTS = BASE / "charts"
CHARTS.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.family"] = "DejaVu Sans"


def load(name: str):
    with (EVALS / name).open() as f:
        return json.load(f)


def save(fig, name: str):
    fig.tight_layout()
    out = CHARTS / name
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out} ({out.stat().st_size} bytes)")


# 1. Live golden pass by language
def chart_golden_by_lang():
    d = load("live_golden_results.json")
    langs = ["en", "hi", "kn"]
    names = {"en": "English", "hi": "Hindi", "kn": "Kannada"}
    labels = [names[l] for l in langs if l in d["by_lang"]]
    passed = [d["by_lang"][l]["passed"] for l in langs if l in d["by_lang"]]
    totals = [d["by_lang"][l]["n"] for l in langs if l in d["by_lang"]]
    rates = [p / t * 100 for p, t in zip(passed, totals)]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(labels, rates, color=["#1E88E5", "#FB8C00", "#2E7D32"], edgecolor="white")
    for bar, rate, p, t in zip(bars, rates, passed, totals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{p}/{t} ({rate:.0f}%)", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylim(0, 110)
    ax.set_ylabel("Pass rate (%)")
    ax.set_title(
        f"Live golden: pass by language\nOverall {d['passed']}/{d['n']} = {d['pass_rate']*100:.1f}%",
        fontsize=11, pad=12,
    )
    save(fig, "live_golden_by_lang.png")


# 2. Live verifier catch
def chart_verifier():
    d = load("live_verifier_results.json")
    cats = ["Grounded passed", "Mutated caught", "False pass", "False fail"]
    vals = [
        d["grounded_passed"],
        d["mutated_caught"],
        int(d["false_pass_rate"] * d["n"]),
        int(d["false_fail_rate"] * d["n"]),
    ]
    rates = [v / d["n"] * 100 for v in vals]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(cats, rates, color=["#1E88E5", "#2E7D32", "#FB8C00", "#E53935"], edgecolor="white")
    for bar, v, r in zip(bars, vals, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{v}/{d['n']} ({r:.0f}%)", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylim(0, 115)
    ax.set_ylabel("Rate (%)")
    ax.set_title(
        f"Live verifier: catch rate\nCatch {d['mutated_caught']}/{d['n']} = {d['catch_rate']*100:.0f}% (40 calls used)",
        fontsize=11, pad=12,
    )
    save(fig, "live_verifier_catch.png")


# 3. Live generation judge means (n=4)
def chart_generation_judge():
    d = load("live_generation_results.json")
    means = d["judge_mean_scores"]
    order = ["faithfulness", "citation_correctness", "clarity", "language_match", "refusal_correctness"]
    labels = [a.replace("_", " ") for a in order]
    vals = [means[a] for a in order]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    bars = ax.bar(labels, vals, color=["#5E35B1", "#1E88E5", "#2E7D32", "#FB8C00", "#00897B"], edgecolor="white")
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.08,
                f"{v:.2f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylim(0, 5.8)
    ax.set_ylabel("Judge mean (1 to 5)")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_title(f"Live generation: judge means (n={d['judge_scored']})\nDeterministic {d['deterministic_passed']}/{d['n']}", fontsize=11, pad=12)
    save(fig, "live_generation_judge.png")


# 4. Live golden failure reasons (problem instances from fail rows)
def chart_failures():
    d = load("live_golden_results.json")
    kinds = Counter()
    fail_rows = 0
    for r in d["results"]:
        if r["deterministic_pass"]:
            continue
        fail_rows += 1
        for p in r["problems"]:
            if p.startswith("missing term"):
                kinds["missing term"] += 1
            elif "none of" in p:
                kinds["missing section cited"] += 1
            elif "not verified" in p:
                kinds["not verified"] += 1
            else:
                kinds[p] += 1
    order = ["missing term", "missing section cited", "not verified"]
    labels = [k for k in order if k in kinds] + [k for k in kinds if k not in order]
    vals = [kinds[k] for k in labels]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(labels, vals, color=["#E53935", "#FB8C00", "#5E35B1"], edgecolor="white")
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                str(v), ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_ylim(0, max(vals) * 1.3 if vals else 1)
    ax.set_ylabel("Problem count (instances)")
    ax.set_title(
        f"Live golden: failure reasons\n{fail_rows} fail rows, {sum(vals)} problem instances",
        fontsize=11, pad=12,
    )
    save(fig, "live_failures.png")


if __name__ == "__main__":
    chart_golden_by_lang()
    chart_verifier()
    chart_generation_judge()
    chart_failures()
