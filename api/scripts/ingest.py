"""T2 CLI: batch ingestion only (admin upload path is T13/T6).

Usage:
    .venv/bin/python api/scripts/ingest.py --text-dir data/marriageact --limit 200
    .venv/bin/python api/scripts/ingest.py --parquet /path/to/in_central_legislation.parquet
    .venv/bin/python api/scripts/ingest.py --pdf "data/HMA.pdf:Hindu Marriage Act, 1955"

Reads QDRANT_URL / QDRANT_API_KEY / QDRANT_COLLECTION / DATABASE_URL
from api/.env (embeddings run server-side via Qdrant Cloud Inference,
so no HF_TOKEN or local model needed). Idempotent: stable point IDs,
upsert + Neon bookkeeping.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app import db as db_module  # noqa: E402
from app.ingest import (  # noqa: E402
    DEFAULT_COLLECTION,
    QdrantStore,
    chunk_act,
    chunks_from_hf_row,
    chunks_from_pdf,
    chunks_from_text_dir,
    iter_open_india_law_rows,
    stable_point_id,
)
from app.models import IngestedChunk  # noqa: E402


def collect(args) -> list:
    chunks = []
    if args.text_dir:
        chunks.extend(chunks_from_text_dir(args.text_dir, lang=args.lang))
    if args.parquet or args.hf:
        rows = iter_open_india_law_rows(
            parquet_path=args.parquet,
            limit=args.limit,
        )
        for row in rows:
            chunks.extend(chunks_from_hf_row(row))
    for spec in args.pdf or []:
        # "path:Act Name" — act defaults to filename stem.
        if ":" in spec:
            pdf_path, act = spec.split(":", 1)
        else:
            pdf_path, act = spec, Path(spec).stem
        chunks.extend(chunks_from_pdf(pdf_path, act=act.strip()))
    for spec in args.url or []:
        # "url:Act Name" via Firecrawl (needs FIRECRAWL_API_KEY).
        if ":" in spec and "://" in spec:
            idx = spec.find(":", spec.find("://") + 3)
            url, act = (spec[:idx], spec[idx + 1:]) if idx != -1 else (spec, spec)
        elif ":" in spec:
            url, act = spec.split(":", 1)
        else:
            url, act = spec, spec
        from app.ingest import chunks_from_firecrawl_url
        chunks.extend(chunks_from_firecrawl_url(url.strip(), act=act.strip()))
    if args.demo:
        # Tiny offline corpus so the pipeline is runnable without downloads.
        chunks.extend(
            chunk_act(
                "Hindu Marriage Act, 1955",
                "Section 9 Restitution of conjugal rights. "
                "When either spouse withdraws from the society of the other, "
                "the court may decree restitution.\n"
                "Section 13 Divorce. Any marriage may be dissolved by decree "
                "of divorce on grounds including cruelty and desertion.",
                lang="en",
                source="demo",
            )
        )
    return chunks


def record_to_neon(session, point_ids, chunks, collection: str) -> int:
    n = 0
    for pid, c in zip(point_ids, chunks):
        row = session.query(IngestedChunk).filter_by(point_id=pid).first()
        if row is None:
            row = IngestedChunk(point_id=pid, act=c.act, section=c.section,
                                lang=c.lang, source=c.source,
                                collection=collection)
            session.add(row)
            n += 1
        else:
            row.act, row.section, row.lang = c.act, c.section, c.lang
            row.source, row.collection = c.source, collection
    session.commit()
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="LawSaathi T2 batch ingestion")
    ap.add_argument("--text-dir", default=None)
    ap.add_argument("--parquet", default=None)
    ap.add_argument("--hf", action="store_true",
                    help="stream vaquill/open-india-law from HF instead of local parquet")
    ap.add_argument("--pdf", action="append", default=[],
                    help='"path:Act Name", repeatable')
    ap.add_argument("--url", action="append", default=[],
                    help='"url:Act Name" via Firecrawl, repeatable')
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--demo", action="store_true",
                    help="ingest a tiny built-in corpus (no downloads)")
    ap.add_argument("--dry-run", action="store_true",
                    help="chunk + embed, skip Qdrant/Neon writes")
    args = ap.parse_args(argv)

    chunks = collect(args)
    print("chunks: %d" % len(chunks))
    if not chunks:
        print("nothing to ingest (no --demo/--text-dir/--parquet/--hf/--pdf?)")
        return 0

    # Stable IDs + payloads; vectors are embedded server-side by Qdrant
    # Cloud Inference (e5-small), so no local/API embedding step here.
    ids = [stable_point_id(c.act, c.section, c.chunk_index) for c in chunks]
    payloads = [c.payload() for c in chunks]

    if args.dry_run:
        print("dry-run: %d points built, not written" % len(ids))
        return 0

    store = QdrantStore.connect(collection=args.collection)
    store.ensure_collection()
    store.upsert_texts(ids, [c.text for c in chunks], payloads)
    print("upserted %d points -> collection %s (model %s)"
          % (len(ids), args.collection, store.model))

    engine = db_module.make_engine(db_module.database_url())
    db_module.init_db(engine)
    Session = db_module._Session
    assert Session is not None
    session = Session()
    try:
        n = record_to_neon(session, ids, chunks, args.collection)
    finally:
        session.close()
    print("neon: %d new ingested_chunks rows" % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
