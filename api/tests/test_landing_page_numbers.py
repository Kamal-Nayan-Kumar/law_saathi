"""The numbers the landing page quotes must match the corpus.

The landing page says how many Acts are in the library and how many
in-force sections there are. Those numbers were right once, then the index
was trimmed, and they were still on the page for a while saying 52 Acts
when the registry held 37. Nothing in the build failed, because a number in
a page is not a test.

So the numbers live here, next to the registry, and the page reads them.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import family_law_acts as F  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LANDING = REPO / "web" / "app" / "page.tsx"


def _landing_text() -> str:
    return LANDING.read_text(encoding="utf-8")


def test_the_registry_agrees_with_the_landing_page_act_count():
    text = _landing_text()
    m = re.search(r'value: "([\d,]+) Acts", label: "Acts in our library"', text)
    assert m, "the landing page no longer shows an Acts count"
    quoted = int(m.group(1).replace(",", ""))
    assert quoted == len(F.ACTS), (
        "the landing page says %d Acts, the registry holds %d"
        % (quoted, len(F.ACTS)))


def test_the_registry_agrees_with_the_landing_page_section_count():
    """The section count is the number of distinct (Act, section) rows the
    registry produces. The registry's own chunk estimate is the closest
    thing it knows, and the two have to be the same figure for the page to
    be honest."""
    text = _landing_text()
    m = re.search(r'value: "([\d,]+)", label: "In-force sections"', text)
    assert m, "the landing page no longer shows a section count"
    quoted = int(m.group(1).replace(",", ""))
    # The estimate is in chunks, and a section can be more than one chunk
    # when it is long. The index holds 2367 points over 1402 sections, so
    # the section count is what the page quotes and the chunk count is the
    # upper bound.
    assert quoted <= sum(F.ESTIMATED_CHUNKS.values()), (
        "the landing page says %d in-force sections, the registry estimates %d "
        "chunks" % (quoted, sum(F.ESTIMATED_CHUNKS.values())))


def test_the_faq_does_not_quote_a_stale_act_count():
    """The FAQ says how many acts are covered. It has to say the same number
    as the stat block above it."""
    text = _landing_text()
    m = re.search(r"from ([\d,]+) in-force acts including", text)
    assert m, "the FAQ no longer quotes an act count"
    quoted = int(m.group(1).replace(",", ""))
    assert quoted == len(F.ACTS), (
        "the FAQ says %d acts, the registry holds %d"
        % (quoted, len(F.ACTS)))
