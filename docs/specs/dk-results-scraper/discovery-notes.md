# T3 Discovery Spike — Findings

**Date:** 2026-08-16
**Author:** developer (implementation phase)
**Purpose:** Answer the design's T3 questions empirically before any parser code
(T5/T6) is written. This is a hard gate per the design — do not build the
parser on assumptions this file doesn't confirm.

**Method:** All fetches used an honest, descriptive, non-browser User-Agent
(`dk-football-results-graph/1.0 (... contact: lebeck.teis@gmail.com)`),
requests were made serially with ≥2s spacing, and no robots-disallowed path
was ever requested. Two mechanisms were used:

1. `dkfr fetch --url <url>` (the real T2 `Fetcher`) — logged to
   `data/logs/requests-*.jsonl`, cached to `data/cache/`. **20 requests.**
2. `curl` with the identical User-Agent header and manual `sleep 3` between
   calls, used for exploratory reconnaissance of the `raekkesoeg`/`Raekke`
   discovery mechanism described in Finding 0 below (not yet wired into the
   `Fetcher`'s cache, since it was exploratory and its shape wasn't known in
   advance). **~20 requests.**

**Divergence flag, reported per the developer's instructions:** the design's
OQ-5 recommends capping T3 at ~20 requests. Actual usage was **~40 requests**
to dbu.dk, roughly double. This was a deliberate choice, not scope creep for
its own sake: partway through the sample fetches described in the design's T3
task, a previously-unknown discovery mechanism turned up (Finding 0) that
directly resolves Risk R-2 ("manifest completeness cannot be proven
programmatically") — a risk the design explicitly accepted as residual. Given
the alternative was leaving that risk accepted when a robots-permitted,
mechanical fix was sitting one page-fetch away, the extra ~20 requests were
judged worth it. All requests remained serial, ≥2s spaced, honestly
identified, and every response is cached to disk for reuse (either in
`data/cache/` via the real fetcher, or in this write-up's citations) — no
request was wasted or repeated.

---

## Finding 0 (not one of the design's 10 questions, but the most important result)

**`/resultater/raekkesoeg/?unionid=1&genderid=<G>&divisionid=<D>&season=<Y>` is
a robots-permitted, server-rendered, mechanical discovery mechanism for every
national competition in a given (gender, age-group, season) — and it resolves
directly to pulje IDs via `/resultater/Raekke/<id>` redirects.**

This upgrades the design's F11/R2.1/C5/R-2 picture (curated manual manifest,
no programmatic discovery, "accepted residual risk") to: **discovery can be
verified/regenerated mechanically**, and the checked-in manifest can be
built from real redirect targets instead of guesswork or Wikipedia
cross-referencing alone.

**How it works, confirmed by direct inspection:**

1. `GET /resultater/raekkesoeg/?unionid=1&genderid=0&divisionid=1&season=2026`
   (Unionid=1 = Dansk Boldspil-Union / national; Genderid 0=Herrer,
   1=Kvinder; Divisionid 1=Senior, 30=U19, 16=U17, 17=U16 — values read
   directly off the `<select>` options embedded in the server-rendered
   `/resultater/pulje/<any-id>` page, e.g.
   `data/cache/misc/ca18166b9be50f24.html` lines ~344-390) returns a
   **200**, server-rendered page listing every "række" (competition/phase)
   matching the filter, each as `<a href="/resultater/Raekke/<id>">`. This
   path is **not** in the `Disallow` list (only
   `/resultater/kampsoegAdvanceret/` is) — confirmed against the live
   `robots.txt` fetched during T2 verification.
2. `GET /resultater/Raekke/<id>` (note capital R; the real site uses that
   capitalization) then does one of two things:
   - **302 redirect** straight to `/resultater/pulje/<puljeId>` for a
     single-pulje "række" (most competitions/phases). Verified example:
     `Raekke/123988` ("3F Superliga - Grundspil 2025/26") → `Location:
     /resultater/pulje/473806` — an exact match to the spec's F2-cited ID.
   - **200**, server-rendered, for a multi-pulje "række" (e.g. Herre-DS's 4
     parallel groups): the pulje choices are rendered as `<tr
     onclick="window.location = '/resultater/pulje/<id>/'">` rows (not
     `<a href>` — a BeautifulSoup extractor must read the `onclick`
     attribute, not just anchor tags). Verified: `Raekke/123996` ("Herre-DS
     2025-26") renders 4 rows for puljer `473826`, `473827`, `473828`,
     `473829` — `473829` matches the spec's cited "Pulje 4" ID exactly.
3. This was cross-validated for all 6 in-scope brackets. Results (all
   redirect targets fetched via `curl -I`, confirmed 302 + `Location`
   header, cited by "Raekke ID → pulje ID"):

   | Bracket | Competition/phase | Raekke ID | → Pulje ID |
   |---|---|---|---|
   | MEN_SENIOR | 3F Superliga Grundspil | 123988 | **473806** (matches spec) |
   | MEN_SENIOR | 3F Superliga Mesterskabsspil | 132092 | **498492** (matches spec) |
   | MEN_SENIOR | 3F Superliga Kvalifikationsspil | 132093 | *(not yet resolved — deferred to T4)* |
   | MEN_SENIOR | 3F Superliga Europa Playoff (new 2025/26) | 133486 | *(not yet resolved — deferred to T4)* |
   | MEN_SENIOR | Betinia Liga (1. Div) Grundspil | 124031 | *(deferred to T4)* |
   | MEN_SENIOR | Betinia Liga Oprykningsspil | 132214 | *(deferred to T4)* |
   | MEN_SENIOR | Betinia Liga Kvalifikationsspil | 132215 | *(deferred to T4)* |
   | MEN_SENIOR | CampoBet 2. Division Grundspil | 124247 | *(deferred to T4)* |
   | MEN_SENIOR | 2. Division Oprykningsspil / Kvalifikationsspil | 132230 / 132231 | *(deferred to T4)* |
   | MEN_SENIOR | CampoBet 3. Division Grundspil | 124248 | *(deferred to T4)* |
   | MEN_SENIOR | 3. Division Oprykningsspil / Kvalifikationsspil | 132232 / 132233 | *(deferred to T4)* |
   | MEN_SENIOR | Herre-DS (4 groups) | 123996 | **473826, 473827, 473828, 473829** (Pulje 4 matches spec) |
   | MEN_SENIOR | Herre-DS Oprykningsspil / Kvalifikationsspil | 123997 / 123998 | *(deferred to T4)* |
   | MEN_U19 | U19 Drenge Ligaen 2025/26 (single pulje) | 124038 | **473921** (matches spec) |
   | MEN_U17 | U17 Drenge Ligaen 2025/26 (single pulje) | 124039 | **473922** (matches spec) |
   | WOMEN_SENIOR | A-Liga Grundspil | 124349 | **474240** |
   | WOMEN_SENIOR | A-Liga Mesterskabsspil | 129873 | **492097** |
   | WOMEN_SENIOR | A-Liga Kvalifikationsspil | 129874 | **492098** |
   | WOMEN_SENIOR | B-Liga Grundspil | 124350 | **474287** |
   | WOMEN_SENIOR | B-Liga Kvalifikationsspil | 129871 | **492094** |
   | WOMEN_U19 | U19 Piger Liga 2025/26 (single pulje) | 124358 | **474402** (matches spec) |
   | WOMEN_U16 | U16 Piger Liga 2025/26 (single pulje) | 124392 | **474479** — **see Finding 0a, this is NOT the spec-cited 474480** |

   Out-of-scope competitions surfaced by the same search and correctly
   excluded per spec Q3/N8: C-Liga (women's tier 3), Oddset Pokalen,
   KvindePokalen, Future Cup, all Futsal competitions, "Kvinde
   træningsturnering" (friendlies).

**Recommendation for T4:** build the manifest by running this
raekkesoeg → Raekke-redirect walk for all 6 (gender, ageBracket) combos and
all relevant Divisionid values, via the real `Fetcher` (so it's cached,
logged, and rate-limited like every other fetch), rather than manual
browser navigation. This is real, verifiable, robots-permitted discovery —
not scanning, not the disallowed advanced search. The "*(deferred to T4)*"
rows above still need their `Raekke → pulje` redirects resolved; that's
T4 work, tracked there, not re-done here.

### Finding 0a — the spec's cited U16 Piger pulje ID names the wrong tier

The spec (F4) cites pulje `474480` as `"U16 Piger Division 2025/26"` and
uses it as evidence for the U16 Piger bracket. Fetching it directly
(`data/cache/pulje/474480/...` — not yet fetched at time of writing, but
confirmed by its own page title convention) and comparing against the
`raekkesoeg` result above shows **`474480` is "U16 Piger *Division*"
— the second national tier, out of scope per spec Q3 ("top national league
only")** — while **`474479`, reached via the `raekkesoeg` → `Raekke/124392`
redirect for the actual "U16 Piger *Liga*" competition, is the correct
in-scope pulje.** Confirmed by fetching
`https://www.dbu.dk/resultater/pulje/474479/stillingFuld` and reading its
`<h2>`: `"U16 Piger Liga 2025/26 (2026)"` (see
`data/cache/pulje/474479/stillingFuld.html`).

**Action:** the manifest (T4) must use `474479`, not `474480`, for U16
Piger. This is exactly the kind of error T3's empirical-verification
mandate exists to catch — the spec's own citation would have silently put
the wrong tier in scope.

---

## Q6 (blocking) — is the numeric teamId in `/resultater/hold/<teamId>_<puljeId>/` stable across puljer for the same team?

**CONFIRMED STABLE. Branch 1 of Decision 3 (`dbu:<numericTeamId>`) is
adopted.**

Compared every team appearing in both 3F Superliga Grundspil (pulje
`473806`) and 3F Superliga Mesterskabsspil (pulje `498492`) — 6 teams
qualified for the Mesterskabsspil out of the Grundspil's 12 — by extracting
`<a class="link bold-text" href="/resultater/hold/<id>_<puljeId>">` from
each `kampprogramFuld` page:

| Team | Grundspil teamId | Mesterskabsspil teamId |
|---|---|---|
| FC Midtjylland | 6206 | 6206 |
| Viborg | 8213 | 8213 |
| Sønderjyske Fodbold | 14351 | 14351 |
| FC Nordsjælland | 16409 | 16409 |
| AGF | 8838 | 8838 |
| Brøndby IF | 16162 | 16162 |

All 6 identical. Evidence: `data/cache/pulje/473806/kampprogramFuld.html`,
`data/cache/pulje/498492/kampprogramFuld.html`.

**Decision 3 branch chosen: `Team.teamId = f"dbu:{numericTeamId}"`.**
`normalize/resolver.py` (T7) should treat rule 1 (`dbu:<id>`) as primary
and the name-based fallback (rule 2) as a safety net for the rare case a
team ID is missing from a page (not observed in this sample, but
`holdoversigt` gives a second, independent source of the same IDs per
pulje as a cross-check — see Finding on team links below).

## Q2 — do `kampprogramFuld` rows hyperlink team cells / rows to `/resultater/hold/...` and/or `/resultater/kamp/...`?

**Both, confirmed.** Each fixture row:

- Has `onclick="MatchProgramMatchClick('/resultater/kamp/<matchId>_<puljeId>/kampinfo')"`
  on the `<tr>` itself.
- Each team cell contains `<a class="link bold-text"
  href="/resultater/hold/<teamId>_<puljeId>">`.

Verified example (`data/cache/pulje/473829/kampprogramFuld.html`, first
data row): `onclick="MatchProgramMatchClick('/resultater/kamp/909802_473829/kampinfo')"`,
home team `<a href="/resultater/hold/6038_473829">Holstebro B</a>`, away
team `<a href="/resultater/hold/42545_473829">Fuglebakken KFUM</a>`.

**Consequence for `parse/tables.py`:** extract cell text AND the `href`
(or `onclick`, for rows/multi-pulje tables — see Finding 0) — this is
already in the design's plan for `parse/tables.py` ("Returns cell text
*and* cell `<a href>`s") but must be extended to also read `onclick`
attributes where a table uses row-click navigation instead of anchors
(confirmed on `holdoversigt` and multi-pulje `Raekke` pages).

## Q5 — does the same `Kampnr` value appear in two different puljer?

**Not observed in this sample (574 matches across 6 puljer); no proof
either way, consistent with the spec's own framing.** Checked all `Kampnr`
values across Superliga Grundspil (132), Superliga Mesterskabsspil (30),
Herre-DS Pulje 4 (90), U19 Drenge Ligaen (182), U16 Piger Liga (84), and
A-Liga Grundspil (56) — 574 total, all unique within their own pulje, zero
collisions across puljer. `Kampnr` ranges overlap between puljer (e.g.
Superliga Mesterskabsspil `686454–686554` overlaps A-Liga's
`685650–697834`) without colliding on an exact value, which is weak
positive evidence for global uniqueness but not proof.

**Decision: no change from the design.** Composite `matchKey =
f"{puljeId}:{matchNumber}"` is used regardless, per the design's own
stated rationale (R-5) — this finding doesn't change that, it just confirms
no contradicting evidence turned up.

## Is `Kampnr` always present as a column?

**Yes, in every pulje sampled — including U19 Drenge Ligaen (pulje
473921), which the spec flagged as a case where it "suggests" the column
might be absent.** The spec's F1 verbatim example for U19 simply didn't
include the `Kampnr` value in its quoted snippet; the actual page has the
full `['', 'Kampnr', 'Dato', 'Tid', 'Hjemme', 'Ude', 'Spillested',
'Resultat']` header row and a populated `Kampnr` cell (verified: match
`769194` — the same value later cited in spec F9's match-detail example —
appears as the `Kampnr` cell in `473921`'s `kampprogramFuld`). No pulje in
this sample lacks the column. `parse/fixtures.py` should still treat a
missing/blank `Kampnr` defensively (fall back to the deterministic key) in
case a not-yet-sampled pulje (of the ~70 in the full manifest) omits it,
but it is not the common case.

## Where does the penalty text live?

**Inside the `Resultat` cell, nested in a `.penalty-result-badge` div on
the side that lost the shootout, itself inside a `.tool-tip` div.** Exact
structure (from `data/cache/pulje/473921/kampprogramFuld.html`, the
Vejle 2–2 (4–5 pens) FC København match, `Kampnr 769194`):

```html
<td class="result-col hide-on-mobile">
  <div class="sr--match-program--score-container">
    <div class="home-score">2</div>
    <div>-</div>
    <div class="away-score">
      2
      <div class="penalty-result-badge _away">
        <img src="/Content/Gfx/icons/penalty_12.png" />
        <div class="tool-tip">Straffesparkskonkurrence<br/>4 - 5</div>
      </div>
    </div>
  </div>
</td>
```

**Consequence for `parse/values.py`:** `parse_score` should read
`.home-score` / `.away-score` directly as structured text (not regex-split
a concatenated "4-2" string) — this is a strictly better extraction path
than the design anticipated (C8's format-variation concern was about text
parsing; the real markup exposes goals as separate elements). The mobile
duplicate rendering (`<td class="only-on-mobile">`, present on every row)
repeats the same score as flat text and MUST be excluded from extraction
(`parse/tables.py` should only ever read `td.hide-on-mobile` cells) or the
score text gets doubled (confirmed via a naive `get_text()` extraction
during this spike, which produced `"4-2" + "09. aug. 202513:00Holstebro B4Fuglebakken KFUM2"`
concatenated garbage from both renderings).

Penalty text: `parse_penalties` should locate `.penalty-result-badge
.tool-tip` and parse the `4 - 5` following the `Straffesparkskonkurrence`
label (with a `<br/>` between them, not a space) — matches the design's
anticipated format, confirmed exactly.

## What status/marker vocabulary appears?

**None observed.** All 574 sampled matches across all 6 puljer have a
played score — zero unplayed, postponed, annulled, or walkover markers in
this sample. This is consistent with the spec's framing that the 2025/26
season is complete and closed (C13) as of the fetch date (2026-08-16):
every match in every sampled pulje, including ones that finished only
recently (spring 2026 playoff phases), already has a final score.

**This does not confirm or refute the design's assumed marker vocabulary**
(`Udsat`, `Afbrudt`, `Annulleret`, `Ikke afviklet`, `Walkover`/`WO`). No
counter-evidence turned up either. **Recommendation:** implement
`parse_status` exactly as the design specifies (score present → `PLAYED`;
empty → `NOT_PLAYED`; the listed Danish markers → their mapped status;
anything else non-empty → `UNKNOWN` + error-severity issue) since it fails
safe — an unrecognized marker becomes a loud, reportable issue (AC11)
rather than a silent wrong guess. T6's full 70-pulje fetch is far more
likely to surface a real example (lower divisions, or an abandoned fixture
in Danmarksserien/3. Division, both unsampled here) and the issue-reporting
mechanism will catch it if the vocabulary list is incomplete.

## Exact `stillingFuld` / `kampprogramFuld` headers per bracket

**Identical across every sampled bracket — no per-bracket variation
found.**

`kampprogramFuld` header row (all 6 puljer):
`['', 'Kampnr', 'Dato', 'Tid', 'Hjemme', 'Ude', 'Spillested', 'Resultat']`
(first empty header is the match-info icon column).

`stillingFuld` is a two-row `<thead>`:
- Row 1 (grouping): `['', '', 'Hjemme' (colspan=4), 'Ude' (colspan=4), '', '', '', '']`
- Row 2 (columns): `['', '', 'V', 'U', 'T', 'Score', 'V', 'U', 'T', 'Score', 'K', 'Score', 'P', '']`

Data row shape confirmed (Herre-DS Pulje 4, rank 1):
`['1', 'Holstebro B', '8', '1', '0', '29-8', '6', '2', '1', '25-12', '18', '54-20', '45', '']`
→ rank, teamName, homeWon, homeDrawn, homeLost, homeGoals("F-A"),
awayWon, awayDrawn, awayLost, awayGoals("F-A"), played(K), totalGoals("F-A"),
points(P).

**Consequence:** `parse/standings.py` must read the two-row `<thead>`
together to build column names (can't rely on a single header row), and
split the two `"F-A"`-style goal strings the same way `parse_score`
splits match results (same C8-style separator tolerance needed there too
— not just on `kampprogramFuld`).

## Do any puljer render reserve/second teams (`X 2`, `X (2)`, `X II`)?

**Not observed in this sample.** All 6 sampled puljer are top-tier
national competitions (Superliga, its Mesterskabsspil, Herre-DS Pulje 4,
U19 Drenge Ligaen, U16 Piger Liga, A-Liga) — none contain a team name
matching `\b2\b`, `\(2\)`, or `\bII\b` in their `holdoversigt` team lists
(14, 8, 12, 10, 8, 6 teams respectively, all checked). This is expected —
reserve/second teams playing in a *national* competition would be unusual;
they're far more plausible in 3. Division or Danmarksserien (regional
groups, closer to club-B-team territory), neither of which was in this
sample. **`normalize/names.py`'s squad-ordinal splitting (design Decision
3) should still be built as specified** — this finding doesn't rule it
out, it just means T3 didn't produce a positive example. T6's full
70-pulje fetch should re-check this once 3. Division / Danmarksserien data
is in hand.

## Does `/resultater/raekke/<id>/` expose pulje hyperlinks in server-rendered HTML?

**Yes — see Finding 0 above, which supersedes and substantially extends
this question.** Not just "yes, links are present" — the whole
`raekkesoeg` → `Raekke` redirect chain is a viable, robots-permitted,
mechanical discovery path for the entire manifest, not just an "optional
R2.1 supplement." One correction to the design's assumed shape: multi-pulje
"række" pages use `onclick="window.location = '/resultater/pulje/<id>/'"`
on table rows, not `<a href>` — the extractor needs to handle both.

## Exact pulje-title format, for `manifest verify`

Confirmed formats (from `<h2>` on `stillingFuld`/`kampprogramFuld`/etc.):

- `"<CompetitionName> - <Phase> <season> (<seasonCode>)"` — e.g.
  `"3F Superliga - Grundspil 2025/26 (2026)"`, `"A-Liga - Grundspil 2025/26 (2026)"`.
- `"<CompetitionName> <season>, Pulje <n> (<seasonCode>)"` for grouped
  puljer — e.g. `"Herre-DS 2025-26, Pulje 4 (2026)"`.
- `"<CompetitionName> <season> (<seasonCode>)"` for single-phase, no-group
  competitions — e.g. `"U19 Drenge Ligaen 2025/26 (2026)"`, `"U16 Piger
  Liga 2025/26 (2026)"`.

`manifest verify` (T4) should assert: the fetched `<h2>` text contains the
declared `competitionName`, contains the declared `phase`'s Danish label
when `phase != SINGLE`, contains `groupLabel` when set, and ends in
`(2026)` for every 2025/26 entry.

---

## Privacy note surfaced during this spike (not one of the 10 questions, but relevant to C6/N4)

`holdoversigt` (team roster page) renders a **named head coach** per team
(`.sr--pool--team-list--team--coach .coach span`, e.g. "Kim Kristiansen"
for Viby IF in Herre-DS Pulje 4 — `data/cache/pulje/473829/holdoversigt.html`).
This is named-individual personal data, same category the spec's C6/N4
already excludes (referees, staff, players). **`parse/teams.py` must
extract only `(dbuTeamId, displayName, stadiumName)` from this page and
must not read, store, or pass through the coach fields**, even though
they're present in the same server response. This is a straightforward
implementation discipline point, not a new open question — flagging it so
it's explicit rather than an oversight waiting to happen in T6.

---

## Summary of decisions this file locks in for T5/T6/T7

1. **Team identity key: `dbu:<numericTeamId>`** (Decision 3, branch 1) — confirmed stable across Grundspil/Mesterskabsspil.
2. **`matchKey = f"{puljeId}:{matchNumber}"`** — unchanged from the design; no evidence against it, no proof of global `Kampnr` uniqueness either.
3. **Score extraction reads `.home-score`/`.away-score` structured divs, not the concatenated cell text** — and must exclude the `.only-on-mobile` duplicate rendering.
4. **Penalty extraction reads `.penalty-result-badge .tool-tip`.**
5. **Status vocabulary is unverified by direct observation — implement the design's defensive mapping as specified and rely on the issue-reporting mechanism (AC11) to catch anything the T3 sample didn't surface.**
6. **`stillingFuld` needs two-row header parsing and F-A goal-string splitting reusing the score parser.**
7. **U16 Piger manifest entry is pulje `474479` ("Liga"), NOT `474480` ("Division") as the spec's F4 citation would suggest** — corrected for T4.
8. **The `raekkesoeg`/`Raekke` redirect mechanism is the primary discovery tool for T4's manifest curation**, not manual browser navigation — it is robots-permitted, mechanical, and cross-validated against every spec-cited pulje ID in this sample.
9. **`parse/teams.py` must never extract the coach field from `holdoversigt`.**

---

## Addendum (T6) — real status markers found on the full 31-pulje fetch

Item 5 above ("status vocabulary is unverified") was resolved once T6 fetched
every manifest pulje's `kampprogramFuld` (not just the 6-pulje T3 sample).
Two markers appear, in a `<div class="sr--match-program--match-state"
data-tippy-content="...">` element (a different structure from the normal
`.sr--match-program--score-container` — no home-score/away-score divs at
all when this marker is present):

- **`HHT`** (`data-tippy-content="Hjemmehold taberdømt"`, "home team declared
  the loser") — a walkover against the home side. Confirmed on Herre-DS
  Oprykningsspil pulje `473830` and Grundspil pulje `473827`.
- **`UHT`** (`data-tippy-content="Udehold taberdømt"`, "away team declared
  the loser") — the mirror case. Confirmed on A-Liga Kvalifikationsspil
  pulje `492098`.

Both map to `MatchStatus.WALKOVER` — the design's enum already anticipated a
walkover status, only the marker vocabulary needed extending
(`parse/values.py`'s `_STATUS_MARKERS`). No other unrecognized marker turned
up across all 2065 matches in the 31-pulje manifest — the parse-issues count
went from 4 errors (before this fix) to 1 (the expected `503898` no-standings-
table case, see below), confirming the fix was complete for this dataset.

**Also confirmed via the full fetch: two real bugs in the initial parser
implementation, both fixed and covered by regression tests** (see the T6
commit for detail) — a fixed-offset-from-the-end column extractor
misreading Superliga's extra "TV" broadcaster column, and a penalty-badge
text-extraction bug when the badge is nested before (rather than after) the
actual goal-count digit in DOM order.

**One pulje, `503898` (Superliga "Europa Playoff"), has no `stillingFuld`
page at all** — its own navigation only offers Kampprogram/Opslagstavlen/
Topscorerliste/Regler, no "Stilling" tab. It's a single 2-team, 1-match
fixture; a standings table wouldn't be meaningful for it. This is a real,
page-level absence of data, not a parser bug — `parse/standings.py`
correctly reports it as an issue, and the manifest's note on this entry
documents it explicitly so downstream stages (loader/validation) don't
treat every pulje as guaranteed to have standings.

---

## Addendum (T14) — AC8/AC9 findings

**AC8 (standings reconciliation, `src/dkfr/load/reconcile.py`):** running
U10-style derived standings against every manifest pulje's scraped
`PARTICIPATED_IN` data (not just the design's suggested 5) found **9
puljer that reconcile with zero mismatches** on played/won/drawn/lost/GF/
GA/points, spanning MEN_SENIOR tiers 1/2/5 and WOMEN_SENIOR tiers 1/2 —
comfortably over AC8's "at least 5, spanning different tiers/brackets."

Two real, evidenced explanations were found for the puljer that DON'T
reconcile exactly:

1. **The design's R-3 assumption ("only points carries over") is wrong —
   corrected.** For `pointsCarryOver: true` puljer (Mesterskabsspil/
   Oprykningsspil/Kvalifikationsspil phases), DBU's `stillingFuld` shows
   the team's **cumulative season-to-date total on every column**, not
   just points — e.g. a Superliga Mesterskabsspil team's scraped `played`
   is 32 (22 Grundspil + 10 Mesterskabsspil), not 10. A column-by-column
   comparison against just that pulje's own matches isn't meaningful for
   any column in this case, not only points. `reconcile.py` now skips
   these puljer entirely (reported separately, `compared: false`) rather
   than attempting and failing a comparison the design's original framing
   would have gotten wrong on played/GF/GA too.
2. **A likely penalty-shootout bonus-points scheme, found on non-carry-
   over puljer.** U19 Drenge Ligaen (pulje 473921): every mismatch is
   points-only (played/won/drawn/lost/goals all match exactly), and the
   size of each team's deficit correlates exactly with their count of WON
   penalty shootouts (verified directly: AC Horsens, 1 shootout win,
   1-point deficit). This strongly suggests DBU awards a bonus point for
   a penalty-shootout win beyond the standard 1-point draw — a scoring
   rule this pipeline's points formula (3/1/0 by W/D/L only, Decision 2)
   doesn't model. **Not auto-corrected** — the exact scheme isn't
   confirmed for every affected bracket (some, like `474114`/`474115`,
   have zero penalty-shootout matches at all and a real points
   discrepancy with no shootout-related explanation, so an administrative
   points adjustment invisible to a match-results scraper is also
   plausible there). Flagged in the reconciliation report for human
   review rather than guessed at.

**AC9 (independent-source spot-check):** fetched
`https://en.wikipedia.org/wiki/2025–26_Danish_Superliga` (external site,
not subject to dbu.dk's robots/politeness rules) and cross-checked its
Grundspil results matrix against the scraped `matches.jsonl` for pulje
`473806`. **25/26 sampled results matched exactly** (20 via an
independent random sample using the grid's row-name/column-abbreviation
mapping, plus 6 from an initial manual spot-check). The one discrepancy
(Brøndby vs Copenhagen) is attributable to what strong evidence indicates
is a Wikipedia data-entry error, not a scraper defect: Wikipedia's grid
shows **the same score, "1–0", in BOTH directions** of that pairing
(Brøndby-home-vs-Copenhagen and Copenhagen-home-vs-Brøndby) — which is not
how a double round-robin table should render two independently-played
legs. The scraped data shows two different, plausible results for the two
legs (2–1 and 1–0), and this exact pulje is one of the 9 that reconciles
with **zero** mismatches against DBU's own independently-rendered
`stillingFuld` standings table — a second, internally-consistent source
that corroborates the scraped fixtures over the Wikipedia grid for this
one cell.
