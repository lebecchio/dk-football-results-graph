// cypher/derive.cypher — rebuilds the derived PLAYED_AGAINST projection
// (design Decision, OQ-1: yes). Full drop-and-rebuild, so re-running is
// idempotent by construction (dkfr derive can be run any number of times
// with the same result, given the same underlying PLAYED_IN data).
//
// Stored once per unordered team pair (lower teamId -> higher teamId, by
// string comparison) and always queried with an undirected pattern
// `(a)-[:PLAYED_AGAINST]-(b)` — Neo4j relationships are physically
// directed, but this makes it behave as the undirected edge the design's
// schema reference shows: (:Team)-[:PLAYED_AGAINST {matchCount}]-(:Team).

// NAME: drop_played_against
MATCH ()-[r:PLAYED_AGAINST]->()
DELETE r;

// NAME: rebuild_played_against
MATCH (a:Team)-[:PLAYED_IN]->(m:Match)<-[:PLAYED_IN]-(b:Team)
WHERE a.teamId < b.teamId
WITH a, b, count(DISTINCT m) AS matchCount
MERGE (a)-[r:PLAYED_AGAINST]->(b)
SET r.matchCount = matchCount;
