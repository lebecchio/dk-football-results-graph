// U8 — All matches played at venue V.
// Params: venueKey (e.g. "broendby-stadion")
// Shape: one row per match at the venue, chronological.
MATCH (v:Venue {venueKey: $venueKey})<-[:PLAYED_AT]-(m:Match)
MATCH (home:Team)-[:PLAYED_IN {side: 'HOME'}]->(m)
MATCH (away:Team)-[:PLAYED_IN {side: 'AWAY'}]->(m)
RETURN
  m.date AS date,
  home.name AS homeTeam,
  away.name AS awayTeam,
  m.totalGoals AS totalGoals,
  m.status AS status,
  m.matchKey AS matchKey
ORDER BY date;
