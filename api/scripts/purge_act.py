"""Purge an Act's chunks from Qdrant + Neon bookkeeping.

Usage:
    .venv/bin/python api/scripts/purge_act.py --act "The Prohibition of Child Marriage (Amendment) Bill, 2021"
    .venv/bin/python api/scripts/purge_act.py --act "..." --dry-run

Needed because ingestion can only refuse what arrives *next*: material that
was already indexed stays there until it is deleted. The Bill guard stops the
loaders, not the index.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import httpx  # noqa: E402

from app import db as db_module  # noqa: E402
from app.ingest import QdrantStore  # noqa: E402
from app.models import IngestedChunk  # noqa: E402


def scroll_ids(store: QdrantStore, act: str) -> list:
    """Every point id in the collection whose payload act == act."""
    out = []
    offset = None
    headers = {"api-key": store._api_key, "Content-Type": "application/json"}
    while True:
        body = {
            "filter": {"must": [{"key": "act", "match": {"value": act}}]},
            "limit": 100,
            "with_payload": False,
            "with_vector": False,
        }
        if offset is not None:
            body["offset"] = offset
        resp = httpx.post(
            "%s/collections/%s/points/scroll"
            % (store._url, store.collection), headers=headers,
            json=body, timeout=30.0,
        )
        resp.raise_for_status()
        res = resp.json().get("result", {})
        out.extend(p["id"] for p in res.get("points", []))
        offset = res.get("next_page_offset")
        if not offset:
            return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Remove an Act from the index")
    ap.add_argument("--act", required=True)
    ap.add_argument("--collection", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    store = QdrantStore.connect(collection=args.collection)
    ids = scroll_ids(store, args.act)
    print("qdrant: %d points for %r in %s"
          % (len(ids), args.act, store.collection))
    if not ids:
        print("nothing to purge")
        return 0
    if args.dry_run:
        print("dry-run: not deleted")
        return 0

    headers = {"api-key": store._api_key, "Content-Type": "application/json"}
    resp = httpx.post(
        "%s/collections/%s/points/delete?wait=true"
        % (store._url, store.collection),
        headers=headers,
        json={"points": ids},
        timeout=60.0,
    )
    resp.raise_for_status()
    print("qdrant: deleted %d" % len(ids))

    engine = db_module.make_engine(db_module.database_url())
    db_module.init_db(engine)
    Session = db_module._Session
    assert Session is not None
    session = Session()
    try:
        n = (session.query(IngestedChunk)
             .filter(IngestedChunk.act == args.act).delete())
        session.commit()
    finally:
        session.close()
    print("neon: deleted %d ingested_chunks rows" % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
