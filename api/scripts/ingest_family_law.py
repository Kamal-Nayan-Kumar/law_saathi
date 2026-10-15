"""Build the LawSaathi vector index from vaquill/open-india-law.

Downloads ``in_central_legislation.parquet`` (26 MB — never the 54 GB dump),
keeps only the Acts in :mod:`app.family_law_acts`, and upserts section-aware
chunks into Qdrant.

Embeddings run server-side via **Qdrant Cloud Inference** with
``intfloat/multilingual-e5-small`` — there is no local embedder and no HF
inference call. The chunk text *and* its metadata live in the Qdrant payload,
so there is no parallel Neon bookkeeping table to keep in sync.

Usage:
    .venv/bin/python api/scripts/ingest_family_law.py --dry-run
    .venv/bin/python api/scripts/ingest_family_law.py
    .venv/bin/python api/scripts/ingest_family_law.py --recreate
    .venv/bin/python api/scripts/ingest_family_law.py --parquet /path/to.parquet

Idempotent: point IDs derive from act + section + chunk index + source
chunk_id, so a re-run overwrites the same points in place.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app import family_law_acts as fla  # noqa: E402
from app.ingest import DEFAULT_COLLECTION, QdrantStore, chunk_text, stable_point_id  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET = REPO / "data" / "corpus" / "in_central_legislation.parquet"
# Hand-authored corrections no dataset carries (see corpus/README.md). Kept out
# of the dataset path on purpose: they are editorial, not scraped.
DEFAULT_AMENDMENTS = REPO / "corpus" / "amendments.jsonl"
HF_URL = ("https://huggingface.co/datasets/vaquill/open-india-law/"
          "resolve/main/in_central_legislation.parquet")

# Columns the payload needs. Reading only these keeps memory flat.
NEEDED_COLS = [
    "act_id", "chunk_id", "title", "chapter", "section_number",
    "section_title", "text", "jurisdiction", "act_status", "in_force",
    "year", "source_url", "language_code", "legal_subject", "section_type",
]

SECTION_TYPE_LABELS = {
    "preamble": "Preamble",
    "short_title": "Short title",
    "definitions": "Definitions",
    "schedule": "Schedule",
    "amendment_provision": "Amendment provision",
}

PAYLOAD_INDEXES = [
    {"field_name": "act"},
    {"field_name": "category_key"},
    {"field_name": "topic"},
    {"field_name": "section_number"},
    {"field_name": "kind"},
    {"field_name": "act_status"},
    {"field_name": "lang"},
    {"field_name": "in_force", "field_schema": {"type": "bool"}},
    {"field_name": "year", "field_schema": {"type": "integer"}},
]

MAX_CHARS = 1500
OVERLAP = 200


def download_parquet(dest: Path) -> Path:
    """Fetch the one needed parquet file from HF (token from api/.env)."""
    import httpx

    token = os.environ.get("HF_TOKEN", "")
    if not token:
        raise RuntimeError("HF_TOKEN is empty — add it to api/.env")
    dest.parent.mkdir(parents=True, exist_ok=True)
    print("downloading %s\n         -> %s" % (HF_URL, dest))
    with httpx.stream("GET", HF_URL,
                      headers={"Authorization": "Bearer " + token},
                      follow_redirects=True, timeout=300.0) as resp:
        resp.raise_for_status()
        with dest.open("wb") as f:
            for block in resp.iter_bytes(chunk_size=1 << 20):
                f.write(block)
    print("downloaded %.1f MB" % (dest.stat().st_size / 1e6))
    return dest


def read_rows(parquet: Path):
    import pyarrow.parquet as pq

    table = pq.read_table(parquet, columns=NEEDED_COLS)
    return {name: table.column(name).to_pylist() for name in NEEDED_COLS}, table.num_rows


def section_label(section_number, section_type: str) -> str:
    num = str(section_number or "").strip()
    if num:
        return "Section %s" % num
    return SECTION_TYPE_LABELS.get((section_type or "").strip().lower(), "")


def build_payload(row: dict, entry: fla.ActEntry, text: str, section: str,
                  chunk_index: int, total: int) -> dict:
    """The complete, self-describing payload for one chunk.

    Everything needed to (a) filter by Act / category / topic / status and
    (b) render a citation with a source link lives here, so Qdrant is the
    whole index — text included.
    """
    try:
        year = int(row.get("year")) if row.get("year") is not None else None
    except (TypeError, ValueError):
        year = None
    in_force = bool(row.get("in_force"))
    return {
        "text": text,
        "act": entry.act,
        "act_title": str(row.get("title") or entry.dataset_title),
        "act_id": str(row.get("act_id") or ""),
        "category": entry.category,
        "category_key": entry.category_key,
        "topic": entry.topic,
        "section": section,
        "section_number": str(row.get("section_number") or ""),
        "section_type": str(row.get("section_type") or ""),
        "chapter": str(row.get("chapter") or ""),
        "source": "vaquill/open-india-law",
        "source_url": str(row.get("source_url") or ""),
        "act_status": str(row.get("act_status") or ""),
        "in_force": in_force,
        "year": year,
        "lang": str(row.get("language_code") or "en"),
        "kind": "repealed_statute" if entry.repealed else "statute",
        "chunk_index": chunk_index,
        "total_chunks": total,
        "chunk_id": str(row.get("chunk_id") or ""),
        "legal_subject": str(row.get("legal_subject") or ""),
    }


def collect(rows: dict, mapping: dict):
    """Filter to the registry and chunk. Returns (ids, texts, payloads, stats)."""
    ids, texts, payloads = [], [], []
    per_act: Counter = Counter()
    per_cat: Counter = Counter()
    titles = rows["title"]
    for i, title in enumerate(titles):
        entry = mapping.get(title)
        if entry is None:
            continue
        row = {k: rows[k][i] for k in NEEDED_COLS}
        raw = str(row.get("text") or "").strip()
        if not raw:
            continue
        section = section_label(row.get("section_number"), row.get("section_type"))
        pieces = chunk_text(raw, max_chars=MAX_CHARS, overlap=OVERLAP)
        for ci, piece in enumerate(pieces):
            pid = stable_point_id(entry.act, section, ci,
                                  str(row.get("chunk_id") or ""))
            ids.append(pid)
            texts.append(piece)
            payloads.append(build_payload(row, entry, piece, section, ci,
                                          len(pieces)))
        per_act[entry.act] += len(pieces)
        per_cat[entry.category] += len(pieces)
    return ids, texts, payloads, per_act, per_cat


def load_amendments(path: Path):
    """Load the curated ``kind: amendment_notice`` chunks.

    These answer the mutual-consent-divorce timing question that the dataset
    cannot: every consolidated corpus still prints the pre-2018 text. They are
    fetched by payload filter (``kind == amendment_notice``), not by
    similarity, so they must be in the index or the agent's amendment guard
    finds nothing.
    """
    ids, texts, payloads = [], [], []
    if not path.exists():
        return ids, texts, payloads
    by_act = {e.act: e for e in fla.ACTS}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        row = dict(record.get("row") or {})
        act = str(record.get("act") or row.get("act") or "").strip()
        text = str(row.get("text") or "").strip()
        if not act or not text:
            continue
        section = str(row.get("section") or "")
        entry = by_act.get(act)
        payload = {
            "text": text,
            "act": act,
            "act_title": str(row.get("title") or act),
            "act_id": "",
            "category": entry.category if entry else "",
            "category_key": entry.category_key if entry else "",
            "topic": entry.topic if entry else "",
            "section": section,
            "section_number": "",
            "section_type": "amendment_notice",
            "chapter": "",
            "source": "corpus/amendments.jsonl",
            "source_url": str(row.get("source_url") or ""),
            "act_status": "amendment",
            "in_force": True,
            "year": None,
            "lang": str(row.get("lang") or "en"),
            "kind": "amendment_notice",
            "chunk_index": 0,
            "total_chunks": 1,
            "chunk_id": str(row.get("chunk_id") or ""),
            "legal_subject": "",
        }
        ids.append(stable_point_id(act, section, 0,
                                   str(row.get("chunk_id") or "")))
        texts.append(text)
        payloads.append(payload)
    return ids, texts, payloads


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the LawSaathi family-law index")
    ap.add_argument("--parquet", default=str(DEFAULT_PARQUET))
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--no-download", action="store_true",
                    help="fail instead of downloading a missing parquet")
    ap.add_argument("--recreate", action="store_true",
                    help="delete every point in the collection first")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse + chunk + report, write nothing")
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--amendments", default=str(DEFAULT_AMENDMENTS),
                    help="curated amendment notices (corpus/amendments.jsonl)")
    ap.add_argument("--no-amendments", action="store_true",
                    help="skip the curated amendment notices")
    args = ap.parse_args(argv)

    parquet = Path(args.parquet)
    if not parquet.exists():
        if args.no_download:
            print("missing parquet: %s" % parquet)
            return 1
        download_parquet(parquet)

    rows, n_rows = read_rows(parquet)
    print("dataset rows: %d" % n_rows)

    mapping = fla.resolve_dataset_titles(rows["title"])
    resolved_acts = {e.act for e in mapping.values()}
    missing = [e.act for e in fla.ACTS if e.act not in resolved_acts]
    print("registry acts matched: %d/%d" % (len(resolved_acts), len(fla.ACTS)))
    if missing:
        print("  NOT FOUND in dataset:")
        for m in missing:
            print("    - %s" % m)

    ids, texts, payloads, per_act, per_cat = collect(rows, mapping)
    n_statute = len(ids)
    if not args.no_amendments:
        a_ids, a_texts, a_payloads = load_amendments(Path(args.amendments))
        ids += a_ids
        texts += a_texts
        payloads += a_payloads
        print("\namendment notices: %d" % len(a_ids))
    print("\nchunks built: %d (%d statute + %d amendment notice)"
          % (len(ids), n_statute, len(ids) - n_statute))
    print("\n=== chunks per category ===")
    for cat, n in per_cat.most_common():
        print("  %5d  %s" % (n, cat))
    print("\n=== chunks per act ===")
    for act, n in per_act.most_common():
        print("  %5d  %s" % (n, act))

    if args.dry_run:
        print("\ndry-run: nothing written")
        return 0

    store = QdrantStore.connect(collection=args.collection)
    if args.recreate:
        before = store.count()
        store.delete_all_points()
        print("\nrecreate: deleted %d existing points" % before)
    store.ensure_collection()
    store.ensure_payload_indexes(PAYLOAD_INDEXES)
    print("payload indexes: %s"
          % ", ".join(s["field_name"] for s in PAYLOAD_INDEXES))

    written = store.upsert_texts_batched(ids, texts, payloads,
                                         batch_size=args.batch_size)
    print("\nupserted %d points (embedding model %s)" % (written, store.model))
    print("collection %s now holds %d points" % (args.collection, store.count()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
