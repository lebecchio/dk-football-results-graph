"""dkfr — Danish football (DBU) results scraper -> Neo4j graph, 2025/26 season.

`__version__` is a pinned constant (not `git describe`), stamped as `scraperVersion`
on every normalized record. It must NOT change based on working-tree state, or
AC7 (byte-identical re-parse of a warm cache) would break on every dirty tree.
"""

__version__ = "0.1.0"
