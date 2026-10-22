"""Which retrieval strategy actually finds the right section?

The question: the agent now runs a topic-scoped search alongside the plain
vector search. Should it instead use a hybrid of vector and keyword search?
The answer is a measurement, not an opinion.

Ground truth comes from the golden set: each entry names the section numbers
the answer must reach (`must_include_any`). The three out-of-scope entries
and the clarification entry are excluded, because the right answer for those
is no family-law section at all.

Scored three ways:
  top5  - a wanted section is among the first 5 passages (the budget the
          reasoner actually gets)
  pool  - a wanted section is anywhere in the 20 the search returned
  MRR   - mean reciprocal rank over the pool, misses counted as zero, which
          is the standard way to score a ranked list

Usage:  python3 scripts/retrieval_bench.py
"""
from __future__ import annotations

import math
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.getcwd(), "api"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.getcwd(), "api", ".env"))
from app import agent as A  # noqa: E402
from app.ingest import QdrantStore  # noqa: E402
from eval.golden_qas import GOLDEN_QAS  # noqa: E402

TOP_K = 5
POOL = 20

# The golden entries whose right answer is "no family-law section".
NOT_A_RETRIEVAL_QUESTION = {
    "oos-rti-en", "oos-landlord-en", "oos-motor-en", "clarify-personal-law-en",
}


def store():
    return QdrantStore.connect()


def section_number(hit) -> str:
    sec = str((hit.get("payload") or {}).get("section", "") or "")
    m = re.search(r"Section\s+(\d+[A-Z]?)", sec)
    return m.group(1) if m else ""


def act_of(hit) -> str:
    return str((hit.get("payload") or {}).get("act", "") or "")


# ---------------------------------------------------------------- strategies

def vec(st, query, act):
    q = "%s %s" % (query, act) if act else query
    return st.search_text(q, top_k=POOL)


def vec_plain(st, query, act):
    return st.search_text(query, top_k=POOL)


def topic_search(st, query, act, tag):
    if not tag:
        return []
    return st.search_text(query, top_k=POOL, filter_payload={"topic": tag})


def rrf(*lists, k=60):
    """Reciprocal rank fusion: each list votes, nothing is deleted."""
    scores, keep = {}, {}
    for lst in lists:
        for rank, hit in enumerate(lst):
            key = A._hit_key(hit)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            keep.setdefault(key, hit)
    return [keep[key] for key, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


_TOKEN = re.compile(r"[a-z0-9]+")


class BM25:
    """Plain BM25 over the corpus, held in memory.

    The collection is a few thousand chunks, so the whole thing fits in a dict
    and the scoring is a loop, not a service. That is the point of the
    comparison: a keyword search here costs nothing but memory.
    """

    def __init__(self, chunks, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = []
        self.df = Counter()
        for c in chunks:
            toks = _TOKEN.findall((c["text"] or "").lower())
            self.docs.append((c, toks, Counter(toks)))
            for t in set(toks):
                self.df[t] += 1
        self.n = len(self.docs)
        self.avg = sum(len(d[1]) for d in self.docs) / max(1, self.n)

    def search(self, query, k=POOL):
        q = _TOKEN.findall((query or "").lower())
        scored = []
        for idx, (chunk, toks, tf) in enumerate(self.docs):
            s = 0.0
            for t in q:
                f = tf.get(t)
                if not f:
                    continue
                idf = math.log(1 + (self.n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * (f * (self.k1 + 1)) / (
                    f + self.k1 * (1 - self.b + self.b * len(toks) / self.avg))
            if s > 0:
                scored.append((s, idx))
        scored.sort(reverse=True)
        return [{"payload": self.docs[i][0], "score": s} for s, i in scored[:k]]


# -------------------------------------------------------------------- score

def score(hits, want_secs):
    rank = None
    for i, h in enumerate(hits[:POOL]):
        num = section_number(h)
        if num and num in want_secs:
            rank = i
            break
    return {
        "top5": rank is not None and rank < TOP_K,
        "pool": rank is not None,
        "rr": 1.0 / (rank + 1) if rank is not None else 0.0,
    }


def main() -> None:
    st = store()
    print("scrolling the corpus for the keyword index…")
    points = st.scroll_all()
    chunks = [{"text": p.get("text", "") or "", "act": p.get("act", ""),
               "section": p.get("section", ""), "topic": p.get("topic", "")}
              for p in points]
    print("chunks: %d" % len(chunks))
    bm25 = BM25(chunks)

    def tag_for(topic, query):
        if topic == "marriage" and A._child_marriage_question(query):
            return "child_marriage"
        if A._dowry_question(query):
            return "dowry"
        return A._CORPUS_TOPIC_TAG.get(topic or "", "")

    def act_payload(st, query, acts):
        """The governing Act's own sections, fetched by payload filter.

        This is exact, not a similarity guess, so it cannot be outranked by a
        passage that merely looks similar.
        """
        out = []
        for corpus_act in acts[:2]:
            name = A._corpus_act_name(corpus_act)
            if not name:
                continue
            out.extend(st.search_text(query, top_k=POOL,
                                      filter_payload={"act": name}))
        return out

    strategies = {
        "vector only": lambda q, t, a, g: vec_plain(st, q, a),
        "RRF vec+actpayload": lambda q, t, a, g: rrf(
            vec(st, q, a), act_payload(st, q, A.acts_for_topic(t))),
        "RRF vec+topic+actpayload": lambda q, t, a, g: rrf(
            vec(st, q, a), topic_search(st, q, a, g),
            act_payload(st, q, A.acts_for_topic(t))),
        "vector + act anchor": lambda q, t, a, g: vec(st, q, a),
        "topic filter only": lambda q, t, a, g: topic_search(st, q, a, g),
        "CURRENT vector+topic hard": lambda q, t, a, g: (
            [h for h in topic_search(st, q, a, g)
             if A._hit_key(h) not in {A._hit_key(x) for x in vec_plain(st, q, a)}]
            + vec_plain(st, q, a)),
        "RRF vector+topic": lambda q, t, a, g: rrf(vec(st, q, a),
                                                   topic_search(st, q, a, g)),
        "RRF vector+keyword": lambda q, t, a, g: rrf(vec(st, q, a),
                                                     bm25.search(q)),
        "RRF all three": lambda q, t, a, g: rrf(vec(st, q, a),
                                                 topic_search(st, q, a, g),
                                                 bm25.search(q)),
        "RRF all + native": lambda q, t, a, g: rrf(
            vec(st, q, a), topic_search(st, q, a, g), bm25.search(q),
            vec_plain(st, q, a)),
    }

    entries = [g for g in GOLDEN_QAS if g["id"] not in NOT_A_RETRIEVAL_QUESTION]
    by_lang = {}
    results = {name: [] for name in strategies}
    for g in entries:
        q = g["query"]
        want_secs = set(str(x) for x in g.get("must_include_any", []))
        topic = A.extract_slots(q).get("topic", "")
        acts = A.acts_for_topic(topic)
        act = acts[0] if acts else ""
        tag = tag_for(topic, q)
        for name, fn in strategies.items():
            try:
                hits = fn(q, topic, act, tag)
            except Exception as exc:  # noqa: BLE001
                print("  %s failed on %s: %r" % (name, g["id"], exc))
                hits = []
            r = score(hits, want_secs)
            r["lang"] = g.get("lang", "en")
            r["id"] = g["id"]
            results[name].append(r)
            by_lang.setdefault(name, {}).setdefault(r["lang"], []).append(r)

    print("\n%d answerable golden questions (out of scope and clarify excluded)\n"
          % len(entries))
    print("%-28s %-9s %-9s %-8s" % ("strategy", "top5", "in pool", "MRR"))
    print("-" * 60)
    for name in strategies:
        rows = results[name]
        top5 = sum(1 for r in rows if r["top5"])
        pool = sum(1 for r in rows if r["pool"])
        mrr = sum(r["rr"] for r in rows) / max(1, len(rows))
        print("%-28s %-9s %-9s %-8s"
              % (name, "%d/%d" % (top5, len(rows)), "%d/%d" % (pool, len(rows)),
                 "%.3f" % mrr))

    print("\nby language (top5 hits):")
    langs = sorted({r["lang"] for r in results["RRF all three"]})
    print("%-28s %s" % ("strategy", "  ".join("%-8s" % l for l in langs)))
    for name in strategies:
        cells = []
        for l in langs:
            rows = by_lang[name].get(l, [])
            cells.append("%-8s" % ("%d/%d" % (sum(1 for r in rows if r["top5"]),
                                            len(rows))))
        print("%-28s %s" % (name, "  ".join(cells)))

    print("\nper question (Y = wanted section in the top 5, ~ = in the pool only):")
    names = list(strategies)
    for i, g in enumerate(entries):
        marks = []
        for name in names:
            r = results[name][i]
            marks.append("Y" if r["top5"] else ("~" if r["pool"] else "."))
        print("  %-28s %s   %s" % (g["id"], " ".join(marks),
                                   g["query"][:44]))
    print("\nlegend: %s" % "  ".join("%d=%s" % (i + 1, n[:12])
                                    for i, n in enumerate(names)))


if __name__ == "__main__":
    main()
