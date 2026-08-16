// cypher/validation.cypher — post-load invariant assertions (spec AC13,
// design "Loader-enforced invariants"). Each query returns VIOLATING rows;
// an empty result means the check passes. Neo4j Community Edition cannot
// enforce these itself (only uniqueness — spec C10), so they are checked
// here, after every load, by dkfr.load.validate / `dkfr validate`.
//
// Each block is preceded by a `// NAME: <snake_case_name>` marker that
// dkfr.load.validate parses to associate a human-readable name with its
// query and result — keep that marker directly above its query, one query
// per `;`-terminated block.

// NAME: match_has_exactly_two_sides
// Every Match must have exactly one HOME and one AWAY PLAYED_IN edge, from
// two distinct teams.
MATCH (m:Match)
OPTIONAL MATCH (m)<-[p:PLAYED_IN]-(t:Team)
WITH m, count(p) AS sideCount,
     count(CASE WHEN p.side = 'HOME' THEN 1 END) AS homeCount,
     count(CASE WHEN p.side = 'AWAY' THEN 1 END) AS awayCount,
     collect(DISTINCT t.teamId) AS teamIds
WHERE sideCount <> 2 OR homeCount <> 1 OR awayCount <> 1 OR size(teamIds) <> 2
RETURN m.matchKey AS matchKey, sideCount, homeCount, awayCount, teamIds
LIMIT 1000;

// NAME: played_in_goals_are_symmetric
// For every match, the home side's goalsFor must equal the away side's
// goalsAgainst, and vice versa (R-4: single-writer discipline, checked).
MATCH (home:Team)-[p:PLAYED_IN {side: 'HOME'}]->(m:Match)<-[q:PLAYED_IN {side: 'AWAY'}]-(away:Team)
WHERE p.goalsFor IS NOT NULL AND q.goalsFor IS NOT NULL
  AND (p.goalsFor <> q.goalsAgainst OR q.goalsFor <> p.goalsAgainst)
RETURN m.matchKey AS matchKey, p.goalsFor AS homeGoalsFor, q.goalsAgainst AS awayGoalsAgainst
LIMIT 1000;

// NAME: played_in_outcome_and_points_agree_with_goals
// outcome/points on each PLAYED_IN edge must be internally consistent with
// its own goalsFor/goalsAgainst.
MATCH (t:Team)-[p:PLAYED_IN]->(m:Match)
WHERE p.goalsFor IS NOT NULL AND p.goalsAgainst IS NOT NULL
  AND (
    (p.goalsFor > p.goalsAgainst AND (p.outcome <> 'WIN' OR p.points <> 3)) OR
    (p.goalsFor = p.goalsAgainst AND (p.outcome <> 'DRAW' OR p.points <> 1)) OR
    (p.goalsFor < p.goalsAgainst AND (p.outcome <> 'LOSS' OR p.points <> 0))
  )
RETURN m.matchKey AS matchKey, t.teamId AS teamId, p.goalsFor, p.goalsAgainst, p.outcome, p.points
LIMIT 1000;

// NAME: every_team_has_exactly_one_club
// Every Team must have exactly one incoming HAS_TEAM edge from a Club.
MATCH (t:Team)
OPTIONAL MATCH (c:Club)-[:HAS_TEAM]->(t)
WITH t, count(c) AS clubCount
WHERE clubCount <> 1
RETURN t.teamId AS teamId, clubCount
LIMIT 1000;

// NAME: every_match_has_exactly_one_stage
// Every Match must have exactly one outgoing IN_STAGE edge.
MATCH (m:Match)
OPTIONAL MATCH (m)-[:IN_STAGE]->(s:Stage)
WITH m, count(s) AS stageCount
WHERE stageCount <> 1
RETURN m.matchKey AS matchKey, stageCount
LIMIT 1000;

// NAME: match_scalars_agree_with_stage
// Match's denormalized scalar copies (Decision 1) must equal their source
// Stage's values — drift here is a loader bug, and this is the check that
// catches it.
MATCH (m:Match)-[:IN_STAGE]->(s:Stage)
WHERE m.puljeId <> s.puljeId OR m.phase <> s.phase OR m.tier <> s.tier
   OR m.bracket <> s.bracket OR m.season <> s.season OR m.competitionId <> s.competitionId
RETURN m.matchKey AS matchKey, m.puljeId AS matchPuljeId, s.puljeId AS stagePuljeId
LIMIT 1000;

// NAME: no_orphan_team_nodes
// Every Team must participate in at least one match or standing (a roster
// entry with zero matches and zero standings rows would be an orphan).
MATCH (t:Team)
WHERE NOT (t)-[:PLAYED_IN]->() AND NOT (t)-[:PARTICIPATED_IN]->()
RETURN t.teamId AS teamId
LIMIT 1000;

// NAME: no_orphan_venue_nodes
// Every Venue must have at least one match played at it.
MATCH (v:Venue)
WHERE NOT (v)<-[:PLAYED_AT]-()
RETURN v.venueKey AS venueKey
LIMIT 1000;

// NAME: every_stage_has_a_competition
// Every Stage's competitionId must resolve to a real Competition node
// (checked via the scalar property, since there is no direct Stage->
// Competition edge in this schema — Decision 1 deliberately routes that
// path through Season).
MATCH (s:Stage)
WHERE NOT EXISTS {
  MATCH (c:Competition {competitionId: s.competitionId})
}
RETURN s.puljeId AS puljeId, s.competitionId AS competitionId
LIMIT 1000;
