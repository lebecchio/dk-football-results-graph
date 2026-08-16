// U10 — Derived standings: reconstruct a pulje's table from its matches,
// for comparison against the scraped stillingFuld table (validation, AC8).
// Params: puljeId
// Shape: one row per team, ranked by points/goal-difference — compare
// against the PARTICIPATED_IN edge for the same Stage (T14's
// reconciliation report does this comparison programmatically).
MATCH (t:Team)-[p:PLAYED_IN]->(m:Match)-[:IN_STAGE]->(s:Stage {puljeId: $puljeId})
WHERE p.goalsFor IS NOT NULL
WITH t, s,
     count(*) AS played,
     sum(p.points) AS points,
     sum(p.goalsFor) AS goalsFor,
     sum(p.goalsAgainst) AS goalsAgainst,
     sum(CASE WHEN p.outcome = 'WIN' THEN 1 ELSE 0 END) AS won,
     sum(CASE WHEN p.outcome = 'DRAW' THEN 1 ELSE 0 END) AS drawn,
     sum(CASE WHEN p.outcome = 'LOSS' THEN 1 ELSE 0 END) AS lost
RETURN
  t.teamId AS teamId,
  t.name AS teamName,
  played,
  won,
  drawn,
  lost,
  goalsFor,
  goalsAgainst,
  goalsFor - goalsAgainst AS goalDifference,
  points
ORDER BY points DESC, goalDifference DESC, goalsFor DESC;
