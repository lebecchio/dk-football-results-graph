// U6 — Degrees of separation: shortest path of "played against" hops
// between team X and team Y, including across tiers where playoff
// structures connect them.
// Params: teamAId, teamBId
// Shape: one row — the hop count and the team names along the path.
// Trivial with the derived PLAYED_AGAINST layer (also expressible without
// it via [:PLAYED_IN*..12] through Match nodes — see the no-derive variant).
MATCH path = shortestPath(
  (a:Team {teamId: $teamAId})-[:PLAYED_AGAINST*..6]-(b:Team {teamId: $teamBId})
)
RETURN
  length(path) AS hops,
  [n IN nodes(path) WHERE n:Team | n.name] AS teamsAlongPath;
