// U5 (alternate) — same result as u05-common-opponents.cypher, without
// relying on the derived PLAYED_AGAINST layer — via two PLAYED_IN 2-hop
// patterns + list intersection. Documented both ways per the design
// ("Both documented" in the query-set table).
// Params: teamAId, teamBId
MATCH (a:Team {teamId: $teamAId})-[:PLAYED_IN]->(:Match)<-[:PLAYED_IN]-(oppA:Team)
WHERE oppA <> a
WITH a, collect(DISTINCT oppA) AS aOpponents
MATCH (b:Team {teamId: $teamBId})-[:PLAYED_IN]->(:Match)<-[:PLAYED_IN]-(oppB:Team)
WHERE oppB <> b
WITH aOpponents, collect(DISTINCT oppB) AS bOpponents
UNWIND [x IN aOpponents WHERE x IN bOpponents] AS common
RETURN DISTINCT common.teamId AS opponentTeamId, common.name AS opponentName
ORDER BY opponentName;
