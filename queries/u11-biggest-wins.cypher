// U11 — Biggest wins / highest-scoring matches, filterable by tier and
// bracket. Index-backed node scan, no traversal (Match.goalMargin and
// Match.totalGoals are both indexed — cypher/schema.cypher).
// Params: bracket (e.g. "MEN_SENIOR"), tier (integer, scoped WITHIN that
// bracket per Decision 1 / Risk R-8 — always filter both together, tier is
// not comparable across brackets), limit (integer, default 10 if omitted —
// pass explicitly via queries/runner.py's --param)
MATCH (m:Match)
WHERE m.bracket = $bracket AND m.tier = $tier AND m.totalGoals IS NOT NULL
MATCH (home:Team)-[ph:PLAYED_IN {side: 'HOME'}]->(m)
MATCH (away:Team)-[pa:PLAYED_IN {side: 'AWAY'}]->(m)
RETURN
  m.date AS date,
  home.name AS homeTeam,
  ph.goalsFor AS homeGoals,
  away.name AS awayTeam,
  pa.goalsFor AS awayGoals,
  m.totalGoals AS totalGoals,
  m.goalMargin AS goalMargin,
  m.matchKey AS matchKey
ORDER BY m.goalMargin DESC, m.totalGoals DESC
LIMIT toInteger($limit);
