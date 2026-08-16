// U9 — A team's path through the season's phases: which puljer it
// appeared in (e.g. Grundspil -> Mesterskabsspil), and its record within
// each. Depends on `phase` being modelled on Stage (AC19: must distinguish
// a Superliga team's Grundspil record from its Mesterskabsspil record).
// Params: teamId
// Shape: one row per Stage the team played in.
MATCH (t:Team {teamId: $teamId})-[p:PLAYED_IN]->(m:Match)-[:IN_STAGE]->(s:Stage)
WHERE p.goalsFor IS NOT NULL
RETURN
  s.puljeId AS puljeId,
  s.phase AS phase,
  s.groupLabel AS groupLabel,
  count(*) AS played,
  sum(CASE WHEN p.outcome = 'WIN' THEN 1 ELSE 0 END) AS won,
  sum(CASE WHEN p.outcome = 'DRAW' THEN 1 ELSE 0 END) AS drawn,
  sum(CASE WHEN p.outcome = 'LOSS' THEN 1 ELSE 0 END) AS lost,
  sum(p.goalsFor) AS goalsFor,
  sum(p.goalsAgainst) AS goalsAgainst,
  sum(p.points) AS points,
  min(m.date) AS firstMatchDate
ORDER BY firstMatchDate;
