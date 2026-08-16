// U1 — All opponents of team X in 2025/26, with each result and home/away side.
// Params: teamId (e.g. "dbu:16162")
// Shape: one row per match the team played — opponent, side, own/opponent
// goals, date, status. Single pattern, no UNION, no CASE on relationship
// type (AC17).
MATCH (t:Team {teamId: $teamId})-[p:PLAYED_IN]->(m:Match)<-[q:PLAYED_IN]-(o:Team)
WHERE o <> t
RETURN
  o.teamId AS opponentTeamId,
  o.name AS opponentName,
  p.side AS side,
  p.goalsFor AS goalsFor,
  p.goalsAgainst AS goalsAgainst,
  p.outcome AS outcome,
  m.date AS date,
  m.status AS status,
  m.matchKey AS matchKey
ORDER BY m.date;
