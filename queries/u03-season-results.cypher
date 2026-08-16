// U3 — Team X's full season results ordered by date, with W/D/L (outcome)
// and a running goal difference.
// Params: teamId
// Shape: one row per match plus a running goal-difference total computed
// with reduce() over the chronologically-collected list — no APOC needed.
MATCH (t:Team {teamId: $teamId})-[p:PLAYED_IN]->(m:Match)<-[q:PLAYED_IN]-(o:Team)
WHERE o <> t
WITH t, m, p, o
ORDER BY m.date
WITH t, collect({
  date: m.date, opponent: o.name, side: p.side, goalsFor: p.goalsFor,
  goalsAgainst: p.goalsAgainst, outcome: p.outcome, matchKey: m.matchKey
}) AS results
UNWIND range(0, size(results) - 1) AS i
WITH results[i] AS row,
     reduce(
       gd = 0, r IN results[0..i+1] |
       gd + coalesce(r.goalsFor, 0) - coalesce(r.goalsAgainst, 0)
     ) AS runningGoalDifference
RETURN row.date AS date, row.opponent AS opponent, row.side AS side,
       row.goalsFor AS goalsFor, row.goalsAgainst AS goalsAgainst,
       row.outcome AS outcome, runningGoalDifference, row.matchKey AS matchKey
ORDER BY date;
