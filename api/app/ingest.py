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

EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
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
    ("indian divorce", "Indian Divorce Act, 1869"),
]


def canonical_act(title: str) -> Optional[str]:
    """Map a raw dataset title to a canonical family act, or None."""
    low = (title or "").lower()
    for alias, canonical in _ACT_ALIASES:
        if alias in low:
            return canonical
    return None


@dataclass
class Chunk:
    text: str
    act: str
    section: str
    lang: str = "en"
    source: str = ""
    page: Optional[int] = None
    chunk_index: int = 0
    total_chunks: int = 1

    def payload(self) -> Dict:
        d = asdict(self)
        return d


# Section heading at line start: "Section 9 ...", "SECTION 13-B ...",
# Hindi "धारा 9 ...". Keep the heading line with the body that follows.
_SECTION_RE = re.compile(
    r"(?m)^\s*(Section\s+\d+[A-Z\-]*|SECTION\s+\d+[A-Z\-]*"
    r"|Sec\.\s*\d+[A-Z\-]*|\u0927\u093e\u0930\u093e\s+\d+)"
)


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


def stable_point_id(act: str, section: str, chunk_index: int) -> str:
    """Deterministic Qdrant point ID so re-runs are idempotent."""
    key = "%s|%s|%d" % (act, section, chunk_index)
    return str(uuid5(NAMESPACE_URL, key))


def legacy_hash_id(act: str, section: str, chunk_index: int) -> str:
    """Short sha256 hex variant (kept for debugging, not used as point ID)."""
    return hashlib.sha256(key_str(act, section, chunk_index).encode()).hexdigest()[:32]


def key_str(act: str, section: str, chunk_index: int) -> str:
    return "%s|%s|%d" % (act, section, chunk_index)


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


class E5Embedder:
    """intfloat/multilingual-e5-small via Hugging Face Inference API.

    No local model runs: vectors come from the hosted HF endpoint, so this
    works on machines that cannot run Sentence Transformers + torch.
    Needs HF_TOKEN in api/.env. e5 convention is kept: passages are
    prefixed with "passage: ", queries with "query: ".
    """

    ENDPOINT = (
        "https://router.huggingface.co/hf-inference"
        "/models/intfloat/multilingual-e5-small"
    )

    def __init__(self, model_name: str = EMBEDDING_MODEL,
                 token: Optional[str] = None):
        self.model_name = model_name
        self._token = token

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM

    def _headers(self) -> Dict[str, str]:
        token = self._token or os.environ.get("HF_TOKEN", "")
        if not token:
            raise RuntimeError("HF_TOKEN is empty — add it to api/.env")
        return {"Authorization": "Bearer " + token}

    def _post(self, texts: Sequence[str]) -> List[List[float]]:
        import httpx

        resp = httpx.post(
            self.ENDPOINT,
            headers=self._headers(),
            json={"inputs": list(texts)},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError("HF inference error: %s" % data["error"])
        # Feature-extraction returns one vector per input.
        return [[float(x) for x in vec] for vec in data]

    def encode_passages(self, texts: Sequence[str]) -> List[List[float]]:
        return self._post(["passage: " + t for t in texts])

    def encode_query(self, text: str) -> List[float]:
        return self._post(["query: " + text])[0]


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
        self, query_vector: Sequence[float], top_k: int = 5
    ) -> List[Dict]:
        import math

        q = list(query_vector)
        qn = math.sqrt(sum(x * x for x in q)) or 1.0
        scored = []
        for pid, vec in self._vectors.items():
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
    """Thin wrapper over qdrant-client; created via ``connect()``."""

    def __init__(self, client, collection: str = DEFAULT_COLLECTION):
        self.client = client
        self.collection = collection

    @classmethod
    def connect(
        cls, url: Optional[str] = None, api_key: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> "QdrantStore":
        from qdrant_client import QdrantClient

        url = url or os.environ.get("QDRANT_URL", "")
        api_key = api_key or os.environ.get("QDRANT_API_KEY", "")
        if not url:
            raise RuntimeError("QDRANT_URL is empty — add it to api/.env")
        client = QdrantClient(url=url, api_key=api_key or None)
        return cls(client, collection or DEFAULT_COLLECTION)

    def ensure_collection(self, dim: int = EMBEDDING_DIM) -> None:
        from qdrant_client.models import Distance, VectorParams

        try:
            self.client.get_collection(self.collection)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, ids, vectors, payloads) -> int:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=pid, vector=list(vec), payload=dict(pl))
            for pid, vec, pl in zip(ids, vectors, payloads)
        ]
        self.client.upsert(collection_name=self.collection, points=points)
        return len(points)

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
    ids = [stable_point_id(c.act, c.section, c.chunk_index) for c in chunks]
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
        title = str(row.get("title") or row.get("act") or row.get("name") or "")
        if canonical_act(title) is None:
            # Some rows carry the act name in a text column instead.
            blob = " ".join(str(row.get(k, "")) for k in row.keys())[:500]
            if canonical_act(blob) is None:
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
    lang = str(row.get("lang") or row.get("language") or "en")
    page = row.get("page")
    try:
        page_int = int(page) if page is not None else None
    except (TypeError, ValueError):
        page_int = None
    if section:
        # Row already maps to one section: chunk within it only.
        pieces = chunk_text(text)
        out = [
            Chunk(text=p, act=act, section=section, lang=lang,
                  source=source, page=page_int, chunk_index=i,
                  total_chunks=len(pieces))
            for i, p in enumerate(pieces)
        ]
        return out
    return chunk_act(act, text, lang=lang, source=source, page=page_int)


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
                             lang=lang, source="%s:%s" % (source, path.name)))
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
                             page=i))
    return out
