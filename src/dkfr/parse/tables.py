"""Shared low-level HTML extraction helpers, used by fixtures.py/standings.py/
teams.py.

Design note (spec R2.9, discovery-notes.md): DBU's pulje pages render every
row TWICE — once in a `hide-on-mobile` desktop cell set, once again in an
`only-on-mobile` mobile card with the same data as flat text. Naive
`get_text()` extraction over a whole `<tr>` concatenates both, producing
garbage (confirmed empirically in T3). Every extractor in this package reads
ONLY the `hide-on-mobile` cells and must never call `.get_text()` on a row
or table directly.

Also per discovery-notes.md: DBU uses `<a href>` navigation on some tables
(kampprogramFuld team/match links) and `onclick="window.location=...'"` row
navigation on others (holdoversigt, multi-pulje Raekke pages). Both are
supported here.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

ONCLICK_HREF_RE = re.compile(r"window\.location(?:\.href)?\s*=\s*'([^']+)'")


def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def desktop_cells(row: Tag) -> list[Tag]:
    """Return only the `hide-on-mobile` <td> cells of a row — never the
    `only-on-mobile` duplicate. If the row has no class-differentiated cells
    at all (a simpler table shape, e.g. some standings tables), fall back to
    all <td> children."""
    cells = row.find_all("td", class_="hide-on-mobile", recursive=False)
    if cells:
        return cells
    all_tds = row.find_all("td", recursive=False)
    mobile_only = row.find_all("td", class_="only-on-mobile", recursive=False)
    if mobile_only and len(mobile_only) < len(all_tds):
        return [td for td in all_tds if td not in mobile_only]
    return all_tds


def cell_text(cell: Tag) -> str:
    """Text of a single cell, with nested-node boundaries preserved as
    whitespace (so e.g. a penalty badge's tooltip doesn't fuse into the
    preceding digit) — but NOT a full-row get_text() call."""
    return cell.get_text(" ", strip=True)


def direct_text(el: Tag) -> str:
    """Only `el`'s own direct NavigableString children, ignoring any nested
    descendant elements entirely. Needed for the score container divs: a
    penalty shootout's `.penalty-result-badge` can be nested INSIDE
    `.home-score`/`.away-score` either before or after the actual goal-count
    text node (confirmed both orders occur — see discovery-notes.md), so a
    plain `get_text()` interleaves the badge's tooltip text with the digit
    depending on DOM order. Reading only direct text children sidesteps the
    badge subtree completely, regardless of its position."""
    return "".join(
        t for t in el.find_all(string=True, recursive=False)
    ).strip()


def cell_link(cell: Tag) -> str | None:
    """The first href or onclick-navigation target found in a cell (checking
    the cell itself before its descendants — confirmed necessary: stillingFuld
    puts `onclick="window.location = '...'"` directly on the `<td>`, not on a
    nested element), or None."""
    a = cell.find("a", href=True)
    if a is not None:
        return a["href"]
    if cell.get("onclick"):
        m = ONCLICK_HREF_RE.search(cell["onclick"])
        if m:
            return m.group(1)
    el = cell.find(attrs={"onclick": True})
    if el is not None:
        m = ONCLICK_HREF_RE.search(el["onclick"])
        if m:
            return m.group(1)
    return None


def row_link(row: Tag) -> str | None:
    """The onclick-navigation target of a whole <tr>, if any (used by
    kampprogramFuld's match-click rows and Raekke's pulje-picker rows)."""
    onclick = row.get("onclick")
    if onclick:
        m = ONCLICK_HREF_RE.search(onclick)
        if m:
            return m.group(1)
    return None


TEAM_ID_RE = re.compile(r"/resultater/hold/(\d+)_(\d+)")
MATCH_ID_RE = re.compile(r"/resultater/kamp/(\d+)_(\d+)")


def extract_team_id(href: str | None) -> str | None:
    if not href:
        return None
    m = TEAM_ID_RE.search(href)
    return m.group(1) if m else None


def extract_match_id(href: str | None) -> str | None:
    if not href:
        return None
    m = MATCH_ID_RE.search(href)
    return m.group(1) if m else None
