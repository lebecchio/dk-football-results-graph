// U5 — Common opponents of team X and team Y (2-hop intersection) — the
// basis of "who has a comparable schedule".
// Params: teamAId, teamBId
// Shape: one row per shared opponent, with each side's result against it.
// Uses the derived PLAYED_AGAINST layer (also expressible via two PLAYED_IN
// 2-hop patterns + list intersection — see queries/u05-common-opponents-no-derive.cypher).
MATCH (a:Team {teamId: $teamAId})-[:PLAYED_AGAINST]-(common:Team)-[:PLAYED_AGAINST]-(b:Team {teamId: $teamBId})
WHERE common <> a AND common <> b
RETURN DISTINCT common.teamId AS opponentTeamId, common.name AS opponentName
ORDER BY opponentName;
