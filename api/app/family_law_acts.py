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

Design notes
------------
- Matching is on the *normalised* dataset title (lowercased, punctuation and
  the leading "The " removed, a trailing "(Rep., ...)" stamp dropped). The
  dataset is inconsistent: "The Hindu Adoptions and Maintenance  Act, 1956"
  has a double space, "The Parsi Marriage and Divorce Act, 1936." a trailing
  period. Normalising once is the only robust way in.
- Nothing is inferred from a substring of an Act name: an Act is either in the
  registry or it is refused. Adding an Act is a one-line change here.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

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

    @property
    def category_key(self) -> str:
        return CATEGORY_KEYS[self.category]


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
    ActEntry("Mental Healthcare Act, 2017",
             "The Mental Healthcare Act, 2017",
             CATEGORY_CHILDREN, "mental_health"),

    # D. Property, inheritance and civil procedure
    ActEntry("Hindu Succession Act, 1956",
             "The Hindu Succession Act, 1956", CATEGORY_PROPERTY, "succession"),
    ActEntry("Indian Succession Act, 1925",
             "The Indian Succession Act, 1925", CATEGORY_PROPERTY, "succession"),
    ActEntry("Partition Act, 1893",
             "The Partition Act, 1893", CATEGORY_PROPERTY, "partition"),
    ActEntry("Mediation Act, 2023",
             "The Mediation Act, 2023", CATEGORY_PROPERTY, "mediation"),

    # E. Criminal law and evidence
    ActEntry("Bharatiya Nyaya Sanhita, 2023",
             "The Bharatiya Nyaya Sanhita, 2023",
             CATEGORY_CRIMINAL, "criminal"),
    ActEntry("Bharatiya Nagarik Suraksha Sanhita, 2023",
             "The Bharatiya Nagarik Suraksha Sanhita, 2023",
             CATEGORY_CRIMINAL, "criminal_procedure"),
    ActEntry("Bharatiya Sakshya Adhiniyam, 2023",
             "The Bharatiya Sakshya Adhiniyam, 2023",
             CATEGORY_CRIMINAL, "evidence"),
    # Repealed in 2023 (replaced by the Sakshya Adhiniyam) but kept for older
    # judgments and for questions about matters that arose before then.
    ActEntry("Indian Evidence Act, 1872",
             "The Indian Evidence Act, 1872, 1 of 1872 (Rep., Act 47 of 2023)",
             CATEGORY_CRIMINAL, "evidence", repealed=True),
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
    # --- Maternity / social security -------------------------------------------
    ActEntry("Code on Social Security, 2020",
             "The Code on Social Security, 2020",
             CATEGORY_CHILDREN, "social_security"),
    ActEntry("Maternity Benefit Act, 1961",
             "The Maternity Benefit Act, 1961, 53 of 1961 (Rep., Act 36 of 2020)",
             CATEGORY_CHILDREN, "maternity", repealed=True),
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
    ActEntry("Right of Children to Free and Compulsory Education Act, 2009",
             "The Right of Children to Free and Compulsory Education Act, 2009",
             CATEGORY_CHILDREN, "children"),
    ActEntry("Child and Adolescent Labour (Prohibition and Regulation) Act, 1986",
             "The Child and Adolescent Labour (Prohibition and Regulation) Act, 1986",
             CATEGORY_CHILDREN, "children"),
    ActEntry("Juvenile Justice Act, 1986",
             "The Juvenile Justice Act 1986, 53 of 1986 (Rep., Act 56 of 2000)",
             CATEGORY_CHILDREN, "children", repealed=True),
    # --- Civil procedure / property / evidence ---------------------------------
    ActEntry("Code of Civil Procedure, 1908",
             "The Code of Civil Procedure, 1908",
             CATEGORY_PROPERTY, "civil_procedure"),
    ActEntry("Transfer of Property Act, 1882",
             "The Transfer of Property Act, 1882",
             CATEGORY_PROPERTY, "property"),
    ActEntry("Registration Act, 1908",
             "The Registration Act, 1908",
             CATEGORY_PROPERTY, "registration"),
    ActEntry("Limitation Act, 1963",
             "The Limitation Act, 1963",
             CATEGORY_PROPERTY, "limitation"),
    ActEntry("Specific Relief Act, 1963",
             "The Specific Relief Act, 1963",
             CATEGORY_PROPERTY, "civil_procedure"),
    ActEntry("Hindu Disposition of Property Act, 1916",
             "The Hindu Disposition of Property Act, 1916",
             CATEGORY_PROPERTY, "property"),
    # --- Historical / repealed, same reason as the Evidence Act above -----------
    ActEntry("Indian Penal Code, 1860",
             "The Indian Penal Code, 45 of 1860 (Rep., Act 45 of 2023)",
             CATEGORY_CRIMINAL, "criminal", repealed=True),
]

ACTS.extend(_ADDITIONAL_ACTS)

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
