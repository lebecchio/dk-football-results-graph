// U2 — Head-to-head: every match between team A and team B, both legs,
// chronologically.
// Params: teamAId, teamBId (e.g. "dbu:16162", "dbu:52769")
// Shape: one row per match, oriented from A's perspective. Single pattern,
// no UNION, no CASE on relationship type (AC17).
MATCH (a:Team {teamId: $teamAId})-[pa:PLAYED_IN]->(m:Match)<-[pb:PLAYED_IN]-(b:Team {teamId: $teamBId})
RETURN
  m.date AS date,
  a.name AS teamA,
  pa.side AS teamASide,
  pa.goalsFor AS teamAGoals,
  b.name AS teamB,
  pb.goalsFor AS teamBGoals,
  pa.outcome AS teamAOutcome,
  m.hasPenalties AS hasPenalties,
  m.matchKey AS matchKey
ORDER BY m.date;
