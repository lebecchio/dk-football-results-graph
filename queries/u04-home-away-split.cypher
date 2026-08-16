// U4 — Team X's record split by home vs away.
// Params: teamId
// Shape: two rows (HOME, AWAY), each with played/won/drawn/lost/goals.
MATCH (t:Team {teamId: $teamId})-[p:PLAYED_IN]->(m:Match)
WHERE p.goalsFor IS NOT NULL
RETURN
  p.side AS side,
  count(*) AS played,
  sum(CASE WHEN p.outcome = 'WIN' THEN 1 ELSE 0 END) AS won,
  sum(CASE WHEN p.outcome = 'DRAW' THEN 1 ELSE 0 END) AS drawn,
  sum(CASE WHEN p.outcome = 'LOSS' THEN 1 ELSE 0 END) AS lost,
  sum(p.goalsFor) AS goalsFor,
  sum(p.goalsAgainst) AS goalsAgainst,
  sum(p.points) AS points
ORDER BY side;
