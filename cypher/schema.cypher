// cypher/schema.cypher — uniqueness constraints + indexes, all IF NOT EXISTS
// (spec R3.6/AC12). Applied before any data load. Neo4j Community Edition
// only supports uniqueness constraints and standard/range indexes — it
// cannot enforce existence, node-key, or property-type constraints (spec
// C10), so cardinality invariants (every match has exactly one home and one
// away team, etc.) are enforced by the loader and checked by
// cypher/validation.cypher, not by the schema itself.
//
// See docs/schema/model.md for the human-facing label/relationship catalog
// this file must stay in sync with.

// --- Uniqueness constraints (one per business key) ---

CREATE CONSTRAINT club_id_unique IF NOT EXISTS
FOR (c:Club) REQUIRE c.clubId IS UNIQUE;

CREATE CONSTRAINT team_id_unique IF NOT EXISTS
FOR (t:Team) REQUIRE t.teamId IS UNIQUE;

CREATE CONSTRAINT match_key_unique IF NOT EXISTS
FOR (m:Match) REQUIRE m.matchKey IS UNIQUE;

CREATE CONSTRAINT stage_pulje_id_unique IF NOT EXISTS
FOR (s:Stage) REQUIRE s.puljeId IS UNIQUE;

CREATE CONSTRAINT season_id_unique IF NOT EXISTS
FOR (s:Season) REQUIRE s.seasonId IS UNIQUE;

CREATE CONSTRAINT competition_id_unique IF NOT EXISTS
FOR (c:Competition) REQUIRE c.competitionId IS UNIQUE;

CREATE CONSTRAINT venue_key_unique IF NOT EXISTS
FOR (v:Venue) REQUIRE v.venueKey IS UNIQUE;

// --- Indexes (hot-path filtering — U1/U3/U11/U8) ---

CREATE INDEX match_date_idx IF NOT EXISTS FOR (m:Match) ON (m.date);
CREATE INDEX match_total_goals_idx IF NOT EXISTS FOR (m:Match) ON (m.totalGoals);
CREATE INDEX match_goal_margin_idx IF NOT EXISTS FOR (m:Match) ON (m.goalMargin);
CREATE INDEX match_bracket_idx IF NOT EXISTS FOR (m:Match) ON (m.bracket);
CREATE INDEX match_phase_idx IF NOT EXISTS FOR (m:Match) ON (m.phase);
CREATE INDEX team_name_idx IF NOT EXISTS FOR (t:Team) ON (t.name);
CREATE INDEX club_name_idx IF NOT EXISTS FOR (c:Club) ON (c.name);

// Relationship-property indexes — supported on Community since 5.0 (design
// tech-stack rationale for pinning 5.26 LTS).
CREATE INDEX played_in_side_idx IF NOT EXISTS FOR ()-[p:PLAYED_IN]-() ON (p.side);
CREATE INDEX played_in_goals_for_idx IF NOT EXISTS FOR ()-[p:PLAYED_IN]-() ON (p.goalsFor);
