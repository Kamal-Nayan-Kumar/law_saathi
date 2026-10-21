"""Curated family-law act registry for the LawSaathi index.

The dataset ``vaquill/open-india-law`` (file ``in_central_legislation.parquet``)
carries ~1,568 central Acts. LawSaathi answers family-law questions only, so
this module is the single list of what is allowed into the vector index, and
the single place the payload metadata is built.

Every entry maps the dataset's *exact* ``title`` to:

- ``act``      canonical, human-readable name used in citations
  (e.g. "Hindu Marriage Act, 1955").
- ``category`` the grouping from the product scope, so the UI / planner can
  filter ("Marriage, divorce and personal law", ...).
- ``topic``    a coarse retrieval key ("divorce", "maintenance", ...).
- ``sections`` optional section-level allowlist. Most Acts contribute all
  their sections; an Act that is part-out-of-scope carries ``sections``
  (``"144"``, or ``"10::Stay of suit"`` for a section the dataset numbers
  ambiguously) and the ingester keeps only those rows for that Act.
- ``rationale`` required when ``sections`` is set: which family-law need
  keeps the narrowed Act in the index.

Design notes
------------
- Matching is on the *normalised* dataset title (lowercased, punctuation and
  the leading "The " removed, a trailing "(Rep., ...)" stamp dropped). The
  dataset is inconsistent: "The Hindu Adoptions and Maintenance  Act, 1956"
  has a double space, "The Parsi Marriage and Divorce Act, 1936." a trailing
  period. Normalising once is the only robust way in.
- Nothing is inferred from a substring of an Act name: an Act is either in the
  registry or it is refused. Adding an Act is a one-line change here.
- The 2026-10-21 trim (SCOPE.md: "Family law only. Out-of-scope topics get a
  redirect, not an answer.") removed the criminal/evidence/social-security/
  property Acts that had crowded family law out of retrieval, since repealed
  statutes sat next to their successors. Two partly-out-of-scope Acts survive
  as section allowlists: the Code of Civil Procedure and the Bharatiya
  Nagarik Suraksha Sanhita (maintenance chapter). EXCLUDED_ACTS below records
  what was cut so it does not creep back.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Categories (the product scope, sections A-E)
# ---------------------------------------------------------------------------

CATEGORY_MARRIAGE = "A. Marriage, divorce and personal law"
CATEGORY_MAINTENANCE = "B. Maintenance, domestic disputes and family courts"
CATEGORY_CHILDREN = "C. Children, adoption and reproductive rights"
CATEGORY_PROPERTY = "D. Property, inheritance and civil procedure"
CATEGORY_CRIMINAL = "E. Criminal law and evidence"

CATEGORY_KEYS = {
    CATEGORY_MARRIAGE: "marriage_divorce_personal_law",
    CATEGORY_MAINTENANCE: "maintenance_domestic_family_courts",
    CATEGORY_CHILDREN: "children_adoption_reproductive",
    CATEGORY_PROPERTY: "property_inheritance_civil",
    CATEGORY_CRIMINAL: "criminal_law_evidence",
}


@dataclass(frozen=True)
class ActEntry:
    act: str            # canonical name, no "The", used in citations
    dataset_title: str  # exact title in the parquet (kept for the resolve step)
    category: str       # one of the CATEGORY_* strings
    topic: str          # coarse retrieval key
    repealed: bool = False
    # Section-level allowlist: the only ``section_number`` values this Act may
    # contribute. ``None`` = the whole Act is in scope. Each entry is either
    # "144" (keep every row numbered 144) or "10::Stay of suit" (keep row 10
    # only when the anchor text occurs in the row body, case-insensitive).
    # Anchors exist for Acts whose dataset numbering is not
    # one-number-per-section: vaquill numbers every Order-rule of the CPC as
    # its own "Section N", so a bare "10" would ingest ~30 unrelated rules
    # instead of s.10 "Stay of suit".
    sections: Optional[Tuple[str, ...]] = None
    # Required when ``sections`` is set: the family-law need this slice of the
    # Act serves. Assertions in tests/test_family_law_acts.py enforce it.
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.sections is not None:
            # Fail at import: a typo in the allowlist must not silently
            # drop whole sections at ingest time.
            for spec in self.sections:
                try:
                    section_spec(spec)
                except ValueError as e:
                    raise ValueError(
                        "ActEntry %r: bad section spec %r: %s"
                        % (self.act, spec, e)) from None

    @property
    def category_key(self) -> str:
        return CATEGORY_KEYS[self.category]

    def allows_row(self, section_number, text: str = "") -> bool:
        """May this dataset row enter the index for this Act?

        Acts without an allowlist allow every row. Checked per row by
        ``api/scripts/ingest_family_law.py`` before chunking, so an
        allowlisted Act contributes exactly the sections the registry named
        and nothing else.
        """
        specs = self.sections
        if not specs:
            return True
        num = normalize_section_number(section_number)
        body = (text or "").lower()
        for spec in specs:
            wants_num, anchor = section_spec(spec)
            if wants_num == num and (anchor is None or anchor in body):
                return True
        return False


def normalize_section_number(value) -> str:
    """"Section 144" / " 144 "/ "144" -> "144"."""
    s = str(value or "").strip().lower()
    s = re.sub(r"^section\s*", "", s)
    return s.replace(" ", "")


@lru_cache(maxsize=None)
def section_spec(spec: str) -> Tuple[str, Optional[str]]:
    """Split an allowlist entry into (section number, optional anchor).

    ``"Section 144"`` -> ``("144", None)``; ``"10::Stay of suit"`` ->
    ``("10", "stay of suit")``. The "Section " prefix is accepted because the
    registry is written for humans; the anchor is lowercased because it is
    matched case-insensitively against row text.
    """
    raw = (spec or "").strip()
    if not raw:
        raise ValueError("empty section spec")
    num_part, sep, anchor_part = raw.partition("::")
    anchor = anchor_part.strip().lower() if sep else None
    num = re.sub(r"^section\s*", "", num_part.strip(),
                 flags=re.IGNORECASE).strip().replace(" ", "")
    if not num:
        raise ValueError("no section number in %r" % spec)
    return num.lower(), anchor


# ---------------------------------------------------------------------------
# The registry. Order mirrors the product scope document.
# ---------------------------------------------------------------------------

ACTS: List[ActEntry] = [
    # A. Marriage, divorce and personal law
    ActEntry("Hindu Marriage Act, 1955",
             "The Hindu Marriage Act, 1955", CATEGORY_MARRIAGE, "marriage"),
    ActEntry("Special Marriage Act, 1954",
             "The Special Marriage Act, 1954", CATEGORY_MARRIAGE, "marriage"),
    ActEntry("Indian Christian Marriage Act, 1872",
             "The Indian Christian Marriage Act, 1872",
             CATEGORY_MARRIAGE, "marriage"),
    ActEntry("Divorce Act, 1869",
             "The Divorce Act, 1869", CATEGORY_MARRIAGE, "divorce"),
    ActEntry("Parsi Marriage and Divorce Act, 1936",
             "The Parsi Marriage and Divorce Act, 1936.",
             CATEGORY_MARRIAGE, "divorce"),
    ActEntry("Muslim Personal Law (Shariat) Application Act, 1937",
             "The Muslim Personal Law (Shariat) Application Act, 1937",
             CATEGORY_MARRIAGE, "personal_law"),
    ActEntry("Muslim Women (Protection of Rights on Divorce) Act, 1986",
             "The Muslim Women (Protection of Rights on Divorce) Act, 1986",
             CATEGORY_MARRIAGE, "divorce"),
    ActEntry("Muslim Women (Protection of Rights on Marriage) Act, 2019",
             "The Muslim Women (Protection of Rights on Marriage) Act, 2019",
             CATEGORY_MARRIAGE, "marriage"),
    ActEntry("Anand Marriage Act, 1909",
             "The Anand Marriage Act, 1909", CATEGORY_MARRIAGE, "marriage"),
    ActEntry("Foreign Marriage Act, 1969",
             "The Foreign Marriage Act, 1969", CATEGORY_MARRIAGE, "marriage"),

    # B. Maintenance, domestic disputes and family courts
    ActEntry("Hindu Adoptions and Maintenance Act, 1956",
             "The Hindu Adoptions and Maintenance  Act, 1956",
             CATEGORY_MAINTENANCE, "maintenance"),
    ActEntry("Protection of Women from Domestic Violence Act, 2005",
             "The Protection of Women from Domestic Violence Act, 2005",
             CATEGORY_MAINTENANCE, "domestic_violence"),
    ActEntry("Dowry Prohibition Act, 1961",
             "The Dowry Prohibition Act, 1961", CATEGORY_MAINTENANCE, "dowry"),
    ActEntry("Family Courts Act, 1984",
             "The Family Courts Act, 1984", CATEGORY_MAINTENANCE, "family_courts"),
    ActEntry("Maintenance and Welfare of Parents and Senior Citizens Act, 2007",
             "The Maintenance and Welfare of Parents and Senior Citizens Act, 2007",
             CATEGORY_MAINTENANCE, "maintenance"),

    # C. Children, adoption and reproductive rights
    ActEntry("Hindu Minority and Guardianship Act, 1956",
             "The Hindu Minority and Guardianship Act, 1956",
             CATEGORY_CHILDREN, "guardianship"),
    ActEntry("Juvenile Justice (Care and Protection of Children) Act, 2015",
             "The Juvenile Justice (Care and Protection of Children) Act, 2015.",
             CATEGORY_CHILDREN, "children"),
    ActEntry("Protection of Children from Sexual Offences Act, 2012",
             "The Protection of Children from Sexual Offences Act, 2012",
             CATEGORY_CHILDREN, "children"),
    ActEntry("Surrogacy (Regulation) Act, 2021",
             "The Surrogacy (Regulation) Act, 2021",
             CATEGORY_CHILDREN, "surrogacy"),
    ActEntry("Assisted Reproductive Technology (Regulation) Act, 2021",
             "The Assisted Reproductive Technology (Regulation) Act, 2021",
             CATEGORY_CHILDREN, "reproductive"),
    ActEntry("Prohibition of Child Marriage Act, 2006",
             "The Prohibition of Child Marriage Act, 2006",
             CATEGORY_CHILDREN, "child_marriage"),
    ActEntry("Medical Termination of Pregnancy Act, 1971",
             "The Medical Termination of Pregnancy Act, 1971",
             CATEGORY_CHILDREN, "reproductive"),
    # Cut 2026-10-21: treatment/psychiatry, not family law (SCOPE.md §4).
    # Mental Healthcare Act 2017 (255 live points) left the registry; JJ
    # 2015 and the medical-termination provisions above carry the family
    # questions that once cost it a slot.

    # D. Property, inheritance and civil procedure
    ActEntry("Hindu Succession Act, 1956",
             "The Hindu Succession Act, 1956", CATEGORY_PROPERTY, "succession"),
    ActEntry("Indian Succession Act, 1925",
             "The Indian Succession Act, 1925", CATEGORY_PROPERTY, "succession"),
    ActEntry("Partition Act, 1893",
             "The Partition Act, 1893", CATEGORY_PROPERTY, "partition"),
    ActEntry("Mediation Act, 2023",
             "The Mediation Act, 2023", CATEGORY_PROPERTY, "mediation"),

    # E. Criminal law and evidence: no whole Act here. LawSaathi redirects
    # criminal/evidence questions (SCOPE.md §4), so the criminal Acts were
    # cut on 2026-10-21: Bharatiya Nyaya Sanhita, Bharatiya Sakshya
    # Adhiniyam, Indian Penal Code (repealed), Indian Evidence Act (repealed).
    # The one thing family law borrows from criminal procedure is the
    # maintenance machinery, which stays below as a section allowlist.
    ActEntry("Bharatiya Nagarik Suraksha Sanhita, 2023",
             "The Bharatiya Nagarik Suraksha Sanhita, 2023",
             CATEGORY_MAINTENANCE, "maintenance",
             sections=("144", "145", "146", "147"),
             rationale="Chapter X (ss.144-147) is the maintenance machinery: "
                       "the successor to CrPC 1973 s.125. Cited by Hindu "
                       "Marriage Act s.4, Special Marriage Act s.27, Parsi "
                       "Marriage and Divorce Act s.32A (maintenance 'in "
                       "addition to' a s.125 order), Domestic Violence Act "
                       "s.20, and Family Courts Act s.19 / Senior Citizens "
                       "Act s.11 (appeals from and orders under Chapter IX "
                       "of the CrPC 1973), the CrPC chapter this replaced. "
                       "s.144 order, s.145 procedure, s.146 alteration of "
                       "allowance, s.147 enforcement."),
]


# ---------------------------------------------------------------------------
# Additional acts added 2026-10-15, after a gap review against the dataset
# (docs/FAMILY-LAW-ACTS.md §1). Same categories as above.
# ---------------------------------------------------------------------------

_ADDITIONAL_ACTS: List[ActEntry] = [
    # --- Custody / guardianship -------------------------------------------------
    # The core guardianship statute. Its absence is why a bare custody query
    # ranked Divorce Act sections first: Guardians and Wards s.17 says "welfare
    # of the minor", not "custody", so similarity alone cannot find it.
    ActEntry("Guardians and Wards Act, 1890",
             "The Guardians and Wards Act, 1890",
             CATEGORY_CHILDREN, "custody"),
    # --- Muslim personal law ----------------------------------------------------
    ActEntry("Dissolution of Muslim Marriages Act, 1939",
             "The Dissolution of Muslim Marriages Act, 1939",
             CATEGORY_MARRIAGE, "divorce"),
    # --- Marriage validity / registration --------------------------------------
    ActEntry("Arya Marriage Validation Act, 1937",
             "The Arya Marriage Validation Act, 1937",
             CATEGORY_MARRIAGE, "marriage"),
    ActEntry("Births, Deaths and Marriages Registration Act, 1886",
             "The Births, Deaths and Marriages Registration Act, 1886",
             CATEGORY_MARRIAGE, "marriage"),
    # --- Married women's property ----------------------------------------------
    ActEntry("Married Women's Property Act, 1874",
             "The Married Womens Property Act, 1874",
             CATEGORY_PROPERTY, "property"),
    # --- Maintenance machinery --------------------------------------------------
    ActEntry("Maintenance Orders Enforcement Act, 1921",
             "The Maintenance Orders Enforcement Act, 1921",
             CATEGORY_MAINTENANCE, "maintenance"),
    # Cut 2026-10-21 as out of scope (SCOPE.md §4): Code on Social Security
    # 2020 (labour/social-security, 546 live points crowding out family law)
    # and Maternity Benefit Act 1961 (repealed by the Code on Social
    # Security).
    # --- Women's safety ---------------------------------------------------------
    ActEntry("Sexual Harassment of Women at Workplace Act, 2013",
             "The Sexual Harassment of Women at Workplace (Prevention, "
             "Prohibition and Redressal) Act, 2013",
             CATEGORY_MAINTENANCE, "women_safety"),
    ActEntry("Indecent Representation of Women (Prohibition) Act, 1986",
             "The Indecent Representation of Women (Prohibition) Act, 1986",
             CATEGORY_MAINTENANCE, "women_safety"),
    # --- Child protection -------------------------------------------------------
    ActEntry("Commissions for Protection of Child Rights Act, 2005",
             "The Commissions for Protection of Child Rights Act, 2005",
             CATEGORY_CHILDREN, "children"),
    # Cut 2026-10-21 as out of scope (education, labour; SCOPE.md §4): Right
    # of Children to Free and Compulsory Education Act 2009, Child and
    # Adolescent Labour Act 1986, Juvenile Justice Act 1986 (repealed 2000;
    # the 2015 Act above is the current one).
    # --- Civil procedure --------------------------------------------------------
    # The dataset's CPC rows are not the bare Act: vaquill numbers every
    # Order-rule as its own "Section N" (CPC s.9 "Courts to try all civil
    # suits", s.24 and s.25 have no row at all; "125" does not exist). The
    # only real bare-Act row family law can use cleanly is s.10; the anchor
    # stops the ~28 other "Section 10" Order-rule rows from entering.
    ActEntry("Code of Civil Procedure, 1908",
             "The Code of Civil Procedure, 1908",
             CATEGORY_PROPERTY, "civil_procedure",
             sections=("Section 10::Stay of suit",),
             rationale="CPC s.10 bars a parallel suit while a proceeding is "
                       "already pending: the rule that keeps a maintenance "
                       "or DV proceeding (BNSS s.144 / DV Act) and a civil "
                       "divorce suit from colliding. Everything else this "
                       "dataset carries for the CPC is Order-rules and "
                       "forms, not the bare Act; the sections AGENTS.md "
                       "listed (s.9, s.24, s.25, s.125, Order 32) have no "
                       "row or are not addressable by section number."),
]

ACTS.extend(_ADDITIONAL_ACTS)

# ---------------------------------------------------------------------------
# Out of scope, cut on 2026-10-21. Kept as a deny-list so a future
# "helpful" restore fails the registry tests instead of silently
# re-crowding family law out of retrieval. All 15 were indexed until
# 2026-10-21; see SCOPE.md §4 and the report of that trim.
# ---------------------------------------------------------------------------
EXCLUDED_ACTS: Tuple[str, ...] = (
    "Indian Penal Code, 1860",               # repealed 2023 (BNS does not apply to family answers)
    "Bharatiya Nyaya Sanhita, 2023",         # criminal law
    "Bharatiya Sakshya Adhiniyam, 2023",     # evidence
    "Indian Evidence Act, 1872",             # repealed 2023
    "Code on Social Security, 2020",         # labour / social security
    "Maternity Benefit Act, 1961",           # repealed 2020
    "Mental Healthcare Act, 2017",           # treatment and psychiatry
    "Transfer of Property Act, 1882",
    "Registration Act, 1908",
    "Limitation Act, 1963",
    "Specific Relief Act, 1963",
    "Hindu Disposition of Property Act, 1916",
    "Right of Children to Free and Compulsory Education Act, 2009",
    "Child and Adolescent Labour (Prohibition and Regulation) Act, 1986",
    "Juvenile Justice Act, 1986",            # repealed 2000; JJ 2015 above
)

# ---------------------------------------------------------------------------
# Measured footprint (2026-10-21). Source of truth: the dry run
#   .venv/bin/python api/scripts/ingest_family_law.py --dry-run \
#     --parquet data/corpus/in_central_legislation.parquet
# which chunked 2365 statute rows with the trimmed registry (+2 hand-written
# amendment notices = 2367 points total on a clean re-ingest). The per-Act
# numbers below are chunks produced by chunk_text(1500/200), not raw rows.
# The sync test in tests/test_family_law_acts.py requires these keys to be
# exactly the registry's Act names, so a registry change without a re-run
# of the dry run fails instead of quietly describing the wrong index.
# ---------------------------------------------------------------------------
ESTIMATED_CHUNKS: Dict[str, int] = {
    "Indian Succession Act, 1925": 517,
    "Juvenile Justice (Care and Protection of Children) Act, 2015": 219,
    "Indian Christian Marriage Act, 1872": 121,
    "Mediation Act, 2023": 121,
    "Divorce Act, 1869": 106,
    "Special Marriage Act, 1954": 97,
    "Surrogacy (Regulation) Act, 2021": 96,
    "Medical Termination of Pregnancy Act, 1971": 93,
    "Parsi Marriage and Divorce Act, 1936": 78,
    "Assisted Reproductive Technology (Regulation) Act, 2021": 78,
    "Guardians and Wards Act, 1890": 75,
    "Protection of Children from Sexual Offences Act, 2012": 75,
    "Hindu Succession Act, 1956": 65,
    "Protection of Women from Domestic Violence Act, 2005": 58,
    "Hindu Marriage Act, 1955": 56,
    "Foreign Marriage Act, 1969": 56,
    "Sexual Harassment of Women at Workplace Act, 2013": 51,
    "Commissions for Protection of Child Rights Act, 2005": 48,
    "Maintenance and Welfare of Parents and Senior Citizens Act, 2007": 45,
    "Births, Deaths and Marriages Registration Act, 1886": 45,
    "Hindu Adoptions and Maintenance Act, 1956": 42,
    "Prohibition of Child Marriage Act, 2006": 33,
    "Family Courts Act, 1984": 31,
    "Married Women's Property Act, 1874": 28,
    "Maintenance Orders Enforcement Act, 1921": 21,
    "Dowry Prohibition Act, 1961": 18,
    "Hindu Minority and Guardianship Act, 1956": 15,
    "Partition Act, 1893": 13,
    "Indecent Representation of Women (Prohibition) Act, 1986": 11,
    "Bharatiya Nagarik Suraksha Sanhita, 2023": 11,
    "Muslim Women (Protection of Rights on Divorce) Act, 1986": 10,
    "Dissolution of Muslim Marriages Act, 1939": 9,
    "Muslim Personal Law (Shariat) Application Act, 1937": 7,
    "Anand Marriage Act, 1909": 7,
    "Muslim Women (Protection of Rights on Marriage) Act, 2019": 7,
    "Arya Marriage Validation Act, 1937": 1,
    "Code of Civil Procedure, 1908": 1,
}
# Floor on the estimated index size after a clean re-ingest. The live
# family-law core was 1126 points before the trim and the trimmed registry
# estimates 2365. Sits below the healthy total but above the loss of the
# biggest single Act (Indian Succession, 517) and above the loss of any whole
# cluster (marriage ~600, children ~732, property/inheritance ~745), so any
# of those regressing silently breaches the floor. Below it, the estimate
# describes a broken corpus.
ESTIMATED_TOTAL_MIN = 1900

BY_ACT: Dict[str, ActEntry] = {e.act: e for e in ACTS}
BY_DATASET_TITLE: Dict[str, ActEntry] = {e.dataset_title: e for e in ACTS}


# ---------------------------------------------------------------------------
# Title matching
# ---------------------------------------------------------------------------

_REP_SUFFIX = re.compile(r"\(\s*rep\..*$", re.IGNORECASE)


def normalize_title(title: Optional[str]) -> str:
    """Lowercase, drop the leading "The ", punctuation and repealing stamps."""
    s = (title or "").lower()
    s = _REP_SUFFIX.sub("", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    if s.startswith("the"):
        s = s[3:]
    return s


def resolve_dataset_titles(dataset_titles) -> Dict[str, ActEntry]:
    """Map every dataset title that belongs to the registry to its entry.

    Returns ``{dataset_title: ActEntry}``. A registry Act that matches nothing
    is simply absent from the result (the caller reports it as missing), and a
    title that matches two registry Acts is impossible because the two
    normalised keys would have to be equal.
    """
    wanted = {normalize_title(e.dataset_title): e for e in ACTS}
    out: Dict[str, ActEntry] = {}
    for title in dataset_titles:
        key = normalize_title(title)
        entry = wanted.get(key)
        if entry is not None:
            out[title] = entry
            continue
        # The Evidence Act's row carries a repealing stamp the normaliser
        # cannot strip from the *entry* side too; fall back to longest-prefix.
        for wkey, wentry in wanted.items():
            if wkey and key.startswith(wkey) and len(wkey) >= 12:
                out[title] = wentry
                break
    return out


def act_names() -> List[str]:
    return [e.act for e in ACTS]


def entry_payload(entry: ActEntry) -> Dict:
    d = asdict(entry)
    d["category_key"] = entry.category_key
    return d
