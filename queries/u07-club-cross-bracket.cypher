// U7 — Cross-bracket club traversal: all opponents faced by ANY team of
// club C, across men's senior/U19/U17/women's/etc. — the query that most
// justifies the Club/Team split (design Decision 3 / AC18).
// Params: clubId (e.g. "fc-koebenhavn")
// Shape: one row per (own team, opponent, match) — spans every bracket the
// club fields a team in, in one query.
MATCH (c:Club {clubId: $clubId})-[:HAS_TEAM]->(t:Team)-[p:PLAYED_IN]->(m:Match)<-[q:PLAYED_IN]-(o:Team)
WHERE o <> t
RETURN
  t.teamId AS ownTeamId,
  t.bracket AS ownBracket,
  o.teamId AS opponentTeamId,
  o.name AS opponentName,
  o.bracket AS opponentBracket,
  p.side AS side,
  p.goalsFor AS goalsFor,
  p.goalsAgainst AS goalsAgainst,
  m.date AS date
ORDER BY t.bracket, m.date;
