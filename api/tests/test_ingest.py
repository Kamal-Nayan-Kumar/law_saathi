"""T2 tests: section-aware chunker + provenance + EN/HI/KN retrieval seam."""
import math

from app.ingest import (
    InMemoryVectorStore,
    build_points,
    canonical_act,
    chunk_act,
    chunk_text,
    chunks_from_hf_row,
    split_sections,
    stable_point_id,
)

HMA9 = (
    "Section 9 Restitution of conjugal rights. When either spouse withdraws "
    "from the society of the other without reasonable excuse, the court may "
    "decree restitution of conjugal rights."
)
HMA13 = (
    "Section 13 Divorce. Any marriage solemnized under this Act may be "
    "dissolved by a decree of divorce on grounds including cruelty, "
    "desertion and adultery."
)
DV12 = (
    "Section 12 Application for protection order. An aggrieved person may "
    "seek protection orders against domestic violence, including residence "
    "and monetary relief."
)


class ConceptEmbedder:
    """Test double: shared dims across EN/HI/KN synonyms.

    A real e5 model maps translations to nearby vectors; this stub maps the
    small fixture vocabulary to the same dims so the retrieval *seam*
    (chunk -> embed -> upsert -> search -> provenance) is tested without
    downloading 100MB+ weights. Live e5+Qdrant quality is verified by the
    CLI dry-run / integration path, not here.
    """

    CONCEPTS = [
        {"divorce", "talak", "तलाक", "ವಿಚ್ಛೇದನ", "cruelty", "desertion", "क्रूरता"},
        {"conjugal", "restitution", "वैवाहिक", "प्रत्यास्थापन", "ದಾಂಪತ್ಯ"},
        {"protection", "domestic violence", "संरक्षण", "घरेलू हिंसा", "ರಕ್ಷಣೆ",
         "ಕೌಟುಂಬಿಕ ಹಿಂಸೆ"},
        {"maintenance", "भरण", "ಪೋಷಣೆ", "adoption", "गोद"},
        {"succession", "inheritance", "उत्तराधिकार", "ಉತ್ತರಾಧಿಕಾರ"},
    ]

    def encode(self, text: str):
        low = text.lower()
        return [1.0 if any(k in low for k in concept) else 0.0
                for concept in self.CONCEPTS]

    def encode_passages(self, texts):
        return [self.encode(t) for t in texts]

    def encode_query(self, text):
        return self.encode(text)


def _fixture_chunks():
    return [
        chunk_act("Hindu Marriage Act, 1955", HMA9, lang="en",
                  source="test")[0],
        chunk_act("Hindu Marriage Act, 1955", HMA13, lang="en",
                  source="test")[0],
        chunk_act("Hindu Marriage Act, 1955",
                  "धारा 13 तलाक। क्रूरता और परित्याग के आधार पर विवाह "
                  "विच्छेद किया जा सकता है।",
                  lang="hi", source="test")[0],
        chunk_act("Hindu Marriage Act, 1955",
                  "ಸೆಕ್ಷನ್ 13 ವಿಚ್ಛೇದನ. ಕ್ರೌರ್ಯ ಮತ್ತು ಪರಿತ್ಯಾಗದ ಆಧಾರದ ಮೇಲೆ "
                  "ವಿವಾಹವನ್ನು ವಿಸರ್ಜಿಸಬಹುದು. Section 13 Divorce.",
                  lang="kn", source="test")[0],
        chunk_act("Protection of Women from Domestic Violence Act, 2005",
                  DV12, lang="en", source="test")[0],
        chunk_act("Protection of Women from Domestic Violence Act, 2005",
                  "धारा 12 संरक्षण आदेश। घरेलू हिंसा से पीड़ित व्यक्ति "
                  "संरक्षण आदेश मांग सकता है।",
                  lang="hi", source="test")[0],
    ]


def _store_with_fixture():
    chunks = _fixture_chunks()
    emb = ConceptEmbedder()
    vectors = emb.encode_passages([c.text for c in chunks])
    ids, vecs, payloads = build_points(chunks, vectors)
    store = InMemoryVectorStore()
    store.upsert(ids, vecs, payloads)
    return store, emb


# --- chunker unit tests ---


def test_split_sections_keeps_boundaries():
    text = "Intro line.\nSection 9 Foo bar.\nBody nine.\nSection 13 Baz.\nBody thirteen."
    parts = split_sections(text)
    titles = [t for t, _ in parts]
    assert any("Preamble" in t for t in titles)
    assert any("Section 9" in t for t in titles)
    assert any("Section 13" in t for t in titles)
    # Bodies must not leak across sections.
    bodies = dict(parts)
    sec9 = [b for t, b in parts if "Section 9" in t][0]
    assert "thirteen" not in sec9.lower()


def test_split_sections_no_headings():
    parts = split_sections("Just some preamble text.")
    assert parts == [("Full Text", "Just some preamble text.")]


def test_chunk_act_never_merges_sections():
    chunks = chunk_act("Hindu Marriage Act, 1955",
                       "Section 9 AAA.\n" + ("x " * 800) + "\nSection 13 BBB.",
                       max_chars=500, overlap=50)
    sections = {c.section for c in chunks}
    assert any("Section 9" in s for s in sections)
    assert any("Section 13" in s for s in sections)
    for c in chunks:
        assert not ("Section 9" in c.text and "Section 13" in c.text)


def test_chunk_text_overlap_and_order():
    pieces = chunk_text("word " * 600, max_chars=500, overlap=100)
    assert len(pieces) > 1
    assert pieces[0].startswith("word")
    # Overlap: last words of piece 0 reappear in piece 1.
    assert set(pieces[0].split()[-5:]) & set(pieces[1].split()[:50])


def test_payload_carries_provenance():
    chunks = chunk_act("Hindu Marriage Act, 1955", HMA9, lang="en",
                       source="india-code:HMA.pdf", page=7)
    p = chunks[0].payload()
    assert p["act"] == "Hindu Marriage Act, 1955"
    assert "Section 9" in p["section"]
    assert p["page"] == 7
    assert p["lang"] == "en"
    assert p["source"] == "india-code:HMA.pdf"


def test_stable_point_id_idempotent_and_unique():
    a = stable_point_id("Hindu Marriage Act, 1955", "Section 9", 0)
    b = stable_point_id("Hindu Marriage Act, 1955", "Section 9", 0)
    c = stable_point_id("Hindu Marriage Act, 1955", "Section 9", 1)
    assert a == b
    assert a != c


def test_canonical_act_filtering():
    assert canonical_act("The Hindu Marriage Act, 1955 (bare act)") == \
        "Hindu Marriage Act, 1955"
    assert canonical_act("Protection of Women from Domestic Violence Act") == \
        "Protection of Women from Domestic Violence Act, 2005"
    assert canonical_act("Some Random Criminal Code") is None


def test_chunks_from_hf_row_uses_section_field():
    row = {"title": "Hindu Marriage Act, 1955", "text": HMA13,
           "section": "Section 13", "lang": "en"}
    chunks = chunks_from_hf_row(row)
    assert len(chunks) == 1
    assert chunks[0].section == "Section 13"
    assert chunks[0].act == "Hindu Marriage Act, 1955"


def test_build_points_idempotent():
    chunks = _fixture_chunks()[:2]
    emb = ConceptEmbedder()
    ids1, _, _ = build_points(chunks, emb.encode_passages([c.text for c in chunks]))
    ids2, _, _ = build_points(chunks, emb.encode_passages([c.text for c in chunks]))
    assert ids1 == ids2


# --- retrieval acceptance: EN/HI/KN probes hit the right sections ---

PROBES = [
    # (query, expected_section_substr, expected_act_substr)
    ("What are the grounds for divorce under Hindu law?", "13",
     "Hindu Marriage"),
    ("तलाक किन आधारों पर मिल सकता है?", "13", "Hindu Marriage"),
    ("ವಿಚ್ಛೇದನಕ್ಕೆ ಕಾರಣಗಳೇನು?", "13", "Hindu Marriage"),
    ("restitution of conjugal rights when spouse withdraws", "9",
     "Hindu Marriage"),
    ("घरेलू हिंसा में संरक्षण आदेश कैसे मिलेगा?", "12", "Domestic Violence"),
]


def test_retrieval_probes_hit_correct_sections():
    store, emb = _store_with_fixture()
    for query, want_section, want_act in PROBES:
        hits = store.search(emb.encode_query(query), top_k=3)
        assert hits, "no hits for %r" % query
        ok = [h for h in hits
              if want_section in h["payload"]["section"]
              and want_act in h["payload"]["act"]]
        assert ok, "query %r -> top-3 %r (want section %r in %r)" % (
            query, [(h["payload"]["act"], h["payload"]["section"]) for h in hits],
            want_section, want_act)


def test_retrieval_returns_provenance_payload():
    store, emb = _store_with_fixture()
    hits = store.search(emb.encode_query("divorce cruelty desertion"), top_k=1)
    assert set(["act", "section", "page", "lang", "source"]) <= set(hits[0]["payload"])


def test_neon_bookkeeping_idempotent():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import db as db_module
    from app.models import IngestedChunk

    engine = create_engine("sqlite://")
    db_module.init_db(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    chunks = _fixture_chunks()[:2]
    emb = ConceptEmbedder()
    ids, _, _ = build_points(chunks, emb.encode_passages([c.text for c in chunks]))
    for _ in range(2):  # run twice like a re-ingest
        for pid, c in zip(ids, chunks):
            row = s.query(IngestedChunk).filter_by(point_id=pid).first()
            if row is None:
                s.add(IngestedChunk(point_id=pid, act=c.act, section=c.section,
                                    lang=c.lang, source=c.source,
                                    collection="law_saathi"))
        s.commit()
    assert s.query(IngestedChunk).count() == 2
    # cosine sanity: identical vectors score 1.0
    v = emb.encode_query("divorce")
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    assert abs(sum(a * a for a in v) / (n * n) - 1.0) < 1e-9
    s.close()


def test_text_dir_loads_txt_and_md(tmp_path):
    from app.ingest import chunks_from_text_dir

    (tmp_path / "hindu_marriage_notes.txt").write_text(
        "Section 9 Restitution of conjugal rights. Body nine.", encoding="utf-8")
    (tmp_path / "divorce_notes.md").write_text(
        "# Divorce\n\nSection 13 Divorce. Body thirteen.", encoding="utf-8")
    chunks = chunks_from_text_dir(str(tmp_path))
    sections = [c.section for c in chunks]
    assert any("Section 9" in s for s in sections)
    assert any("Section 13" in s for s in sections)


def test_firecrawl_loader_chunks_markdown(monkeypatch):
    import app.ingest as ingest_mod

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"markdown": (
                "# Hindu Marriage Act\n\nSection 13 Divorce. Cruelty "
                "and desertion are grounds.")}}

    monkeypatch.setattr(ingest_mod.os, "environ",
                        {"FIRECRAWL_API_KEY": "test-key"})

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
    chunks = ingest_mod.chunks_from_firecrawl_url(
        "https://example.com/hma", act="Hindu Marriage Act, 1955")
    assert any("Section 13" in c.section for c in chunks)
    assert all(c.source.startswith("firecrawl:") for c in chunks)


def test_firecrawl_loader_needs_key(monkeypatch):
    import app.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod.os, "environ", {})
    try:
        ingest_mod.chunks_from_firecrawl_url("https://example.com/x", act="X")
    except RuntimeError as e:
        assert "FIRECRAWL_API_KEY" in str(e)
    else:
        raise AssertionError("expected RuntimeError for missing key")


def test_qdrant_store_upsert_texts_uses_document():
    import app.ingest as ingest_mod

    seen = {}

    class FakeResp:
        def raise_for_status(self):
            pass

    def fake_put(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["body"] = json
        return FakeResp()

    import httpx
    import unittest.mock as mock
    with mock.patch.object(httpx, "put", fake_put):
        store = ingest_mod.QdrantStore(
            None, collection="law_saathi",
            url="https://xyz.qdrant.io:6333", api_key="k")
        n = store.upsert_texts(["id-1"], ["Section 9 text"], [{"act": "HMA"}])
    assert n == 1
    assert seen["url"].endswith("/collections/law_saathi/points?wait=true")
    pt = seen["body"]["points"][0]
    assert pt["payload"] == {"act": "HMA"}
    assert pt["vector"] == {
        "text": "Section 9 text", "model": ingest_mod.QdrantStore.MODEL}


def test_qdrant_store_search_text_uses_document():
    import app.ingest as ingest_mod

    seen = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"result": {"points": [
                {"id": "id-1", "score": 0.9,
                 "payload": {"act": "HMA", "section": "Section 9"}}]}}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["body"] = json
        return FakeResp()

    import httpx
    import unittest.mock as mock
    with mock.patch.object(httpx, "post", fake_post):
        store = ingest_mod.QdrantStore(
            None, collection="law_saathi",
            url="https://xyz.qdrant.io:6333", api_key="k")
        hits = store.search_text("conjugal rights", top_k=3)
    assert seen["url"].endswith("/collections/law_saathi/points/query")
    assert seen["body"]["query"] == {
        "text": "conjugal rights",
        "model": ingest_mod.QdrantStore.MODEL}
    assert hits[0]["payload"]["section"] == "Section 9"


def test_chunks_from_hf_row_real_columns():
    from app.ingest import chunks_from_hf_row

    row = {"title": "The Hindu Adoptions and Maintenance  Act, 1956",
           "text": "Section 22: Maintenance of dependants. Subject to ...",
           "section_number": 22, "language_code": "en",
           "source_url": "https://www.indiacode.nic.in/handle/123456789/1638"}
    chunks = chunks_from_hf_row(row)
    assert len(chunks) == 1
    assert chunks[0].section == "Section 22"
    assert chunks[0].lang == "en"
    assert "indiacode" in chunks[0].source


def test_chunks_from_jsonl_roundtrip(tmp_path):
    import json
    from app.ingest import chunks_from_jsonl

    p = tmp_path / "sample.jsonl"
    p.write_text(json.dumps({
        "act": "Hindu Marriage Act, 1955",
        "row": {"title": "Hindu Marriage Act, 1955",
                "text": "Section 13 Divorce. Cruelty and desertion.",
                "section_number": 13, "language_code": "en"}}) + "\n",
        encoding="utf-8")
    chunks = chunks_from_jsonl(str(p))
    assert len(chunks) == 1
    assert chunks[0].act == "Hindu Marriage Act, 1955"
    assert chunks[0].section == "Section 13"


def test_stable_ids_unique_across_rows_same_section():
    from app.ingest import chunks_from_hf_row, stable_point_id

    def row(cid):
        return {"title": "Hindu Succession Act, 1956",
                "text": "Section 1 Short title. This Act may be called ...",
                "section_number": 1, "language_code": "en", "chunk_id": cid}

    a = chunks_from_hf_row(row("IND_x_s001"))
    b = chunks_from_hf_row(row("IND_y_s001"))
    assert stable_point_id(a[0].act, a[0].section, 0, a[0].uid) != \
        stable_point_id(b[0].act, b[0].section, 0, b[0].uid)
    # Same inputs -> same ID (idempotent re-runs).
    a2 = chunks_from_hf_row(row("IND_x_s001"))
    assert stable_point_id(a[0].act, a[0].section, 0, a[0].uid) == \
        stable_point_id(a2[0].act, a2[0].section, 0, a2[0].uid)


def test_matching_act_title_first():
    from app.ingest import matching_act

    # Title match wins.
    assert matching_act({"title": "Hindu Marriage Act, 1955",
                         "text": "..."}) == "Hindu Marriage Act, 1955"
    # Non-family title is out even if text mentions family law.
    assert matching_act({"title": "The Court-Fees Act, 1870",
                         "text": "applies to Hindu Marriage Act cases"}) is None
    # No title -> text-blob fallback still works.
    assert matching_act({"text": "Special Marriage Act procedure..."}) == \
        "Special Marriage Act, 1954"
    # Repealed rows are excluded even with a matching title.
    assert matching_act({"title": "The Special Marriage Act 1872 (Rep.)",
                         "act_status": "repealed"}) is None


def test_split_sections_numbered_bare_act():
    from app.ingest import chunk_act, split_sections

    text = ("THE HINDU MARRIAGE ACT, 1955\nPreliminary\n"
            "9. Restitution of conjugal rights.- When either spouse withdraws.\n"
            "See Sec. 15 for details of procedure.\n"
            "13. Divorce.- Any marriage may be dissolved on cruelty.")
    parts = split_sections(text)
    titles = [t for t, _ in parts]
    assert any(t.startswith("Section 9:") for t in titles), titles
    assert any(t.startswith("Section 13:") for t in titles), titles
    # Mid-text "Sec. 15" must not splinter a section.
    assert not any("Sec. 15" in t for t in titles)
    chunks = chunk_act("Hindu Marriage Act, 1955", text, source="bare-act")
    assert {c.section for c in chunks} == set(titles), \
        [c.section for c in chunks]
