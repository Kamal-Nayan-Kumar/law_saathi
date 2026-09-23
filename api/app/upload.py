"""T6: Document upload + ingestion + per-doc Q&A seam.

- PDF text extraction (pypdf lazy)
- Sliding chunk + section+page provenance
- Index into Qdrant / InMemoryVectorStore with doc_id filter
- Per-doc retrieval: query filtered by doc_id payload
"""
import hashlib
import os
import re
from typing import Dict, List, Optional
from uuid import uuid4

from app.ingest import Chunk, chunk_text, stable_point_id, InMemoryVectorStore, build_points


def extract_pdf_text(pdf_path: str) -> List[str]:
    """Return list of page texts from PDF (lazy import pypdf)."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf is required for PDF upload; pip install pypdf") from e
    reader = PdfReader(pdf_path)
    return [(page.extract_text() or "").strip() for page in reader.pages]


def chunk_pdf_document(
    pdf_path: str,
    doc_id: str = "",
    doc_title: str = "",
    lang: str = "en",
    max_chars: int = 1500,
    overlap: int = 200,
) -> List[Chunk]:
    """Chunk a PDF page-by-page; each chunk carries doc_id / page / section."""
    pages = extract_pdf_text(pdf_path)
    doc_id = doc_id or str(uuid4())
    doc_title = doc_title or os.path.basename(pdf_path)
    chunks: List[Chunk] = []
    for i, text in enumerate(pages, start=1):
        if not text:
            continue
        pieces = chunk_text(text, max_chars=max_chars, overlap=overlap)
        # Derive a simple section label from first line if it looks like a heading
        section = "Page %d" % i
        first_line = (text.splitlines()[0] if text else "").strip()
        if first_line and len(first_line) < 120:
            # If first line has numbered heading or "Section", use it
            if re.search(r"\b(section|sec\.|\d+\.)\b", first_line, re.I):
                section = first_line[:120]
        for idx, piece in enumerate(pieces):
            chunks.append(Chunk(
                text=piece,
                act="",
                section=section,
                lang=lang,
                source="upload:%s" % pdf_path,
                page=i,
                chunk_index=idx,
                total_chunks=len(pieces),
                uid="%s#%d#%d" % (pdf_path, i, idx),
                doc_id=doc_id,
                doc_title=doc_title,
            ))
    # Re-number chunk_index per section for stable IDs (same as chunk_act)
    per_section: Dict[str, int] = {}
    for c in chunks:
        i = per_section.get(c.section, 0)
        c.chunk_index = i
        per_section[c.section] = i + 1
    for c in chunks:
        c.total_chunks = per_section[c.section]
    return chunks


def index_document(
    chunks: List[Chunk],
    store,  # InMemoryVectorStore or QdrantStore
    embedder=None,
) -> int:
    """Upsert chunks into store; if embedder provided use it, else assume store handles embedding (Qdrant server-side)."""
    if hasattr(store, "upsert_texts"):
        # QdrantStore server-side embedding via REST
        ids = [stable_point_id(
            c.doc_id or c.act or "doc",
            c.section,
            c.chunk_index,
            c.uid or c.doc_id or "") for c in chunks]
        texts = [c.text for c in chunks]
        payloads = [c.payload() for c in chunks]
        return store.upsert_texts(ids, texts, payloads)
    # InMemoryVectorStore requires vectors
    if embedder is None:
        raise RuntimeError("embedder required for InMemoryVectorStore")
    vectors = embedder.encode_passages([c.text for c in chunks])
    ids, vecs, payloads = build_points(chunks, vectors)
    return store.upsert(ids, vecs, payloads)


class DocStore:
    """Thin wrapper around a vector store with per-doc filtering."""

    def __init__(self, backend=None, embedder=None):
        self.backend = backend or InMemoryVectorStore()
        self.embedder = embedder

    def index_pdf(self, pdf_path: str, doc_id: str = "", doc_title: str = "",
                  lang: str = "en") -> str:
        chunks = chunk_pdf_document(pdf_path, doc_id=doc_id,
                                    doc_title=doc_title, lang=lang)
        index_document(chunks, self.backend, self.embedder)
        return chunks[0].doc_id if chunks else (doc_id or "")

    def query_doc(self, doc_id: str, text: str, top_k: int = 5,
                  embedder=None):
        emb = embedder or self.embedder
        if emb is None:
            raise RuntimeError("embedder required for query")
        qvec = emb.encode_query(text) if hasattr(emb, "encode_query") else emb.encode(text)
        if hasattr(self.backend, "search"):
            # InMemoryVectorStore accepts filter_payload via search signature
            return self.backend.search(qvec, top_k=top_k,
                                       filter_payload={"doc_id": doc_id})
        # QdrantStore search_text
        return self.backend.search_text(text, top_k=top_k,
                                        filter_payload={"doc_id": doc_id})
