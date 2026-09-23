"""T2: RAG ingestion pipeline — acts -> section-aware chunks -> e5 -> Qdrant.

Design (per ADRs 0003/0004/0006):
- Embeddings: intfloat/multilingual-e5-small, via Hugging Face Inference API.
- Vectors: Qdrant Cloud (collection ``law_saathi`` by default).
- App data: Neon Postgres records Qdrant point IDs (see ``IngestedChunk``).
- Corpus: vaquill/open-india-law legislation filtered to family acts +
  enerscript/MARRIAGEACT + India Code PDFs as truth.

This module has NO hard third-party imports at import time so unit tests
run on a bare checkout (Python 3.9 compatible). Optional deps
(qdrant-client, datasets/pyarrow, pypdf, python-docx) are imported
lazily inside the functions that need them; embeddings and Firecrawl
go over HTTPS via httpx.
"""
import hashlib
import os
import re
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import NAMESPACE_URL, uuid5

EMBEDDING_DIM = 384
DEFAULT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "law_saathi")

# Canonical family acts (docs/stack.md). Aliases match substrings in
# open-india-law titles, which vary in punctuation/casing.
FAMILY_ACTS = [
    "Hindu Marriage Act, 1955",
    "Special Marriage Act, 1954",
    "Hindu Adoption and Maintenance Act, 1956",
    "Hindu Succession Act, 1956",
    "Guardians and Wards Act, 1890",
    "Protection of Women from Domestic Violence Act, 2005",
    "Indian Divorce Act, 1869",
]

_ACT_ALIASES = [
    ("hindu marriage", "Hindu Marriage Act, 1955"),
    ("special marriage", "Special Marriage Act, 1954"),
    ("hindu adoption", "Hindu Adoption and Maintenance Act, 1956"),
    ("hindu succession", "Hindu Succession Act, 1956"),
    ("guardians and wards", "Guardians and Wards Act, 1890"),
    ("domestic violence", "Protection of Women from Domestic Violence Act, 2005"),
    ("the divorce act", "Indian Divorce Act, 1869"),
]


def canonical_act(title: str) -> Optional[str]:
    """Map a raw dataset title to a canonical family act, or None."""
    low = (title or "").lower()
    for alias, canonical in _ACT_ALIASES:
        if alias in low:
            return canonical
    return None


def matching_act(row: Dict) -> Optional[str]:
    """Match a corpus row to a canonical family act.

    Title first; text-blob fallback only when the row has no usable title.
    This keeps out non-family acts that merely reference family law.
    Repealed rows are excluded (stale law must not be retrieved).
    """
    if str(row.get("act_status") or "").lower() == "repealed":
        return None
    title = str(row.get("title") or row.get("act") or row.get("name") or "")
    hit = canonical_act(title)
    if hit or title.strip():
        return hit
    blob = " ".join(str(row.get(k, "")) for k in row.keys())[:500]
    return canonical_act(blob)


@dataclass
class Chunk:
    text: str
    act: str = ""
    section: str = ""
    lang: str = "en"
    source: str = ""
    page: Optional[int] = None
    chunk_index: int = 0
    total_chunks: int = 1
    # Per-source discriminator (hf chunk_id, filename, pdf page): keeps IDs
    # unique when two rows map to the same act+section. Same inputs still
    # give the same ID, so re-runs stay idempotent.
    uid: str = ""
    # Per-document upload fields (T6)
    doc_id: str = ""
    doc_title: str = ""

    def payload(self) -> Dict:
        d = asdict(self)
        return d


# Section heading at line start. Bare acts use numbered headings
# ("9. Restitution of conjugal rights.- ..."); HF rows use "Section N".
# Bare "Sec." is deliberately NOT a heading: running text wraps leave
# "Sec. 15 ..." at line starts and splinter sections into junk.
_SECTION_RE = re.compile(
    r"(?m)^\s*(Section\s+\d+[A-Z\-]*|SECTION\s+\d+[A-Z\-]*"
    r"|\u0927\u093e\u0930\u093e\s+\d+"
    r"|\d{1,3}[A-Z]?\.(?=\s+[A-ZA-Z\u0900-\u097F]))"
)
_NUMBERED_RE = re.compile(r"^\s*(\d{1,3}[A-Z]?)\.\s+(.*)$")


def split_sections(text: str) -> List[Tuple[str, str]]:
    """Split act text into (section_title, body) pairs.

    Text before the first heading becomes ("Preamble", ...). If no heading
    matches, the whole text is one ("Full Text", ...) section.
    """
    text = (text or "").strip()
    if not text:
        return []
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return [("Full Text", text)]
    out: List[Tuple[str, str]] = []
    if matches[0].start() > 0:
        pre = text[: matches[0].start()].strip()
        if pre:
            out.append(("Preamble", pre))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[m.start(): end].strip()
        first_line = block.splitlines()[0].strip() if block else ""
        num = _NUMBERED_RE.match(first_line)
        if num:
            # Unify bare-act headings with HF style: "Section 9: ...".
            rest = num.group(2).strip()
            title = ("Section %s: %s" % (num.group(1), rest))[:120]
        else:
            title = first_line[:120]
        out.append((title, block))
    return out


def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> List[str]:
    """Sliding-window split on char budget with overlap. Keeps order."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: List[str] = []
    start = 0
    step = max_chars - overlap
    while start < len(text):
        end = min(start + max_chars, len(text))
        # Prefer a sentence/word boundary near the end.
        if end < len(text):
            cut = text.rfind(". ", start, end)
            if cut < start + max_chars // 2:
                cut = text.rfind(" ", start, end)
            if cut > start + max_chars // 2:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start += step
    return [c for c in chunks if c]


def chunk_act(
    act: str,
    full_text: str,
    lang: str = "en",
    source: str = "",
    page: Optional[int] = None,
    max_chars: int = 1500,
    overlap: int = 200,
    uid: str = "",
) -> List[Chunk]:
    """Section-aware chunking: never merge two sections into one chunk."""
    chunks: List[Chunk] = []
    for section_title, body in split_sections(full_text):
        for piece in chunk_text(body, max_chars=max_chars, overlap=overlap):
            chunks.append(
                Chunk(
                    text=piece,
                    act=act,
                    section=section_title,
                    lang=lang,
                    source=source,
                    page=page,
                    uid=("%s|%s" % (uid, section_title)) if uid else "",
                )
            )
    # Number chunks per section for stable provenance + IDs.
    per_section: Dict[str, int] = {}
    for c in chunks:
        i = per_section.get(c.section, 0)
        c.chunk_index = i
        per_section[c.section] = i + 1
    for c in chunks:
        c.total_chunks = per_section[c.section]
    return chunks


def stable_point_id(act: str, section: str, chunk_index: int,
                     salt: str = "") -> str:
    """Deterministic Qdrant point ID so re-runs are idempotent."""
    key = "%s|%s|%d|%s" % (act, section, chunk_index, salt or "")
    return str(uuid5(NAMESPACE_URL, key))


def legacy_hash_id(act: str, section: str, chunk_index: int) -> str:
    """Short sha256 hex variant (kept for debugging, not used as point ID)."""
    return hashlib.sha256(key_str(act, section, chunk_index).encode()).hexdigest()[:32]


def key_str(act: str, section: str, chunk_index: int) -> str:
    return "%s|%s|%d" % (act, section, chunk_index)


# ---------------------------------------------------------------------------
# Embeddings run server-side via Qdrant Cloud Inference (e5-small); the
# stores below are the only embedding path, so there is no local embedder.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Vector stores (Qdrant wrapper + in-memory fake with the same seam)
# ---------------------------------------------------------------------------


class InMemoryVectorStore:
    """Test double with the QdrantStore seam: upsert + cosine search."""

    def __init__(self) -> None:
        self._vectors: Dict[str, List[float]] = {}
        self._payloads: Dict[str, Dict] = {}

    def upsert(
        self,
        ids: Sequence[str],
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[Dict],
    ) -> int:
        for i, v, p in zip(ids, vectors, payloads):
            self._vectors[i] = list(map(float, v))
            self._payloads[i] = dict(p)
        return len(ids)

    def search(
        self, query_vector: Sequence[float], top_k: int = 5,
        filter_payload: Optional[Dict] = None
    ) -> List[Dict]:
        import math

        q = list(query_vector)
        qn = math.sqrt(sum(x * x for x in q)) or 1.0
        scored = []
        for pid, vec in self._vectors.items():
            p = self._payloads.get(pid) or {}
            if filter_payload:
                ok = all(p.get(k) == v for k, v in filter_payload.items())
                if not ok:
                    continue
            dot = sum(a * b for a, b in zip(q, vec))
            vn = math.sqrt(sum(x * x for x in vec)) or 1.0
            scored.append((dot / (qn * vn), pid))
        scored.sort(reverse=True)
        out = []
        for score, pid in scored[:top_k]:
            out.append({"id": pid, "score": score, "payload": self._payloads[pid]})
        return out

    def __len__(self) -> int:
        return len(self._vectors)


class QdrantStore:
    """Qdrant Cloud with server-side inference (no local embeddings).

    Upserts send raw text as ``Document`` objects and Qdrant embeds them
    with ``intfloat/multilingual-e5-small`` (free Cloud Inference model);
    queries do the same. Qdrant auto-applies the e5 ``passage:``/``query:``
    prefixes, so callers pass plain text.
    """

    MODEL = "intfloat/multilingual-e5-small"

    def __init__(self, client, collection: str = DEFAULT_COLLECTION,
                 model: str = MODEL, url: Optional[str] = None,
                 api_key: Optional[str] = None):
        self.client = client
        self.collection = collection
        self.model = model
        self._url = (url or os.environ.get("QDRANT_URL", "")).rstrip("/")
        self._api_key = api_key or os.environ.get("QDRANT_API_KEY", "")

    @classmethod
    def connect(
        cls, url: Optional[str] = None, api_key: Optional[str] = None,
        collection: Optional[str] = None, model: Optional[str] = None,
    ) -> "QdrantStore":
        from qdrant_client import QdrantClient

        url = url or os.environ.get("QDRANT_URL", "")
        api_key = api_key or os.environ.get("QDRANT_API_KEY", "")
        if not url:
            raise RuntimeError("QDRANT_URL is empty — add it to api/.env")
        # cloud_inference=True sends Document objects to the cluster for
        # server-side embedding instead of local FastEmbed runs.
        client = QdrantClient(url=url, api_key=api_key or None,
                              cloud_inference=True)
        return cls(client, collection or DEFAULT_COLLECTION,
                   model or cls.MODEL, url=url, api_key=api_key)

    def ensure_collection(self, dim: int = EMBEDDING_DIM) -> None:
        """Create the collection if missing (REST; SDK parses fail here)."""
        import httpx

        if not self._url:
            raise RuntimeError("QDRANT_URL is empty — add it to api/.env")
        headers = {"api-key": self._api_key, "Content-Type": "application/json"}
        resp = httpx.get("%s/collections/%s" % (self._url, self.collection),
                         headers=headers, timeout=30.0)
        if resp.status_code == 200:
            return
        if resp.status_code != 404:
            resp.raise_for_status()
        create = httpx.put(
            "%s/collections/%s" % (self._url, self.collection),
            headers=headers,
            json={"vectors": {"size": dim, "distance": "Cosine"}},
            timeout=60.0,
        )
        create.raise_for_status()

    def upsert_texts(self, ids, texts, payloads) -> int:
        """Upsert raw texts; Qdrant embeds them server-side (idempotent).

        Uses plain REST: qdrant-client 1.13.3 mis-parses the Cloud
        Inference usage block in SDK responses.
        """
        import httpx

        if not self._url:
            raise RuntimeError("QDRANT_URL is empty — add it to api/.env")
        points = [
            {"id": pid,
             "vector": {"text": text, "model": self.model},
             "payload": dict(pl)}
            for pid, text, pl in zip(ids, texts, payloads)
        ]
        resp = httpx.put(
            "%s/collections/%s/points?wait=true"
            % (self._url, self.collection),
            headers={"api-key": self._api_key,
                     "Content-Type": "application/json"},
            json={"points": points},
            timeout=120.0,
        )
        resp.raise_for_status()
        return len(points)

    def upsert(self, ids, vectors, payloads) -> int:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=pid, vector=list(vec), payload=dict(pl))
            for pid, vec, pl in zip(ids, vectors, payloads)
        ]
        self.client.upsert(collection_name=self.collection, points=points,
                           wait=True)
        return len(points)

    def search_text(self, text: str, top_k: int = 5,
                    filter_payload: Optional[Dict] = None) -> List[Dict]:
        """Search with raw text; Qdrant embeds the query server-side.

        Uses plain REST (not the SDK's query_points) because qdrant-client
        1.13.3 mis-parses the Cloud Inference usage block in responses.
        """
        import httpx

        if not self._url:
            raise RuntimeError("QDRANT_URL is empty — add it to api/.env")
        json_body = {"query": {"text": text, "model": self.model},
                     "limit": top_k, "with_payload": True}
        if filter_payload:
            json_body["filter"] = {"must": [
                {"key": k, "match": {"value": v}} for k, v in filter_payload.items()
            ]}
        resp = httpx.post(
            "%s/collections/%s/points/query"
            % (self._url, self.collection),
            headers={"api-key": self._api_key,
                     "Content-Type": "application/json"},
            json=json_body,
            timeout=60.0,
        )
        resp.raise_for_status()
        pts = resp.json().get("result", {}).get("points", [])
        return [{"id": str(p["id"]), "score": float(p["score"]),
                 "payload": dict(p.get("payload") or {})} for p in pts]

    def search(self, query_vector, top_k: int = 5) -> List[Dict]:
        # qdrant-client >=1.10 uses query_points; older uses search.
        try:
            res = self.client.query_points(
                collection_name=self.collection,
                query=list(query_vector),
                limit=top_k,
                with_payload=True,
            )
            pts = res.points
        except AttributeError:
            pts = self.client.search(
                collection_name=self.collection,
                query_vector=list(query_vector),
                limit=top_k,
                with_payload=True,
            )
        out = []
        for p in pts:
            pid = getattr(p, "id", None)
            out.append(
                {"id": str(pid), "score": float(getattr(p, "score", 0.0)),
                 "payload": dict(getattr(p, "payload", {}) or {})}
            )
        return out


def build_points(
    chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]
) -> Tuple[List[str], List[List[float]], List[Dict]]:
    ids = [stable_point_id(c.act, c.section, c.chunk_index, c.uid)
           for c in chunks]
    vecs = [list(map(float, v)) for v in vectors]
    payloads = [c.payload() for c in chunks]
    return ids, vecs, payloads


# ---------------------------------------------------------------------------
# Corpus loaders (lazy heavy deps; each yields Chunk lists)
# ---------------------------------------------------------------------------


def iter_open_india_law_rows(
    parquet_path: Optional[str] = None,
    hf_dataset: str = "vaquill/open-india-law",
    hf_file: str = "in_central_legislation.parquet",
    hf_token: Optional[str] = None,
    limit: Optional[int] = None,
) -> Iterable[Dict]:
    """Yield raw rows with act-relevant text, filtered to family acts.

    Prefers a local parquet file when given; otherwise streams the single
    needed file from Hugging Face (never the full 54GB dump). Requires
    ``datasets`` or ``pyarrow`` — imported lazily so unit tests skip it.
    """
    token = hf_token or os.environ.get("HF_TOKEN", "") or None
    if parquet_path:
        try:
            import pyarrow.parquet as pq
        except ImportError as e:
            raise RuntimeError("pyarrow is required to read a local parquet file") from e
        table = pq.read_table(parquet_path)
        cols = {n: table.column(n).to_pylist() for n in table.column_names}
        n = table.num_rows
        for i in range(n if limit is None else min(n, limit)):
            yield {k: v[i] for k, v in cols.items()}
        return
    try:
        from datasets import load_dataset
    except ImportError as e:
        raise RuntimeError(
            "datasets is required to stream vaquill/open-india-law; "
            "pip install datasets pyarrow"
        ) from e
    ds = load_dataset(hf_dataset, data_files=hf_file, split="train",
                      streaming=True, token=token)
    count = 0
    for row in ds:
        if matching_act(dict(row)) is None:
            continue
        yield row
        count += 1
        if limit is not None and count >= limit:
            break


def chunks_from_hf_row(row: Dict, source: str = "vaquill/open-india-law") -> List[Chunk]:
    title = str(row.get("title") or row.get("act") or row.get("name") or "Unknown Act")
    act = canonical_act(title) or title
    text = str(row.get("text") or row.get("content") or row.get("section_text") or "")
    if not text.strip():
        return []
    section = str(row.get("section") or row.get("section_no") or "")
    if not section and row.get("section_number") not in (None, ""):
        section = "Section %s" % row.get("section_number")
    lang = str(row.get("lang") or row.get("language")
               or row.get("language_code") or "en")
    page = row.get("page")
    try:
        page_int = int(page) if page is not None else None
    except (TypeError, ValueError):
        page_int = None
    src = source
    if row.get("source_url"):
        src = "%s | %s" % (source, row.get("source_url"))
    uid = str(row.get("chunk_id") or row.get("source_url") or "")
    if section:
        # Row already maps to one section: chunk within it only.
        pieces = chunk_text(text)
        out = [
            Chunk(text=p, act=act, section=section, lang=lang,
                  source=src, page=page_int, chunk_index=i,
                  total_chunks=len(pieces), uid=uid)
            for i, p in enumerate(pieces)
        ]
        return out
    return chunk_act(act, text, lang=lang, source=src, page=page_int, uid=uid)


def chunks_from_jsonl(path: str,
                      source: str = "vaquill/open-india-law") -> List[Chunk]:
    """Load rows saved by api/scripts/download_corpus.py.

    Each line is {"act": canonical-act, "row": {...raw columns...}}.
    """
    import json

    out: List[Chunk] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            row = dict(record.get("row", {}))
            if record.get("act") and not row.get("title"):
                row["title"] = record["act"]
            out.extend(chunks_from_hf_row(row, source=source))
    return out


def _read_text_file(path) -> str:
    """Read .txt/.md directly; .docx via python-docx (lazy)."""
    from pathlib import Path as _P

    p = _P(path)
    if p.suffix.lower() == ".docx":
        try:
            import docx
        except ImportError as e:
            raise RuntimeError(
                "python-docx is required for .docx files; pip install python-docx"
            ) from e
        doc = docx.Document(str(p))
        return "\n".join(par.text for par in doc.paragraphs)
    return p.read_text(encoding="utf-8", errors="ignore")


def chunks_from_text_dir(
    directory: str, lang: str = "en", source: str = "enerscript/MARRIAGEACT"
) -> List[Chunk]:
    """Load local text files (.txt/.md/.docx); filename stem -> act guess."""
    from pathlib import Path

    out: List[Chunk] = []
    paths = sorted(Path(directory).glob("*.txt")) + \
        sorted(Path(directory).glob("*.md")) + \
        sorted(Path(directory).glob("*.docx"))
    for path in paths:
        raw_title = path.stem.replace("_", " ").replace("-", " ")
        act = canonical_act(raw_title) or raw_title
        out.extend(chunk_act(act, _read_text_file(path),
                             lang=lang, source="%s:%s" % (source, path.name),
                             uid=path.name))
    return out


def chunks_from_firecrawl_url(
    url: str, act: str, lang: str = "en", api_key: Optional[str] = None,
    source: str = "firecrawl",
) -> List[Chunk]:
    """Scrape an act page (e.g. India Code) to markdown via Firecrawl.

    Used for URL-based corpus sources; local uploads stay on local parsers
    (free, offline). Requires FIRECRAWL_API_KEY.
    """
    import httpx

    key = api_key or os.environ.get("FIRECRAWL_API_KEY", "")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY is empty — add it to api/.env")
    resp = httpx.post(
        "https://api.firecrawl.dev/v1/scrape",
        headers={"Authorization": "Bearer " + key},
        json={"url": url, "formats": ["markdown"]},
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    markdown = data.get("markdown", "") or ""
    if not markdown.strip():
        raise RuntimeError("Firecrawl returned empty markdown for %s" % url)
    return chunk_act(act, markdown, lang=lang,
                     source="%s:%s" % (source, url))


def chunks_from_pdf(
    pdf_path: str, act: str, lang: str = "en", source: str = "india-code"
) -> List[Chunk]:
    """India Code PDF as truth: one chunk pass per page, section-aware."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf is required to read India Code PDFs") from e
    reader = PdfReader(pdf_path)
    out: List[Chunk] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        out.extend(chunk_act(act, text, lang=lang,
                             source="%s:%s" % (source, pdf_path),
                             page=i, uid="%s#%d" % (pdf_path, i)))
    return out
