"""Scope assertions for the family-law ingest registry.

The registry (api/app/family_law_acts.py) is the single list of what may
enter the vector index. These tests pin the 2026-10-21 trim: LawSaathi
answers family law only, so the index must not re-grow the out-of-scope
corpus that made a custody question compete with IPC sections for a slot
in the top-k (SCOPE.md §4: "Out-of-scope topics get a redirect, not an
answer.").
"""
from pathlib import Path

from app import family_law_acts as fla

# The topics SCOPE.md redirects instead of answering. An Act carrying one of
# these topics may only be in the index if it is narrowed to specific
# sections (e.g. BNSS s.144, the maintenance chapter inside criminal
# procedure).
OUT_OF_SCOPE_TOPICS = {"criminal", "criminal_procedure", "evidence"}

# The exact dataset titles, copied from in_central_legislation.parquet as
# read on 2026-10-21 (with the quirks: PMDA's trailing period, HAMA's double
# space, JJ 2015's trailing period). These are what resolve_dataset_titles
# is matched against in production.
DATASET_TITLES = [
    "The Hindu Marriage Act, 1955",
    "The Special Marriage Act, 1954",
    "The Indian Christian Marriage Act, 1872",
    "The Divorce Act, 1869",
    "The Parsi Marriage and Divorce Act, 1936.",
    "The Muslim Personal Law (Shariat) Application Act, 1937",
    "The Muslim Women (Protection of Rights on Divorce) Act, 1986",
    "The Muslim Women (Protection of Rights on Marriage) Act, 2019",
    "The Anand Marriage Act, 1909",
    "The Foreign Marriage Act, 1969",
    "The Hindu Adoptions and Maintenance  Act, 1956",
    "The Protection of Women from Domestic Violence Act, 2005",
    "The Dowry Prohibition Act, 1961",
    "The Family Courts Act, 1984",
    "The Maintenance and Welfare of Parents and Senior Citizens Act, 2007",
    "The Hindu Minority and Guardianship Act, 1956",
    "The Juvenile Justice (Care and Protection of Children) Act, 2015.",
    "The Protection of Children from Sexual Offences Act, 2012",
    "The Surrogacy (Regulation) Act, 2021",
    "The Assisted Reproductive Technology (Regulation) Act, 2021",
    "The Prohibition of Child Marriage Act, 2006",
    "The Medical Termination of Pregnancy Act, 1971",
    "The Hindu Succession Act, 1956",
    "The Indian Succession Act, 1925",
    "The Partition Act, 1893",
    "The Mediation Act, 2023",
    "The Guardians and Wards Act, 1890",
    "The Dissolution of Muslim Marriages Act, 1939",
    "The Arya Marriage Validation Act, 1937",
    "The Births, Deaths and Marriages Registration Act, 1886",
    "The Married Womens Property Act, 1874",
    "The Maintenance Orders Enforcement Act, 1921",
    "The Sexual Harassment of Women at Workplace (Prevention, "
    "Prohibition and Redressal) Act, 2013",
    "The Indecent Representation of Women (Prohibition) Act, 1986",
    "The Commissions for Protection of Child Rights Act, 2005",
    "The Bharatiya Nagarik Suraksha Sanhita, 2023",
    "The Code of Civil Procedure, 1908",
]


# ---------------------------------------------------------------------------
# 1. Registry contents
# ---------------------------------------------------------------------------

def test_every_entry_is_family_law_or_narrowed_with_a_reason():
    """Catches an entry that is out of scope AND unexplained.

    If someone adds an Act for labour, criminal or evidence law without
    narrowing it to family-relevant sections and recording which family-law
    need it serves, this fails and tells them which entry went wrong.
    """
    bad = []
    for e in fla.ACTS:
        family = (e.topic not in OUT_OF_SCOPE_TOPICS
                  and e.category != fla.CATEGORY_CRIMINAL)
        narrowed = (e.sections is not None
                    and len(e.sections) > 0
                    and e.rationale.strip() != "")
        if not (family or narrowed):
            bad.append(e.act)
    assert not bad, \
        "registry entries that are neither family-law Acts nor documented " \
        "section allowlists: %s" % bad


def test_out_of_scope_topic_requires_section_allowlist():
    """The named bug: a criminal/evidence Act re-added at full width.

    The trim cut IPC, BNS, BSA and the Evidence Act (~2042 live points) so
    87% of the index stopped being non-family law. This fails if any of them,
    or a new one, comes back as a whole-criminal-Act entry.
    """
    bad = [e.act for e in fla.ACTS
           if e.topic in OUT_OF_SCOPE_TOPICS and not e.sections]
    assert not bad, \
        "Acts with out-of-scope topics and no section allowlist: %s" % bad


def test_act_cut_by_the_trim_does_not_come_back():
    """The named bug: scope-creep restores the pre-trim index.

    Before the trim this module held 52 Acts and the Qdrant collection was
    87.3% non-family law. Anyone (human or assistant) re-listing one of the
    cut Acts fails here with the Act's name.
    """
    names = {fla.normalize_title(e.act) for e in fla.ACTS}
    back = [a for a in fla.EXCLUDED_ACTS if fla.normalize_title(a) in names]
    assert not back, "cut Acts re-listed in the registry: %s" % back


# ---------------------------------------------------------------------------
# 2. Allowlist syntax
# ---------------------------------------------------------------------------

def test_allowlisted_entries_are_documented_and_well_formed():
    """The named bug: an allowlist that parses to nothing at ingest time.

    sections=(\"Section 10::Stay of suit\",) must yield a number and (when
    the anchored form is used) a non-empty anchor; a spec like \"::\" or
    \"text only\" must fail loudly here rather than silently excluding the
    rows it was meant to keep.
    """
    narrowed = [e for e in fla.ACTS if e.sections is not None]
    assert narrowed, "expected the trimmed partial-scope Acts to be present"
    for e in narrowed:
        assert e.rationale.strip(), "%s: allowlisted without a rationale" % e.act
        for spec in e.sections:
            wants_num, anchor = fla.section_spec(spec)
            assert wants_num, "%s: spec %r parses to no section" % (e.act, spec)
            if "::" in spec:
                assert anchor, "%s: anchored spec %r lost its anchor" % \
                    (e.act, spec)
        assert e.repealed is False, \
            "%s: an allowlist for a repealed Act re-indexes stale law" % e.act


def test_allows_row_keeps_only_the_named_sections():
    """The named bug: the allowlist matches by nothing, or by everything.

    Two concrete regressions, measured against the real corpus on
    2026-10-21: (a) a bare-number CPC allowlist would ingest every rule of
    every Order that happens to carry the number (\"Section 10\" is 29 rows,
    only one of them CPC s.10 'Stay of suit'); (b) BNSS n.s.148-149 are
    public-order provisions; if they return, the maintenance chapter grew
    back into the whole criminal-code Act.
    """
    cpc = fla.BY_ACT["Code of Civil Procedure, 1908"]
    s10_row = ("Act: The Code of Civil Procedure, 1908 | In Force\n"
               "Section 10: Stay of suit\n1[Explanation VII.— ...]")
    assert cpc.allows_row("10", s10_row)
    assert cpc.allows_row("Section 10", s10_row)  # "Section " prefix ignored
    # Every other rule numbered 10 (Orders' rules) stays out.
    assert not cpc.allows_row(
        "10", "Section 10: Registry of memorandum of appeal\n* Order XLI ...")
    # The Act's other real sections and the 30 rows with no number at all
    # (Schedule indexes, report commentary) stay out.
    assert not cpc.allows_row("9", "Act: The Code of Civil Procedure, 1908")
    assert not cpc.allows_row("", "…ORDER XXXII SUITS BY OR AGAINST MINORS…")

    bnss = fla.BY_ACT["Bharatiya Nagarik Suraksha Sanhita, 2023"]
    maintenance_row = ("Chapter X: ORDER FOR MAINTENANCE OF WIVES, CHILDREN "
                       "AND PARENTS | Section 144: Order for maintenance")
    assert bnss.allows_row("144", maintenance_row)
    assert bnss.allows_row("147", "Section 147: Enforcement of order")
    assert not bnss.allows_row(
        "148", "Section 148: Dispersal of assembly by use of civil force")
    assert not bnss.allows_row("531", "any BNSS row outside Chapter X")

    whole = fla.BY_ACT["Hindu Marriage Act, 1955"]
    assert whole.allows_row("13B", "anything at all")
    assert whole.allows_row("", "unnumbered rows too, registry owns the Act")


# ---------------------------------------------------------------------------
# 3. Estimate snapshot
# ---------------------------------------------------------------------------

def test_estimate_snapshot_matches_the_registry():
    """The named bug: the estimate describes an index the registry no longer
    builds. After changing ACTS, the dry run must be re-run and this
    snapshot refreshed; otherwise the size floor below defends nothing.
    """
    registry_names = sorted(e.act for e in fla.ACTS)
    assert sorted(fla.ESTIMATED_CHUNKS) == registry_names, \
        "ESTIMATED_CHUNKS is stale; re-run ingest_family_law.py --dry-run"


def test_estimate_is_big_enough_for_family_law_to_be_the_index():
    """The named bug: coverage collapses and the floor is too low to say so.

    Measured 2026-10-21: the trimmed registry maps to 2365 statute chunks
    (+2 amendment notices). The floor sits above the loss of the biggest
    single Act (losing the Indian Succession Act, 517, must fail) and
    above the loss of any whole cluster (marriage ~600, children ~732,
    property/inheritance ~745).
    """
    assert len(fla.ESTIMATED_CHUNKS) >= 30
    total = sum(fla.ESTIMATED_CHUNKS.values())
    assert total >= fla.ESTIMATED_TOTAL_MIN
    # It is a coverage alarm, not a loose lower bound: losing the Indian
    # Succession Act (517, the biggest chunk count) already breaches the
    # floor. Losing a smaller single Act such as Juvenile Justice (219) is
    # caught by the snapshot test instead. If real coverage grows, raise the
    # floor with it.
    assert total - 517 < fla.ESTIMATED_TOTAL_MIN, \
        "raise ESTIMATED_TOTAL_MIN if real coverage grows"

    # Every registry Act must be indexed for family law or for a
    # documented family-law need; none may be labelled criminal.
    out_of_scope = [e.act for e in fla.ACTS
                    if e.topic in OUT_OF_SCOPE_TOPICS]
    assert not out_of_scope, out_of_scope


# ---------------------------------------------------------------------------
# 4. Title resolution
# ---------------------------------------------------------------------------

def test_resolve_dataset_titles_resolves_every_entry():
    """The named bug: an Act that silently fails to resolve contributes zero
    points: the trim quietly deletes coverage. The registry's own
    dataset_title must always resolve to itself...
    """
    for entry in fla.ACTS:
        out = fla.resolve_dataset_titles([entry.dataset_title])
        assert out.get(entry.dataset_title) is entry, \
            "registry Act %r does not resolve its own dataset_title %r" % (
                entry.act, entry.dataset_title)


def test_resolve_matches_the_real_dataset_titles():
    """The named bug: guess-free regression against dataset quirks.

    These title strings were read from in_central_legislation.parquet on
    2026-10-21, including the two rows whose punctuation resolutions were
    hand-patched: double space (HAMA), trailing period (PMDA, JJ 2015).
    """
    out = fla.resolve_dataset_titles(DATASET_TITLES)
    assert len(out) == len(DATASET_TITLES)
    # The fixture is the registry's own title set as measured in the parquet:
    # a registry change without refreshing this fixture is caught here.
    assert set(DATASET_TITLES) == {e.dataset_title for e in fla.ACTS}

    hama = out["The Hindu Adoptions and Maintenance  Act, 1956"]
    assert hama.act == "Hindu Adoptions and Maintenance Act, 1956"
    assert out["The Parsi Marriage and Divorce Act, 1936."].act == \
        "Parsi Marriage and Divorce Act, 1936"
    assert out["The Juvenile Justice (Care and Protection of "
               "Children) Act, 2015."].act == \
        "Juvenile Justice (Care and Protection of Children) Act, 2015"
    assert out["The Code of Civil Procedure, 1908"].sections == \
        ("Section 10::Stay of suit",)
    assert out["The Bharatiya Nagarik Suraksha Sanhita, 2023"].topic == \
        "maintenance"


def test_resolve_drops_the_cut_acts():
    """The named bug: deleting a registry entry while the title resolver
    still matches it: the trim would be a no-op and the out-of-scope corpus
    continues to be pulled in.
    """
    for title in [
        # The IPC's dataset row carries the repealing stamp.
        "The Indian Penal Code, 45 of 1860 (Rep., Act 45 of 2023)",
        "The Code on Social Security, 2020",
        "The Transfer of Property Act, 1882",
        "The Limitation Act, 1963",
        "The Registration Act, 1908",
        "The Juvenile Justice Act 1986, 53 of 1986 (Rep., Act 56 of 2000)",
        "The Maternity Benefit Act, 1961, 53 of 1961 (Rep., Act 36 of 2020)",
        "The Right of Children to Free and Compulsory Education Act, 2009",
        "The Child and Adolescent Labour (Prohibition and "
        "Regulation) Act, 1986",
        "The Specific Relief Act, 1963",
        "The Mental Healthcare Act, 2017",
        "The Bharatiya Nyaya Sanhita, 2023",
        "The Bharatiya Sakshya Adhiniyam, 2023",
        "The Indian Evidence Act, 1872, 1 of 1872 (Rep., Act 47 of 2023)",
        "The Hindu Disposition of Property Act, 1916",
    ]:
        assert fla.resolve_dataset_titles([title]) == {}, title


# ---------------------------------------------------------------------------
# 5. The ingester applies the allowlist
# ---------------------------------------------------------------------------

def _script():
    from importlib.util import module_from_spec, spec_from_file_location
    path = (Path(__file__).resolve().parents[1] / "scripts" /
            "ingest_family_law.py")
    spec = spec_from_file_location("ingest_family_law", path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ingest_keeps_only_allowlisted_sections_and_chunks_the_rest_normally():
    """The named bug: the ingester ignores the allowlist.

    BNSS s.148 (public order) hides behind an allowlist that names only
    Chapter X: a returned s.148 chunk proves the gate fails open. The
    s.144 row over 1500 chars proves the kept rows still go through
    chunk_text normally instead of being truncated to a single blob.
    """
    mod = _script()
    title = "The Bharatiya Nagarik Suraksha Sanhita, 2023"
    filler = "maintenance wages sentence rations awaited converted. " * 55
    # 2970 chars: the sliding window advances 1300 per piece (1500 - 200
    # overlap), so a third piece needs more than 2800 chars.
    assert len(filler) > 2800
    short = "Chapter X. Section 144: allowance owed, warrant issued."
    forbidden = ("Section 148: Dispersal of assembly by use of civil force."
                 " Orders under this section remain outside the index.")
    rows = {c: ["" for _ in range(3)] for c in mod.NEEDED_COLS}
    rows["title"] = [title, title, title]
    rows["section_number"] = ["144", "148", "144"]
    rows["section_type"] = ["section", "section", "section"]
    rows["chunk_id"] = ["c144a", "c148x", "c144b"]
    rows["act_status"] = ["in_force"] * 3
    rows["in_force"] = [True] * 3
    rows["text"] = [filler, forbidden, short]

    mapping = fla.resolve_dataset_titles(rows["title"])
    entry = mapping[title]
    assert entry.sections, "test is meaningless without the allowlist"

    ids, texts, payloads, per_act, _ = mod.collect(rows, mapping)

    assert per_act[entry.act] == 4, per_act  # 3 pieces of s.144 + 1 short row
    assert len(ids) == 4 and len(set(ids)) == 4  # unique stable ids
    joined = " ".join(texts)
    assert "Dispersal of assembly" not in joined, \
        "s.148 leaked through the section allowlist"
    # The 2970-char s.144 row went through chunk_text normally (pieces stay
    # inside MAX_CHARS and the count matches the sliding window), rather than
    # being truncated to one blob.
    assert all(len(t) <= 1500 for t in texts)
    lens = sorted((len(t) for t in texts), reverse=True)
    assert lens[0] == 1500 or lens[0] < 1500 and lens[0] >= 1300, lens

    # Kept rows become normal statute payloads, not a special case.
    p0 = payloads[0]
    assert p0["act"] == entry.act and p0["topic"] == "maintenance", p0
    assert p0["section"] == "Section 144", p0
    assert p0["source"] == "vaquill/open-india-law", p0
    assert p0["act_status"] == "in_force", p0
    p_last = payloads[-1]
    assert p_last["section"] == "Section 144" and p_last["total_chunks"] == 1
