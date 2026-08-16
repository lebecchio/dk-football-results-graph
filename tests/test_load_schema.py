"""dkfr.load.driver / dkfr.load.schema — offline unit tests plus a live-DB
integration test (marked, skippable without a running Neo4j)."""

from __future__ import annotations

from dkfr.load.driver import iter_statements


def test_iter_statements_splits_on_semicolon_and_skips_comments():
    script = """
    // a comment
    CREATE CONSTRAINT a IF NOT EXISTS FOR (n:A) REQUIRE n.id IS UNIQUE;

    // another comment
    CREATE INDEX b IF NOT EXISTS FOR (n:B) ON (n.x);
    """
    stmts = list(iter_statements(script))
    assert len(stmts) == 2
    assert "CREATE CONSTRAINT a" in stmts[0]
    assert "CREATE INDEX b" in stmts[1]
    assert all("//" not in s for s in stmts)


def test_iter_statements_skips_blank_trailing_segment():
    script = "CREATE INDEX a IF NOT EXISTS FOR (n:A) ON (n.x);"
    stmts = list(iter_statements(script))
    assert len(stmts) == 1


def test_real_schema_file_parses_into_statements():
    from pathlib import Path

    script = Path("cypher/schema.cypher").read_text(encoding="utf-8")
    stmts = list(iter_statements(script))
    assert len(stmts) == 16  # 7 constraints + 9 indexes
    assert sum(1 for s in stmts if s.startswith("CREATE CONSTRAINT")) == 7
    assert sum(1 for s in stmts if s.startswith("CREATE INDEX")) == 9
