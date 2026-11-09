"""Phase D charts from eval JSON artifacts only. matplotlib only, Agg backend."""
import json
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


# 1. Retrieval pass rates by set
def chart_retrieval():
    d = load("retrieval_results.json")
    by_kind = d.get("by_kind", {})
    labels, rates, counts, colors = [], [], [], []
    PALETTE = {"retrieval": "#2E7D32", "golden": "#1E88E5", "golden_expanded": "#FB8C00"}
    for kind in ["retrieval", "golden", "golden_expanded"]:
        if kind not in by_kind:
            continue
        b = by_kind[kind]
        r = b["passed"] / b["n"] if b["n"] else 0
        labels.append(kind)
        rates.append(r * 100)
        counts.append(f"{b['passed']}/{b['n']}")
        colors.append(PALETTE.get(kind, "#666666"))
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(labels, rates, color=colors, edgecolor="white")
    for bar, rate, c in zip(bars, rates, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{c} ({rate:.1f}%)", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylim(0, 110)
    ax.set_ylabel("Pass rate (%)")
    ax.set_title(f"Retrieval: expected pass rate by set\nOverall {d['passed']}/{d['n']} = {d['pass_rate']*100:.1f}% (n={d['n']})", fontsize=11, pad=12)
    fig.savefig_needed = False
    save(fig, "retrieval_by_set.png")


# 2. Generation stub checks
def chart_generation():
    d = load("generation_results.json")
    by_check = d["stub"]["by_check"]
    labels, rates, counts = [], [], []
    for check, v in by_check.items():
        r = v["passed"] / v["total"] * 100 if v["total"] else 0
        labels.append(check)
        rates.append(r)
        counts.append(f"{v['passed']}/{v['total']}")
    fig, ax = plt.subplots(figsize=(10, 4.5))
    bars = ax.bar(labels, rates, color="#5E35B1", edgecolor="white")
    for bar, rate, c in zip(bars, rates, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{c}\n{rate:.0f}%", ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, 115)
    ax.set_ylabel("Stub pass rate (%)")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_title(f"Generation (stub mode): pass rate by check axis\nStub {d['stub']['passed']}/{d['stub']['n']} overall", fontsize=11, pad=12)
    save(fig, "generation_checks.png")


# 3. Verifier catch rate
def chart_verifier():
    d = load("verifier_results.json")
    cats = ["Mutated caught", "Grounded held", "False fail", "False pass"]
    vals = [d["mutated_caught"], d["grounded_passed"], int(d["false_fail_rate"] * d["n"]), int(d["false_pass_rate"] * d["n"])]
    rates = [v / d["n"] * 100 for v in vals]
    colors = ["#2E7D32", "#1E88E5", "#E53935", "#FB8C00"]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(cats, rates, color=colors, edgecolor="white")
    for bar, v, r in zip(bars, vals, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{v}/{d['n']} ({r:.0f}%)", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylim(0, 115)
    ax.set_ylabel("Rate (%)")
    ax.set_title(f"Verifier (stub wiring): mutation catch rate\nCatch {d['mutated_caught']}/{d['n']} = {d['catch_rate']*100:.0f}%", fontsize=11, pad=12)
    save(fig, "verifier_catch.png")


# 4. E2E stub offline pass rate
def chart_e2e():
    d = load("e2e_stub_results.json")
    ext = d["extended_offline"]
    flows = d["persona_flows"]
    total_n, total_p = d["total"], d["passed"]
    blocks = [("Extended offline", ext["passed"], ext["n"]), ("Persona flows", flows["passed"], flows["n"]), ("Total", total_p, total_n)]
    labels = [b[0] for b in blocks]
    rates = [p / n * 100 for _, p, n in blocks]
    counts = [f"{p}/{n}" for _, p, n in blocks]
    colors = ["#1E88E5", "#FB8C00", "#2E7D32"]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(labels, rates, color=colors, edgecolor="white")
    for bar, rate, c in zip(bars, rates, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{c} ({rate:.1f}%)", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylim(0, 110)
    ax.set_ylabel("Pass rate (%)")
    ax.set_title("E2E (stub, offline): pass rate\nOffline only, no live LLM", fontsize=11, pad=12)
    save(fig, "e2e_stub.png")


if __name__ == "__main__":
    chart_retrieval()
    chart_generation()
    chart_verifier()
    chart_e2e()
