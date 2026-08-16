"""ParseIssue — the record of anything a parser couldn't fully interpret.

Nothing is ever silently dropped (spec R2.9/AC11): every parser function in
this package returns `(records, issues)`, and issues are collected across
the whole run into data/reports/parse-issues.json.
"""

from __future__ import annotations

from pydantic import BaseModel

from dkfr.vocab import ParseIssueSeverity


class ParseIssue(BaseModel):
    sourceUrl: str
    rowIndex: int
    rawRow: str
    reason: str
    severity: ParseIssueSeverity
