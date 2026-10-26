# Legend creator: plan

Builds a **skeleton** created player from web career data, as a standalone
FM26 changeset. The boring, factual part is automatic: biography, contract,
homegrown, one position, playing history and club spells. CA/PA stay 0 and
attributes stay empty, left for the author to do by hand.

## Scope (user, 2026-09-25)

| Field | Rule |
|---|---|
| Names | `Pfna` first, `Psna` last, `Pcna` common name, `Pfln` full name |
| Birthday | real DOB + offset, where `offset = target season - prime season`. His age in the target season equals his age in his prime. Dainelli, prime 2005/06, target 2025 = 9/6/1999 |
| Nationality | `Pnti` from the source; a second nation (`P2ni`) only when a source states it |
| Contract | `Pcti` = the chosen club. The four dates follow the user rules of 2026-09-08, reusing `convert_edition.sync_contract_dates` rather than copying it: `Pcjd` and `PCNj` are FORCED to the join date of the open spell at that club. `Pcsd` (last signed) falls between the season after he joined and the target season, at most 4 years back, and stays empty if he joined this season. `Pcex` is the end of a season from the target season out, capped at signed + 6, or target + 3 with no signed date. Draws are seeded from the record id, so reruns are identical. All four go at the very END of the file (a club change resets Date Joined), each with a `db_random_id` |
| International caps | `Piap`/`Pigl` = caps and goals from NFT's match list dated BEFORE the prime season starts (Dainelli: up to 30/6/2005, so his 11/6/2005 cap counts). 1/1 cutoff for a calendar-year nation |
| Homegrown | FM's rule: 3 seasons aged 15-21 on 1 July, a B team counting as its parent. A nation counts at 3 such seasons at its clubs. Worked out AFTER the playing history is built, reusing `repair_type_change.home_grown`. Can be more than one club or nation |
| Position | exactly one, set to 20 (`Pgoa`, `Pdce`, `Pdls`/`Pdrs`, `Pwbl`/`Pwbr`, `Pdmc`, `Pmce`, `Pmls`/`Pmrs`, `Pamc`, `Paml`/`Pamr`, `Pace`, `Pswe`). Generic source labels ("Defender", "Central") map to the most likely one; the CSV can override it |
| Playing history `Plhs` | every season up to the one BEFORE the prime, shifted by the offset. The prime season and everything after it are dropped. So the career ends on target-1, filled (the converter's "2024 filled") |
| Club spells `Pnph` | one spell per stay at a club, begin and end taken from the playing history |
| CA/PA, attributes | 0 and empty, by design |

## Sources and precedence

| Source | Best for | Access |
|---|---|---|
| national-football-teams | **default for anyone with international caps**. Per-season club, apps, goals, division level, DOB, position | plain HTTP |
| bdfutbol | Spanish football. Only lists leagues in its own database (Sérgio Cruz starts at 25) | plain HTTP |
| carrierecalciatori.it | Italian football, named divisions (Serie C1/C2...) | plain HTTP |
| zerozero | Portuguese football | Cloudflare: a real Chrome the user unlocks once (below) |
| Wikipedia, any language | youth clubs, loans (`→`), half-season stays, full name. Tried in the player's language first, then en | MediaWiki API |

The primary source gives the season rows. Wikipedia adds youth clubs, loan
markers and the owning club, and a missing full name. When two sources
disagree on a season, the primary wins and the report flags the row. Nothing
gets averaged.

**zerozero through a real browser.** `creator/browser.py` launches Google
Chrome with its own profile (`~/.fmpt-chrome`) and a remote-debugging port.
The user passes the Cloudflare check and logs in once; the profile keeps the
cookies. The script then drives that Chrome over CDP (a small stdlib websocket
client, since the project runs on `/usr/bin/python3` without pip). It also
finds a profile URL by Google-searching "<name> <club> zerozero" and taking
the first zerozero.pt/jogador result.

Every fetched page is cached on disk (`creator/cache/`) with a 2-3 s delay
between requests: sources are read once, and the result stays in the user's
own database.

## Building the record

1. **Resolve names to FM26 ids.**
   - Clubs go through `fm_names` by name plus nation. A B team resolves to its
     own id; homegrown maps it to the parent.
   - Divisions go through `creator/levels.json`, a map from (nation, level) to
     the current FM26 competition id (Italy II = Serie B), filled per nation
     from the name index. carrierecalciatori's named divisions map to a level
     first (Serie C1 = 3).
   - A name that does not resolve leaves that cell blank and is flagged. Club
     and division are written LAST in a row (converter rule), so a miss costs
     only those two cells.
2. **Rows.**
   - Year = season start year + offset.
   - `yror` 1/2 orders a season with two clubs. Sources list them newest first
     (NFT, carrierecalciatori), so their order is reversed.
   - Loans set `onln`.
   - Youth seasons from Wikipedia become blank rows with the youth tick, only
     at age 18 or younger (the youth-flag rule). A season with no appearances
     is written as `0`, never blank ("0 is 0").
3. **Spells.**
   - Consecutive seasons at one club are one spell. Join 1/7, leave 30/6;
     1/1 and 31/12 for calendar-year nations (`SEASON_CALENDAR`).
   - A season with two clubs means a move on 1/1 (the first spell ends 31/12)
     unless a source gives a date.
   - A loan is its own spell, nested inside the owning club's open spell. The
     owner is Wikipedia's parent club, else the last non-loan club.
   - The spell at the target club stays open. If the target club is not his
     last club, a new spell starts on the target season's join date.
4. **Emit**, in the order the editor accepts. The Evandro lesson: the type
   change comes first, or the values written before it are reset.
   1. `ADDR` (dcty 2, no `nwui`)
   2. `Ptyp` 1→2
   3. names
   4. DOB
   5. nation
   6. position
   7. `Plhs`
   8. `Pnph`
   9. homegrown grids (men's nation record)
   10. contract

   Ids come from `rebuild_lost_records.free_ids` against a ledger
   (`creator/ids.json`) seeded from every `final_xmls` file, so no two created
   people ever share a high word.
5. **Verify.**
   - Replay the emitted file with `probe_editor_replay` (never
     `clean_import.replay`).
   - Check the replayed grid equals the model row for row.
   - Write a report: every flag, every unresolved club or division, every
     disagreement between sources.

## Input

A CSV, one player per line:

```
name,prime_season,target_club,target_season,position,urls
Dario Dainelli,2005,Fiorentina,2025,,https://www.national-football-teams.com/player/14831/Dario_Dainelli.html
```

`position` blank means "take it from the source". `urls` can be empty for a
zerozero player: the script searches. One CSV makes one changeset plus one
report.

## Layout

```
creator/
  create_legends.py      CLI: CSV in, changeset + report out
  sources/nft.py  bdfutbol.py  carriere.py  wikipedia.py  zerozero.py
  browser.py             Chrome + CDP for zerozero
  model.py               Profile / Season / Spell, merge + flags
  build.py               offset, rows, spells, homegrown, emit
  levels.json            (nation, level) -> FM26 competition id
  ids.json               created-id ledger
  cache/                 fetched pages
```

It imports `scripts/` modules (`fm_names`, `repair_type_change`,
`rebuild_lost_records`, `probe_editor_replay`) and does not copy them.

## Delivery

1. **Probe:** Dainelli alone (NFT + it.wikipedia) at Fiorentina 2025. The user
   imports it into FM26. This settles whether the game loads a record this thin
   (every created record so far carried about 150 fields).
2. NFT, Wikipedia, bdfutbol and carrierecalciatori parsers, with Junquera
   (bdfutbol) and Berti (carrierecalciatori) as test players.
3. zerozero through the browser, with Pedro Barny.
4. Batch from a sheet.

## Decided

- City of birth (`Pcbi`): Wikipedia's LuogoNascita, else NFT's birthPlace, looked up in FM26's own city table (`cache/fm26_cities.json`, read from 2600_fm/lang_db with Python 3.14). A name several FM26 cities share is flagged, not guessed (2026-09-25).
- Plhs rows carry join/leave from the spells: first row of a spell the join, last row the leave; a loan nests inside the parent spell (CLAUDE.md, join and leave dates on a rebuilt career).
- Youth over zero: a 0-app senior row in a season Wikipedia files under youth becomes a blank youth row while he is 18 or younger on 1 July (Empoli 1997/98); older than that it stays a 0-app senior season and is flagged (Modena 1998/99). A season no source covers is flagged as a hole.

- Levels FM26 plays in groups map to the umbrella league the author's Italy file uses: Serie C 43127171, Serie D 831597 (2026-09-25).
- Ids: `ids.json` is re-seeded from EVERY xml under `FM 26 XML Files/` on each run (the first probe collided with the Portugal rebuilt records in `extracts/`), the high word is checked against FM26's own people table (`cache/fm26_basic_people_db.bin`, decompressed with the zstd CLI), and a player keeps his id across reruns (`by_key`).
- Verification: Plhs through `probe_editor_replay`, Pnph through `creator/verify.py` (the former does not model spell snapshots and drops every Pnph op, even on files that import fine).

- Contract: the 2026-09-08 rules (above). The user's answer of 2026-09-25 pointed back to them.
- Caps: count only up to the start of the prime season.

## Fix mode: people FM26 already has (2026-10-08)

A CSV row with a `dbid` column fixes that person in place instead of creating one
(`creator/fix.py`). His career is FM26's OWN playing history, read from
`2620_fm/pl_hist_{index,id,dt}.dat` (`creator/fm26_history.py`, format in its
docstring), cut before the prime season, shifted by the offset and written with
the Rooney/Drogba method: Clear `Plhs`, insert every row with all its columns
(order, club, division, apps, goals, youth, loan, fee, join, leave). Clubs and
divisions are already FM26 DBIDs, so nothing is resolved by name.

- Written: `Ptyp` 1->2 and a `PErt` Clear (non-player only, the author's own
  pattern), `Pdob` and `Piap`/`Pigl` from NFT, `Plhs`, `Pnph` (spell builder +
  FM26's own dates), homegrown, contract. Never: names, nation, birthplace,
  position, CA/PA, attributes, personality.
- The Order column is copied as FM holds it, 3-8 included (user: Maldini and
  Gattuso's Milan rows read 5/4/3 in the editor too).
- Fees are written raw: FM stores pounds, the editor shows euros (x1.157);
  a changeset cites the stored value (Rooney's 27000000).
- A fix must be imported AFTER any legend file that also edits that person.
- FM26 only starts ~17k people before 1990: the report flags a history that
  starts after 18 or has a hole; web sources are not merged in.
- The tribunal tick (flag bit 2) is not written yet - flagged when a kept row has it.
- International retirement is undone on every fix: `Pird` nulled, `Pirc` false (the author's pair).
- `Pdcn` (days at club AND nation, one grid, team = club or nation DBID) is Cleared and
  rewritten as of the target season's 1 July. Rules read off FM's own values (Gudjohnsen):
  a loan's days go to the loan club and come OUT of the parent spell (Monaco 365 - Tottenham
  123 = 242); a nation counts the days at its clubs, carve-out included (France 242); his own
  nation counts. Plain date difference. Rows carry no age flags (0t21/d152/mnag/mxag/bfat/etto all off).

## Decided (2026-10-08)
- A season no source covers stays a flagged hole, filled by hand.
- The parent's leave date stays on its last own row when loans follow it.
- The contract expiry stays the seeded random draw (one to six seasons out); no minimum.
- Every fix also clears the debut and first-goal dates (`Pidd`/`Pigd`); their opponents
  (`PIDo`/`PIGo`) stay. The Pdcn age-band columns stay off: they matter for youth players
  counted homegrown at a team or nation, rare and harder (user, 2026-10-08).

## Batch (2026-10-08)
`create_legends.py <csv>` runs every row into `out/<csv name>/` (`--out-dir` overrides); a failing player is reported
and skipped. Writes one xml + md per player, `<csv> - all.xml` (the PASSED players merged, in
CSV order) and `<csv> - summary.md`. Mode per row: `dbid` filled = fix, empty = create.

## Divisions from FM26's team league history (2026-10-08, supersedes the umbrella-league rule of 2026-09-25)
A created row's division is the competition the club played in THAT season, read from FM26's
own team league history (`fm26_leagues.py`; server table 75, teams = server 28, competitions =
client 5; cache `cache/fm26_league_history.json`, rebuilt with Python 3.14). A European season
is filed under the year it ENDS (league row 1979 = 1978/79), a calendar-year nation's under its
own year. Dainelli now gets Serie C1/A, C2/C, C1/B instead of the umbrella Serie C/D. Only when
the club has no row does the source's level map through `levels.json`, flagged.
Fix rows keep the division FM26's player history already holds.

## The sheet (2026-10-08)
Columns `Position, Name, Nation, Team, Season, Website, Exists[, Id]`; `--target-season`
(default 2025) on the CLI, so FM27 is a parameter. Season = prime season start (1995 = 1995/96).
Exists Y/Yes = fix (FM26 has him, staff or player), found by name + nation, accents ignored; a
namesake tie is broken by league rows in the 5 seasons up to the prime (26 "Rui Costa"), a real
tie (two famous "João Pinto") is refused - add the Id. One link per Website cell, the site read
off the host: NFT, Wikipedia (pt/en/it infoboxes), zerozero (reported, not read yet).
Exists Y/Yes, or an FM26 id in the Exists (or an Id) cell, means fix. The Team column is resolved
once per sheet with the nation most of its players share, so every player gets the same target
club (Salamanca -> 1768 by override); a Team cell can also hold an FM26 id.
Position codes GK RB CB LB DM CM AM RW LW ST, or the Portuguese GR DD DC DE Mdef/MD MC MAC/MO
ED EE PL (any case), map to one FourCC (created players, and a staff member a fix converts;
a fix never touches an existing player's position).

- Any nation: each NFT club row carries its country, a pt infobox club its flag; a club
  resolves in its own country, else anywhere with the player's country preferred.
- Club ranking: reserve/B/women's sides out, whole-word score (a distinctive word counts
  double), country, then REPUTATION (bare "Milan" = A.C. Milan, not an extinct namesake),
  then lowest id. A match leaving a distinctive word unexplained is marked CHECK in the
  report; `club_overrides.json` pins "Name|Nation" -> id by hand.
- NFT without a Wikipedia link: Wikipedia is looked up by name (player's language, then
  en), taken only when its birth date equals NFT's.
- Wikipedia alone: rows come from the infobox stays, apps/goals only for one-season stays.
- Youth rows only from age 15 (FM's homegrown start); childhood clubs are dropped.
- A club the index gives no nation takes the nation of its latest league competition.

## zerozero (2026-10-08)
Cloudflare challenges scripts AND automated browsers (the DevTools Chrome looped on the checkbox),
so zerozero is read in the USER'S OWN Chrome through the Claude extension (`/chrome`): Claude runs
`sources/zerozero_extract.js` on the player page and saves its output as
`cache/zerozero_<player id>.txt` (key=value lines + "season;club;team_path;apps;goals" rows). The
batch then reads the cache (`sources/zerozero.py`); a zerozero row whose cache is missing fails
with "page not fetched yet". The page gives no division and no club country: divisions come from
FM26's league history, clubs are looked for in the TARGET club's country first (Babalito is
Mozambican, his clubs Portuguese). "-" = a season with no figures (blank), "[Jun.A S19]" = youth.
Also: FIFA codes in the Nation column (MOZ), "SC/CD/GD..." stripped as club prefixes, colonial
town names mapped (Lourenço Marques -> Maputo).
- (later 2026-10-08, user) Each zerozero career row carries its club's country as
  `span.flag:PT` - read as a sixth field and mapped ISO -> FM nation; the target-country
  preference is now only the fallback for a row without a flag.
- zerozero youth sides ("[Jun.A S19]") are kept at ANY age (user); the age-15 floor stays
  for Wikipedia's childhood youth list only.
- Extractor output: "key: value" lines (an "=" is blocked by the extension's output filter),
  kept on the page as window.__zz and read back in slices (tool output is cut near 2,000 chars).
- Youth floor (user, 2026-10-08): a youth season counts from the one he turns 15 in - 14 on
  1 July - for every source; younger seasons are dropped (YOUTH_MIN_AGE = 14).
- Wikipedia career statistics table (en "Career statistics", pt "Estatísticas", it
  "Statistiche"): parsed with rowspan/colspan (`wikipedia.career_table`), one row per season and
  club with loans; it replaces the infobox totals for every season it covers, the infobox stays
  fill the rest. Infobox `fullname` alias read; <ref> citations stripped before reading fields.
- FM26 history: 0xFFFFFFFF in a club/division cell is EMPTY (361k of 2.1M rows), never an id.
- Exists=Y always goes to fix mode (FM26's own history has priority over any web source).
- Calendar-year clubs in the creator (user, 2026-10-08): a club's calendar comes from its FM
  nation (CALENDAR_YEAR_NATIONS). A calendar club's Wikipedia stay "2008-2012" is every year
  2008 to 2012 INCLUSIVE and a bare year is that year; its spells run 1/1-31/12, a move inside
  the year on 1/7. In a shared year the calendar club's row comes first. A year may carry youth
  rows at two clubs (Barra Mansa + Fluminense 2012). Contracts use convert_edition.Seasons for
  the target club. Club nations are memoized (one offline name index per run).
- (user, 2026-10-08) A youth row carries the competition the club's SENIOR team played that
  season, from the league history (Babalito's Benfica juniors 1972/73 -> Primeira Liga).
- Created players get `Pdcn` too (days at club and nation, cleared and rewritten, same rules as
  a fix). A created spell ends the day before the next begins, so it is counted inclusively (365
  per season, as FM counts its own spells). A spell opening on the target season's first day has
  0 days and writes no row.
- Ethnicity `Peth` (user, 2026-10-08; Northern + North Africa added same day), created players only, from the country of BIRTH
  (zerozero "País de nascimento", Wikipedia en birth_place last part / pt paisnatal; else the
  nationality, flagged): Central/South Europe -> 1 Mediterranean/Hispanic, Africa -> 3
  African/Caribbean, South America -> 9 Mixed Race, anything else unset. Values read off the
  author's files (0 Northern European, 2 North African/Middle Eastern). Lists: build.MEDITERRANEAN
  / AFRICA / SOUTH_AMERICA. A fix never touches FM26's own ethnicity.

## First real batch: Académico de Viseu (2026-10-08, inputs/viseu.csv, 23 players)
- Sheet names 'First "Common" Last' -> first/last from the outer parts, common = the quoted one.
- FIFA-ish codes seen: MAL = Mali, CBV = Cape Verde (alongside MLI / CPV).
- zerozero: "(E) [Owner]" after a club = on loan (empréstimo) from Owner; "[B]" = the B side;
  "[Veteranos]/[Futsal]/[Praia]" rows are not his career and are skipped; a current player's
  page title carries " :: 2026/2027"; /joueur/ links are the same player id.
- A fix whose player FM26 already has AT the target club keeps his real contract (Viseu's
  current squad: prime = target season, nothing to shift).
- Reading zerozero: one browser_batch per two players, 18-line slices (tool output is cut
  near 1,500 chars per item). A localhost receiver was refused by the permission classifier.
- Viseu batch lessons (2026-10-08): (1) home_grown's fallback is a nation NAME (an id crashed
  four players); (2) a fix row's person ALREADY AT THE TARGET CLUB wins over any nation filter -
  FM26 files Viseu's foreign players as "Portugal", and the first run matched the wrong Robinho;
  (3) club abbreviations are spelled out for search and scoring (FC Futebol Clube, SC Sporting
  Clube/Sport Club, Est. Estrela, CP Clube de Portugal...), the bare words searched too, and a
  distinctive word outweighs any number of generic ones; (4) club_overrides.json pins Académica.
- (user, 2026-10-08, after the Viseu run)
  - zerozero pages can carry SEVERAL career tables (veterans first, his football career, a
    coaching "J V" one, a national-team "EDIÇÃO" one): every table with an ÉPOCA and a G column
    is read, veterans/futsal/beach rows dropped (Flávio's career was in the second table).
    "(Extinto)" is stripped from club names.
  - A season FM26's league history lacks: a Portuguese club -> Portuguese Regional Divisions
    (55020301); an African club -> that country's highest-reputation men's league.
  - A club FM26 lacks (or a known wrong match) -> Unknown Club 16027118, which never counts
    for homegrown or days. club_overrides.json pins CCD Montijo there.
  - City of birth must be a city of the birth country (fm26_world: client table 2 nation index
    -> table 11 nation DBID); Brazilian cities are "Name (UF)". Luanda = 103003 (Angola).
- (user, 2026-10-08) A Brazilian season FM26 lacks -> 19127225 (Brazilian Non-League Clubs);
  El Salvador -> its top league; every other country without a specific rule -> its top league.
- `create_legends.py ... --only "Name"` rebuilds just that player and re-merges with the files
  already in --out-dir (summary marks the others KEPT) - a one-player fix without a 16-min rerun.
- (user, 2026-10-08) NFT "-" is data-order="-1": blank apps/goals, never 0 (a real 0 stays 0).
- Height `Phes` (cm, odvl 0) for created players and converted non-players, from NFT
  (itemprop="height">1.77m), Wikipedia (en height, pt altura, it Altezza) or zerozero
  ("ALTURA / PESO: 178 cm / 66 kg" - only on pages with recent data). None found = flagged.
- A fix that converts a non-player writes the sheet's position code (Jorge Rosário: DM) - a
  staff record has no position at all.

## bdfutbol (2026-10-08)
Cloudflare too: read in the user's Chrome with `sources/bdfutbol_extract.js` (window.__bdf, 18-line
slices), cached as `cache/bdfutbol_<jNNNN>.txt`, parsed by `sources/bdfutbol.py` into the same row
shape as zerozero (fed through the same builder path). Career = `table.traject`: season, team,
country (empty = Spain), division (1ª/2ª/2ªB/3ª -> level, fallback only), games, goals. Profile:
Nombre completo, Fecha de nacimiento, Lugar/País de nacimiento, Demarcación, Altura. A goals "-"
with games played is 0 (bdfutbol prints "-" for none). Test: Junquera j5372, passes.

## Running without Claude: bookmarklets (2026-10-08)
zerozero and bdfutbol answer every plain request with a Cloudflare JS challenge (9 curl variants
tried for bdfutbol: hosts, http/https, UAs, browser headers - all 403), so a real browser has to
read them. `bookmarklets/make.py` builds `bookmarklets/bookmarklets.html` from the extractor
scripts in sources/ (single source of truth): drag the two buttons to the bookmarks bar, click one
on a player page, and it saves zerozero_<id>.txt / bdfutbol_<jNNNN>.txt to Downloads (it warns
when the page has no career rows, e.g. still on the Cloudflare screen).
`create_legends.py sheet.csv --import-downloads` moves them into cache/ (newest copy wins,
"name (1).txt" handled) before the batch. NFT, Wikipedia and the FM search index need no browser.
Rebuild the bookmarklets after any change to an *_extract.js.

## Divisions without FM26 league history (2026-10-09)
Order: a hand pin in division_overrides.json ("Club|season start year" -> competition) ->
FM26's team league history -> source level I: the country's top league -> a lower source
level: today's league at that level (levels.json; Italian amateur categories and Serie D of
any era -> Serie D) -> an Unknown Club season in Italy: Italian Lower Division 1400399 ->
the country default (Portugal regional 55020301, Brazil 19127225, else the top league).
Unknown Club rows never use Unknown Club's own history or country (FM26 files it under
Albania); the season's own country stands in. Seasons a season-by-season source skips,
between his first and last, are filled from the Wikipedia infobox (level from the same
club's neighbouring season).

## 2026-10-13
- foradejogo youth sides (JUN, JUV, INI, INF, ESC; escalao>0 in the team link) are youth
  rows: blank, youth tick, from the season he turns 15 (14 on 1 July) to 18. A senior row
  at the same club and season wins over the youth one (Rúben Micael's União 2003/04).
- Sheet columns CA, PA, CR, HR, WR write PCAB, PPAB, PCRP, PHRP, PWRP, create and fix
  alike, only when the cell holds a number on the editor's scale (0-200; PA -200..200);
  anything else is flagged and not written. A fix still never writes position or
  nationality (a converted non-player gets the sheet position, having none).
- A created player's season with 0 games while he is 18 or younger on 1 July (turns 19
  in it at the latest) becomes a blank youth row with the tick. Blank seasons stay blank.
  A fixed player keeps FM26's own history as it is.
- A fixed player moved to a new club has his squad number (Psnu) nulled; one already at
  the target club keeps it.
- division_overrides.json also takes "<FM26 club id>|<year>". Old Estrela da Amadora
  (2000030636, no FM26 league history) pinned from en.wikipedia "C.F. Estrela da Amadora
  (1932)": top flight 60, Liga de Honra years 61 (1987/88 inferred: promoted in 1988).
  levels.json: Portugal I=60, II=61.
- Team RET (user, 2026-10-22): retire mode - Pcti nulled (old club as odvl), PErt cleared
  and one retirement dated 30/6/2024, nothing else. Every fix also clears PErt now, not
  only a converted non-player.
- A fix whose season is the player's first in FM26 (a youth player placed at his first
  club) no longer stops: empty playing history, one open spell at the target club from
  that season (flagged).
- Achievements (Pacl, user 2026-10-22): FM26's own rows decoded from server_db.dat
  (fm26_achievements.py, 36-byte records). A fix removes those from the chosen season on
  (like the playing history): the grid is cleared and the earlier rows written back cell
  by cell, real years (not shifted). Season of
  an achievement: calendar-year clubs = its year; otherwise a bare year is the season's end.
- "Already at the target club" (no Pcti/contract written) now also requires that FM26's
  history has no move into that club dated after 1/10 of the target season: the search
  index lists a pre-agreed later transfer as the current club (Eduardo Fereira: La Guaira
  to 15/12/2025, Caracas from 20/12/2025). The fix report says when no contract is written.
