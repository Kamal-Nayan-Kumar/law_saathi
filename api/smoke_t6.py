"""T6 smoke QA: upload PDF chunk -> doc store -> per-doc Q&A -> doc citation."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.upload import chunk_pdf_document, DocStore
from app.agent import _evidence_source_type, format_citation, compose_answer, new_state
from app.ingest import InMemoryVectorStore

def smoke():
    pdf_path = "/tmp/test_doc.pdf"
    # 1. Extract + chunk
    chunks = chunk_pdf_document(pdf_path, doc_id="t6-doc-1", doc_title="Test Judgment")
    assert chunks, "no chunks from PDF"
    assert chunks[0].doc_id == "t6-doc-1"
    assert chunks[0].doc_title == "Test Judgment"
    print("Chunk OK:", len(chunks), "chunks; doc_id=", chunks[0].doc_id)

    # 2. Index into in-memory doc store
    class SimpleEmb:
        def encode_passages(self, texts):
            return [[1.0 if "custody" in t.lower() else 0.5] * 4 for t in texts]
        def encode_query(self, text):
            return [1.0 if "custody" in text.lower() else 0.5] * 4
    store = InMemoryVectorStore()
    ds = DocStore(backend=store, embedder=SimpleEmb())
    ds.index_pdf(pdf_path, doc_id="t6-doc-1", doc_title="Test Judgment")
    print("Index OK; store size:", len(store))

    # 3. Per-doc query (with filter)
    hits = ds.query_doc("t6-doc-1", "custody rights", top_k=3, embedder=SimpleEmb())
    assert hits, "per-doc query returned empty"
    assert all(h["payload"].get("doc_id") == "t6-doc-1" for h in hits), "filter missed doc"
    print("Per-doc retrieve OK; hits=", len(hits))

    # 4. Citation grouping
    payload = hits[0]["payload"]
    assert _evidence_source_type({"payload": payload}) == "doc", "expected doc source"
    cit = format_citation(payload)
    assert "Test Judgment" in cit or "doc" in cit, "citation missing doc ref: %s" % cit
    print("Citation OK:", cit)

    # 5. Compose answer with doc evidence
    state = new_state("What does this say about custody?")
    state["evidence"] = hits[:2]
    state["doc_id"] = "t6-doc-1"
    answer, citations, sources = compose_answer(state)
    assert "doc" in sources, "missing doc in citation_sources"
    assert any("Test Judgment" in c or "doc" in c for c in citations), "doc citation missing"
    print("Compose OK; sources:", sources[:2])
    print("T6 SMOKE PASS")

if __name__ == "__main__":
    smoke()
