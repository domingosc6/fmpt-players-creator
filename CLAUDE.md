# CLAUDE.md — FMPT Legends Database (FM editor tooling) — v2

Guidance for Claude Code on this **personal** project (unrelated to any work
repo; no work conventions apply). Reference document — read top to bottom when
resuming.

## 0. Repository layout

This folder is the git repo **`domingosc6/fmpt-players-creator`** (private,
the user's personal GitHub account, branch `main`). `README.md` describes every
script; this section is what Claude needs to work in it.

| folder | what it is |
|---|---|
| `scripts/` | the edition converter and its helpers (§3); `checks/` is the promotion gate, `batch/` the batch runner |
| `creator/` | Legends Creator: creates and fixes FM26 legends from a sheet. Rules in `creator/PLAN.md` |
| `placements/` | club/slot proposals per sheet player; `santa_clara/` is the same pipeline for one sheet |
| `comparativo/` | club fields (stadium, morale, training, youth, finances) for the Comparativo sheet, read from FM26's database; layouts in the script header |

**In git:** code, docs, `creator/` configs and input sheets, and
`creator/ids.json` (the ledger of every created id - one copy only, never
regenerate it). **On disk only** (`.gitignore`): the `FM 18/24/26 XML Files/`
data, `scripts/archive/` (frozen versions), `scripts/probes/` (one-off
investigations), the caches (`creator/cache/`, `scripts/fm_names_cache.json`,
`placements/nft_cache/`), run outputs (`creator/out/`, `placements/*.json`,
`placements/xlsx/`), `work/`, and the packaged `Legends Creator/` + its zip
(rebuilt by `creator/make_package.py`).

- **Scripts run from any directory.** Each one finds the repo's data from its
  own location (`__file__`); paths given as arguments are relative to the
  caller's cwd. Keep it that way: never hardcode `/Users/...` or
  `~/Documents/FMPT-Legends`, and never write scratch files to a session's job
  directory - shared intermediates go in `work/` at the repo root.
- **FM26's people table** comes from `build.people_db()` (`creator/build.py`,
  cached in `creator/cache/fm26_basic_people_db.bin`), not a copy.
- **The FM26 Editor install and zstd go through `creator/fm26_install.py`**:
  `db_dir()` (any Steam library on macOS/Windows, `FM26_EDITOR_DIR` overrides),
  `decompress()` (built-in zstd on 3.14, the `zstd` command on 3.9) and
  `zstd_python()` (the interpreter a `--build` runs under). Never hardcode the
  Steam path or `/opt/homebrew/bin/python3` again. The user runs on macOS and
  Windows.
- **`creator/ids.json` is synced through git** between computers: pull before
  creating players, commit + push after. The `Legends Creator/` package is
  retired as the place to run from (its ledger was merged into the repo on
  2026-10-23).
- **Git:** commit as `Domingos Costa <30902660+domingosc6@users.noreply.github.com>`
  (set in this repo's config). The global Jira-ticket commit hook is switched
  off here (`core.hooksPath = .git/hooks`). `git push` works as is; any `gh`
  command must run as `env -u GITHUB_TOKEN gh ...`, or it acts as the work
  account and cannot see the repo. Commit or push only when the user asks.

## 1. The project

**FMPT Legends** is a Football Manager editor database (FM Portugal community
project) that recreates football legends, each "transported" from their
subjective prime season into a target game season. A legend's own career history
is shifted by a per-player offset so it lines up with the target.

### Design rules
- **Prime-season anchoring, per player.** Each legend is placed at their prime;
  their history is internally consistent, but **not across players** — two
  legends' "2022/23 at Barcelona" can mean different real seasons. Never "fix"
  cross-player inconsistency.
- **One instance per legend** (FM forbids duplicates). Club assignment priority:
  a) years at club, b) goals/individual honours there, c) trophies won there,
  d) importance to that club's All-Star XI.
- **Squad cap 30** per club; weak clubs also get All-Star squads for balance.
- **Leagues** rebuilt on historical first-division presence; continental
  qualification by presence, current coefficients kept.
- Calendar-year leagues (Argentina, Brazil) keep 1/1 joins & 31/12 leaves;
  European leagues use 1/7 / 30/6.

### Six change categories
Every person is one of these; the changeset shape differs:
1. **Current player at his current club** — in-place edits on a real DBID.
2. **Current player moved to another club** — edits + contract/transfer + often
   `lsop=2` deletes of post-prime clubs.
3. **Ex-player in the DB as staff** — `Ptyp` 1→2 (non-player→player), delete the
   `PErt` retirement, restore playing attributes, de-age.
4. **Player not in the DB** — full creation: `ADDR` registry record + all fields.
5. **Coach in the DB** — in-place edits.
6. **Coach not in the DB** — new non-player record (`ADDR` with `dcty=1`).

Categories 1/2/3/5 target real DBIDs; 4/6 are self-contained.

### Soft-delete of surplus players
A current player who fits no squad is removed by **adding a backdated `PErt`
retirement** (e.g. `30/6/2020`) — at game start he's long retired and gone,
record preserved for future editions. Report any person with a `PErt` addition.

## 2. Claude's role

- **Role 1 (primary): edition/season conversion.** Shift an old profile file to a
  target season using `convert_edition.py` (see §3). This is the main deliverable
  — files run to the thousands.
- **Role 2 (later): skeleton generation.** Build new-player XML from a spec (name,
  DOB, club, career), which the user fills with attributes. Do not start unasked.

### Working style
- Conversation in **English**, even when source material is Portuguese.
- **Always ASK before shifting managers/staff** (`--shift-staff`).
- **Flag anything unfamiliar** in a new file rather than guessing.
- Don't over-build; the user drives scope.
- DBIDs are **not** names — never claim a club/nation name from an ID; it comes
  from a user mapping or is labelled inference.

## 3. The converter — `scripts/convert_edition.py`

Frozen copies live in `scripts/archive/` (on disk, not in git); the latest is
`*_v32.py`, which produced the current files. The history: `convert_edition_v1_backup.py` (v1), `convert_edition_v2.py` (v2,
conversion of cumulative files) `convert_edition_v3.py` + `clean_import_v3.py`
(v3, conversion + career rebuild) `convert_edition_v4.py` +
`clean_import_v4.py` (v4: v3 + dead-weight removal, fee re-attachment, whole-row
snapshot materialisation, leap-day clamp) and **`convert_edition_v5.py` +
`clean_import_v5.py` (v5, 2026-09-03: adds `--rebuild-real-history`, the shift
model for REAL database records), `convert_edition_v6.py` + `clean_import_v6.py`
+ `fm_names_v1.py` (v6, 2026-09-04: real-record rebuild accepted, Clear and
rewrite, spells derived from the career, `--names`), `convert_edition_v7.py`
+ `clean_import_v7.py` (v7, 2026-09-05: dates of birth repaired, impossible years
never shifted - see below) and **`convert_edition_v9.py` + `clean_import_v9.py`
+ `fm_names_v2.py` (v9, 2026-09-07: season calendars per nation, so a
calendar-year league gets 1/1 - 31/12 derived dates, and leagues whose calendar has
MOVED are excluded and reported instead - see §5f. `fm_names` now stores each
club's nation; entries written by an older build are re-fetched once)**.
Do not edit the frozen copies; branch from them.

```
convert_edition.py INPUT OUTPUT (--offset N | --target-season YEAR)
                   [--shift-staff] [--flag-year-only] [--report FILE.md]
                   [--continuations current|none|all]
```
- **`--report FILE.md`** — the explanations file: spread, multi-id people, anomalies,
  anchorless list, ambiguous links, staff, non-person tables, year-only rows, and
  the date-of-birth sections (corrected / refused by the guard / never edited /
  still wrong), dates the editor cannot read, and the **season calendars** section
  (§5f: the calendar each nation got, the derived dates written, and every nation
  where the author's own dates disagree with the table).
  Standard run: `--target-season 2025 --flag-year-only --rebuild-careers
  --drop-retired-adaptations --rebuild-real-history --names --report <file>.md`.
  Write it to `FM 26 XML Files/explanations/`, the XML to `FM 26 XML Files/converted_xmls/`,
  named `FMPT Legends - <Country> - target2025 - clean.*`. **Only the `- clean`
  files are for import**; superseded conversions live in the `old/` subfolder of
  each output directory (moved there 2026-09-03) - never import from `old/`.
- **`--continuations`** — see §5b. Default `current`.
- **`--offset N`** — add N years to every person, uniformly. Use when the whole
  file shares one vintage.
- **`--target-season YEAR`** — "make every player current for season YEAR/(YEAR+1)"
  (label year, e.g. `2025` for 25/26). Computes a **per-player** offset from each
  player's last-season anchor, so a **mixed-vintage** file (FM17…21) all lands on
  the same target. Prints the offset spread and flags anomalies. **Prefer this**
  for anything possibly mixed.
- **`--shift-staff`** — also shift managers/staff, by the **majority** player
  offset (managers have no reliable anchor). Off by default (staff left intact).
- **Left unshifted in target mode** (and listed in the report): staff, anchorless
  people that carry dates, anomalies (anchor in the future or > 12 years before
  the target — real records whose old history was edited). No majority fallback
  for players: the user prefers an unshifted record over a guessed offset.
- **`--flag-year-only`** — write the list of rows that won't round-trip (see §6)
  to `OUTPUT.year-only.txt`.

**Leap day**: adding years to 29 February clamps the day to the 28th when the
target year is not a leap year — the editor rejects the impossible date and
shows a blank (Denis Law's 29/2 leave date). Applies to every shifted date.

**Shifts** (people = table 1 only): `Pdob`, contract dates (`Pcjd`/`Pcex`/`Pcsd`/
`PCNj`), loan dates (`PLsd`/`PLed`), and grids `Plhs`/`Pnph`/`PPsT`.
**Untouched:** non-person records (clubs = table 3), `PErt` retirements, `Pacl`
honours, `odvl` scalars, non-date integers, sentinel years 1900/2100, and **any
year below 1000** — FM writes an unset date as year 0 (Paredes' Reggina spell)
and the author's own typos have lost a digit (198, 201, 209). Shifting one only
produces a different date the editor cannot read; they are listed in the report
and never repaired, because nothing says which digit he dropped.

### Join and leave dates on a rebuilt career (v7)
Fixing a career is three steps, in this order: **shift the playing history, shift
the non-playing history, then fill in the rows' missing join and leave dates.**

The author leaves most CREATED careers with no date on the rows at all
(Di Gennaro). The **club-spells grid is the source of truth** for them, and it has
to be REPLAYED to be read (`replay_spells`) — a created player builds his spells on
blank rows, so no snapshot ever names the club and the last-value reading real
records use sees nothing. Runs and spells are paired in order at each club, and a
date is only taken when it lands inside the run (his spells can lag his career
relabelling by an edition: Platini's Nancy B spell reads 2018 against a 2012 row).

His grid is **all or nothing per player**: one date out of step forfeits the lot.
Taking the ones that happen to fit and deriving the rest is worse than deriving
them all — Thuram's Parma spell is a year behind his Parma rows, and the mixture
left Monaco leaving in 2022 against a Parma joining in 2023, a hole neither source
implies.

Taking his dates is what puts 1/1 and 31/12 on a calendar-year league and a real
date on a mid-season move — neither is derivable from the career (Elkjaer joined
Koln 1/1/2018 and Lokeren 6/2/2019). Where no spell answers, the dates are derived
from the runs as a real record's are: first row of the run carries the join, last
one the leave, a loan nests inside the parent spell without breaking it. A B team
counts as its parent club, so the first-team row can carry a join date from the
season the player entered the reserves (Thuram, AS Monaco 2 in 2016).

A one-day gap between a leave and the next join is CORRECT and not to be
smoothed: the season ends 30 June and the next begins 1 July. A mid-season
transfer the author never dated leaves a row joined and left the same day (81 of
7489 rows in Italy); nothing in the file says otherwise.

**Real records are untouched by this** — their spells are derived FROM the career,
so both grids already agree and reading one back into the other would be circular.
Every run there already has a join on its first row and a leave on its last.

### Continuation ids and the created-career rebuild (v7)
A linked id with no `ADDR` is a **continuation** of the created record unless it
flips person type or its `Pdob` `odvl` is a BIRTHDAY the record never had. The
test is the **day and month**, not the whole date: the author bumps the year
edition after edition and the chain has holes (Platini's FM19 id cites 1989, a
year no pass in the file wrote), while a genuinely different person does not
share a birthday. Getting this wrong is not a missing edit — the excluded ops
survive into the output and run AFTER the rebuild's Clear, relabelling the rows
it just wrote and duplicating others. 14 of 15 Italy exclusions were this bug.

### Dates of birth (v7)
The author moves the date of birth and the career in separate passes and they
drift apart, so a legend can be transported with the wrong age. Two repairs, and
neither guesses:
- **A real database record** was rebuilt from its REAL years, and its real date of
  birth is in the file too — the FIRST `Pdob` op's `odvl` is the untouched
  database value. So the date belongs at that value plus the same career shift.
  Applied only where a real career was actually read (not a stub under 3 rows,
  not a career the author typed after his own Clear).
- **A created player** has no real anchor. What is his is the span he was given
  (career last year minus year of birth) — a property of the PLAYER, restated
  every time the author relabels. The span he states MOST OFTEN is the one he
  means; a single pass that disagrees is the slip. Ties go to the build that
  created the record, where he typed career and age together (Platini: 28 at
  FM17, 27 at FM19, and 28 is the real one).

The correction is written onto the last `Pdob` op of **every** id the person has —
which id the editor resolves is not knowable here (Maldini's last word sits on an
id that never applies). The age at his first senior season is the **guard**: a
computed date that puts a child in a league game means the career was misread, so
nothing is written and the record goes on the by-hand list.

A record whose date of birth the author never touched at all cannot be computed —
no `Pdob` op means no `odvl`, and the FM reference index carries no dates of
birth. The report lists those with the exact number of years to add by hand.

Edition ↔ season: FM YY's current season is `(YY-1)/YY`, label year `2000+YY-1`
(FM24 → 23/24 → 2023; FM26 → 25/26 → 2025). So FM24→FM26 current = **+2**; to
prep NEXT season add one more. `--target-season 2025` = "everyone current for
25/26".

**Validate a conversion** by diffing against source: every shiftable date/year
moved by the right offset, nothing missed/doubled, `odvl`/clubs/`PErt`/`Pacl`
unchanged, and (target mode) each person shifted by their own computed offset.

## 4. File format reference

`.fmf` files are proprietary binary — inspect only (`strings`, zlib). All work is
on the **XML** export. An export is one `<record>` with header fields (`version`,
`svvs`, `EdBr`, `EdDt`) and a `<list id="db_changes">` of change records.

### Change record
```xml
<record>
  <integer id="database_table_type" value="1"/>   <!-- 1=people, 3=clubs, 55=added-records registry -->
  <large id="db_unique_id" value="…"/>             <!-- target record -->
  <unsigned id="property" value="…"/>              <!-- FourCC packed in a uint -->
  <… id="new_value" …/>                            <!-- typed: string/integer/date/boolean/record/null -->
  <integer id="version" .../>
  <integer id="db_random_id" .../>
  <… id="odvl" …/>                                 <!-- pre-change old value; never shift -->
</record>
```
- **Property IDs are FourCC** (4 ASCII chars big-endian in a uint). Decode:
  `printf '%08x' N | xxd -r -p`.
- **New record**: a table-55 change with property `ADDR`, whose `new_value` nests
  the new table type, `dcty` (**2=player, 1=non-player**) and a fresh
  `db_unique_id`; all later changes reference that ID. One table-55 record can
  carry several ADDR changes.
- **Staff→player** on an existing record: `Ptyp` 1→2, paired with deleting the
  `PErt` retirement row.
- **Reference values** (club/nation/city/competition) = nested records with a
  `large` internal ID + an integer `DBID`. DBIDs are opaque (no names in XML).

### Key FourCCs
| Person (P) | | Non-player (N) | | Grid columns |
|---|---|---|---|---|
| `Pfna`/`Psna`/`Pfln` name | `Pdob` DOB | `Ncra`/`Npta` current/potential ability (0–200) | `year` (col `2036687218`) |
| `PCAB`/`PPAB` CA/PA (0–200) | `Pcbi`/`Pnti` city/nation | `Ncrr`/`Nwrr`/`Nhmr` reputations | `join`(`1785686382`)/`leave`(`1818583414`)/`left`(`1818584692`) |
| `PCRP`/`PHRP`/`PWRP` reputations | `Phes` height | `ND**` staff attributes | `apps`(`1634758771`)/`gols`(`1735355507`) |
| `Pcti` contract club | `Pcjd`/`Pcex`/`Pcsd`/`PCNj` contract dates | | `tjob` (5=manager, 11=player, 12=player-coach) |
| `PLsd`/`PLed` loan start/end | `Pskt`/`Psnu` shirt number | | |
| `PD**` player attributes (1–20) | `PM**` preferred moves | | |
| `Plhs` playing history | `Pnph` club spells / non-playing history | | |
| `PPsT` previous clubs | `Pacl` honours/achievements | | |
| `PErt` retirements | `Ptyp` person type (1/2) | | |
| `Piap`/`Pigl` intl caps/goals | `Ppro`/`Ptem`/`Pspo`/`Ploy`/`Ppre` personality | | |

Scale note: `PD**` player attributes are 1–20; CA/PA and reputations (P and N)
are 0–200. Prefer a CA/PA/reputation reading for ~200-valued N fields before
assuming a coaching attribute.

### History grids (`Plhs`/`Pnph`/`PPsT`) — cell-edit replay
Grids are sequential cell ops, matched to rows by their `olvl` snapshot:
- `lsop`: **0** insert blank row, **1** set one cell (`id`=column, `value`=new),
  **2** delete a row, **3** CLEAR the whole grid (the editor's Clear button; the
  author then retypes the career — Phil Neal FM24), **4** duplicate a row.
- Column FourCCs: `year`, `yror`, `join`, `leave`/`left`, `apps`, `gols`, `ytht`
  (youth flag), `team`, `divi`/`competition`, `tjob`.
- `olvl` carries the target row's prior state (year, dates, apps, gols, club…).
  `odvl` = the scalar old value (top-level fields).

### Dates: precise vs year-only
- **Precise**: `day=1 month=7 year=1992` = an exact date.
- **Year-only** (`day=0 month=0 year=2006`) = a season with no exact day; stored
  internally as a `1/1/1901` marker + the season year. **Shift its year like any
  other**, but see the round-trip limitation in §6.
- `1/1/1900` = empty/null date.

### Anchor season: empty vs filled last playing-history row
The season a player is anchored to is read from the LAST (max-year) `Plhs` row's
FINAL apps/goals:
- **Empty** (apps/goals cleared or never set) at year Y → current season
  `Y/(Y+1)`, current year **Y**. (Authored by issuing apps/goals CLEAR ops,
  `val=None`, on that row.)
- **Filled** (apps/goals >0, not later cleared) at year Y → prepared for the NEXT
  season, current year **Y+1**.

So two players ending at the same year can need different offsets to reach one
target. **Reliable signal = the LAST apps/goals op on the max-year row** (CLEAR →
empty; positive → filled). Do **not** read apps/goals from `olvl` — it shows the
pre-clear numbers and yields false "filled" positives.

## 5. The core rule — ordered-produced (history grid shifting)

Grid ops carry no row index; the editor finds the row by matching the op's `olvl`
against the state a prior op produced. `olvl` holds two kinds of reference needing
opposite treatment on a shift:
- **First-touch / real-DB refs** — the first op to touch a row cites its real DB
  values (edition-absolute; season labels never renumber across editions).
  **Leave unshifted.** Includes every `lsop=2` delete (they run first).
- **Chain refs** — a later op cites a value an earlier op already wrote. **Shift**,
  or the editor finds no row and silently drops the op.

**The rule:** per grid, keep a `produced` set of the SOURCE year/date values
written by prior `lsop=1` set ops. Shift an `olvl` year/date iff it is in
`produced`; then shift the op's own `new_value` and add its pre-shift value to
`produced`. Sentinels never shift. Ordering (not value range) disambiguates —
for a small offset real and target years overlap, but a first-touch/delete refs
a value *before* any op produces it. This unifies created and existing records.

## 5b. Cumulative files — one person, several record ids (v2)

A file re-saved edition after edition keeps every edit ever made (builds FM15…
FM24 in one file; the `version` integer on each change is the authoring editor
build: 2281 FM15, 2380–2382 FM16, 2469 FM17, 2637/2640 FM18, 2768/2773 FM19, 2961
FM20, 3032/3035 FM21, 3569 FM24). On load the editor maps each created record to
a **session id**; edits made then are saved under that id with **no ADDR** — a
"continuation id". The same legend can therefore sit under several ids, and may
also have been edited on a real DB record in one edition and recreated in another
(the duplicate names). Club refs also change kind: old editors store the integer
DBID (`Ttea 1687`), FM24 the `large` unique id — same club, never comparable.

**Identity linking.** Ids are unioned when an id's `olvl`/`odvl` snapshots that
match none of its own rows match another id's **current** state on ≥ 2
independent points (a season row with apps/goals, a club spell with both dates,
the exact previous `Pdob`) — or a clear winner (2× the runner-up). Created ids
never cite anyone. Club-only / year-only rows are too common (teammates) to link
on; contract dates likewise. Over-linking is the failure mode to watch: check
the report has no component with two different names (known duplicates aside).

**Live vs dead — resolved 2026-09-03.** Continuation ids are NOT dead. Editor
grids (England: Alan Smith, Bonds, Williams) show ops from every edition landing
or missing *individually*: the editor resolves each op's `olvl` to the FIRST row
that fits, so a relabel sequence "row reading (2016,0,0) → 2015, → 2014, …" hits
the same row repeatedly while the copies stay as identical junk rows, later ops
miss, and 1900 scratch rows survive. Kempes/Puchades "showing FM17" was such a
miss, not a dead id. Default `--continuations all`: anchor from every id of the
person = the literal-replay state the cleaner rebuilds from.

**Anchor from a relabelled row.** A later edition renumbers seasons via `year`
sets whose `olvl` carries the row's apps/goals; when no apps/goals op follows on
the max-year row, filled-ness is read from that snapshot.

## 5b2. Removing adapted retired-player records — `--drop-retired-adaptations`

Removed (every change on the id): existing records (no ADDR) adapted from an FM
retired-player entry — `Ptyp` old value **5**, or an EMPTY old date of birth on a
record that had a name (the retired-players table has no DOB and is already
player-typed: Hansen) — and **created shells** whose only changes are names and biography bits
(Rowley; their ADDR entry goes too; a created referee with `O***` attributes is
not a shell). England: 76 + 6 + 6 records / ~8.6k changes; Spain: 36 + 5 + 5. NOT removed, by decision: staff→player
adaptations (`Ptyp` 1→2, 233 in England) even when a created twin exists — the
staff record may resurface and then needs a manual edit; and same-name created
pairs (Moncur). Tom Finney / Tommy Finney are two players. Done before identity linking, so these records can no
longer fuse with created ones. Listed in the report.

## 5c. Career rebuild — `convert_edition.py --rebuild-careers` (created players)

Library in `clean_import.py` (replay / clean / emit); **run it through the
converter**, never standalone on a converted file (the standalone CLI re-links
ids on shifted values and grouped Shilton/Collins differently → leftover passes
applied on top of fresh rows, careers 1–2 seasons short; 2026-09-03 incident).
For each created player (ADDR `dcty=2`, not staff) the converter replays every
`Plhs` op of every linked id literally on the SOURCE (first-match; unmatched op
lost, no phantom rows), applies the rules — drop 1900/2100 rows; drop exact
duplicates (year, club, apps, goals); FLAG same year+club with different stats;
FLAG gaps; youth flag on EMPTY seasons at age ≤ 18 — **empty = no apps/goals
recorded (blank), a recorded 0/0 is a real season**; blank and 0 look alike in
snapshots (FM24 writes 0, older editors null) so matching treats them alike while
values keep the distinction — reads the **anchor from the rebuilt rows** (max year, filled → +1), REMOVES all old `Plhs` ops of the person
and writes one fresh sequence under the primary id, already shifted: insert row,
fill every cell, next row, ascending years, no dups, no relabels. Index- and
snapshot-matching agree, so the grid is exactly what is emitted. **Real DB records linked into a created person are left out of the rebuild**
(a member id with a `Ptyp` flip, or a `Pdob` old value the chain never produced,
acts on another database object — Mito, Portugal, was fused with an unrelated
player's rows). Their ops stay in the file and are shifted as before.
**Which earlier passes did the editor apply?** Unknowable directly; the author's
LAST pass cites the states he saw. `replay_best` tries every subset of the
intermediate passes and keeps the one under which most ops of the last pass
match (Tommy Smith: his FM18 renumbering never showed in FM24; the FM24 rework
cites FM16 states). **The saving editor's pass is trusted**: an unmatched set-op
of that pass materialises the row it cites WHOLE from the raw `olvl` — division,
youth/loan flags, order and dates included, not just year/apps/goals/club (John
Barnes lost every division that way), and rows that
pass never touched are dropped when the author retyped the same club/apps/goals
elsewhere (his view was the editor's scramble; club compared kind-agnostically).
**Doubled op lists** (whole first pass repeated verbatim, 33 England players e.g.
Hollins/Wise/Osgood/Harris/McCreadie): the repeat is dropped. **Deletes**: a
`lsop=2` is ignored when a LATER set-op of the person cites exactly the deleted
state — the author still saw that row (Hollins' FM17 deletes vs his FM18
relabels); otherwise it applies (Rowley's FM17 deletes of Bournemouth, Banks). **Transfer fees** are re-attached after the rebuild, not carried on rows: a fee
op cites the row as the author saw it and row states drift under first-match
replay (Ferdinand's fees landed twice and on a loan row). What the statement
says reliably is the CLUB, plus the author's FINAL figure when he retyped a
mistyped fee (Diouf, Muamba). Each fee then sits on the LAST season of that
club's spell = the season he left; a loan spell elsewhere does not split the
parent spell and a loan row never carries a fee; a club with several spells
takes the fee on the spell whose last season matches the statement's apps/goals,
else the one covering its year, else the last. A fee for a club absent from the
career is FLAGged, not placed (6 in England, 1 in Spain). **Loans**: a loan row
and a permanent row at the same club in one season are legitimate (Bentley:
Arsenal 1, Blackburn loan 2, Blackburn 3), not a duplicate. Transfer
seasons (two rows, same year, different clubs) are kept **with their row order**
(`yror`, FourCC 2037542770: 1 = first spell, 2 = second); rows left unset take
the smallest free numbers, the spell with a leaving date first. **Club and
competition references**: the VALUE keeps every part the source had (FM24: `large
Ttea` + `integer DBID`), the SNAPSHOT keeps only the key (`Ttea` / `competition`)
— a DBID inside a snapshot makes every later op on the row miss (Grobbelaar).
Cells carried: year, order, apps, goals, youth, **on-loan (`onln`
1869507694), transfer fee (`cash` 1667330920)**, join/leaving, club, division —
written stats/flags/dates first, club and division LAST, so a club
unknown to the target DB (Durban City is not in FM26) loses only those two cells. England: 450 players,
28,462 ops → 24,816; every rebuilt career ends 2024-filled or 2025-empty.
**A row with a club but no division is usually intentional** — an unknown
early-20th-century club, or a team whose competition is not in the database
(Keenor, Heron, Waddle, Barnes at Sudbury; 82 rows in England, 76 Spain, 4
Portugal): do not chase these. Validated in FM26 by the user: Banks, Bonds,
Williams, A. Smith, Grobbelaar, Collins, Shilton, Wright, Cunningham, Hollins,
Wise, Osgood, Harris, McCreadie, Neal, Keller, Riise, T. Smith, Hansen, Bentley,
Ferdinand, Townsend, A. Wright, Rowley, Barnes, Law, Bento, Coelho, Mito.
Output naming: `… - target2025 - clean.xml` / `.md`. Out of scope: existing DB
records, staff, `Pnph`.

## 5d. Club spells (`Pnph`, the editor's "Non Playing History") - NOT rebuilt yet

One row per stay at a club: club, date joined, date left, job. Only year-shifted
so far (the leap-day clamp applies). **Most players are already correct** - the
user verified Denis Law, Bentley, Trautmann, Woodcock, McDonald, Pallister,
A. Smith, Waddle, Ginola, Diouf. Audit script: `scripts/probes/audit_club_spells.py` (writes
`FM 26 XML Files/explanations/club-spells audit.md`). Everything it finds is a
SOURCE error carried over faithfully, in three classes:
- **more than one open-ended spell** - one open spell is the current club and
  loans nested inside it are normal; a second one means a missing leave date
  (Ferdinand's West Ham). England 24, Spain 0, Portugal 0.
- **a leave date no spell begins on** (allowing the normal one-day gap, 30/6 to
  1/7 and 31/12 to 1/1) - a typo, e.g. Ferdinand's Leeds date one year early.
  England 40, Spain 106, Portugal 17.
- **two spells at one club that overlap or touch** - one spell split in two or a
  duplicated row (Alan Wright's two Blackburn spells, Des Walker's two identical
  Forest rows). Fix by hand. England 47, Spain 4, Portugal 2.
Plus the class that is INVISIBLE in the file: a club missing from the FM26
database (Durban City, Grobbelaar) resolves to nothing and the date ops citing it
then miss, so the row goes blank. Only the target database reveals these; in
England only Grobbelaar references Durban.

Checks deliberately NOT made: "a club in the playing history with no spell" -
the editor does not require a spell per club and every case checked was correct.
Also note this audit replays the grid with the same first-match rule as the
rebuild, which is an APPROXIMATION of the editor: only 1/1/1900 means an empty
date, other 1900 dates are real scratch values later ops cite (Trautmann).

Also deferred: a playing-history row with no join/leave date where the spell has
them (McDonald at Oxford, Ginola) - source omission, "really really later".

## 5e. Real database records - `--rebuild-real-history` (Clear and rewrite)

Real records (no ADDR) are legends adapted from someone already in the FM
database, almost always a NON-player (`Ptyp` old value 1, 3 or 5).

**Why they need rewriting, not patching.** The record itself resolves - Rooney's
DOB and club do change in FM26 - but every GRID op fails, because an `olvl`
snapshot must be a COMPLETE, EXACT image of the row as the TARGET database holds
it. Proved by experiment (`TEST - row matching probe.xml`): correcting one
malformed field made a delete land, while removing a field or sending a minimal
snapshot failed, and rewriting a club to the FM24 long id failed too. Pre-FM21
snapshots name clubs and divisions with the old `integer` DBID where FM26 uses
the `large` id, and 703 of 782 England real records carry only those, so their
deletes and cell edits can never match. **`lsop=3` (Clear) carries no snapshot,
so it cannot fail** - and SETTING a value resolves an old id perfectly well; only
MATCHING compares raw ids. Hence: Clear the grid and write the career fresh.
User-confirmed in FM26 on Rooney and Drogba.

**The career comes from the author's own procedure**: he deletes every
playing-history row from the prime season onwards and relabels the rest by ONE
constant, touching every row - so each op's first-touch snapshot is an image of a
real row (year, club, apps, goals, dates) and the whole real career is in the
file. Kept rows = those a first-touch year op relabels and no first-touch delete
removes; shift = (target - 1 if the last kept season has apps else target) minus
the last kept real year.

**Club spells move with the career**, or the two grids would contradict each
other. They are DERIVED from the rebuilt career - consecutive seasons at one club
are one spell, and **a loan never interrupts the spell at the parent club**
(Lampard's season on loan at Swansea sits inside one West Ham spell, not between
two of them); the loan gets its own nested spell and never breaks the chain - and each spell's JOIN date is, in order of preference: the
author's own last value for that club (already shifted to the file's season, so
it needs only the person's offset) when it still fits the run; else the real
image shifted; else 1 July of the run's first season. A date is only accepted
when its SEASON matches the run's first season (a January join belongs to the
season that began the previous July - Henry joined Juventus on 18 January), and a
year-only date is never carried. **Each spell then ends exactly when the next one
begins**, which is what every correct example shows (Rooney 31 August, Henry
18 January, Drogba 1 January); the last stays open. England 5 of 593 spell sets
fail to chain, Spain 10 of 635, Portugal 0 of 118.
Two things do NOT work and were tried: reading the spells grid directly (its
dates are rewritten every edition and a chained snapshot is indistinguishable
from a real one - Drogba), and following the author's dates blindly (his spell
dates lag his career relabelling by an edition or two - Rooney).

**Scale.** England 637 of 791 rebuilt, Spain 624 of 875, Portugal 144 of 194.
Three refinements got the coverage there:
- **Dominant shift, not a single one.** A row that appears to move by some other
  amount is a second relabel of a row already counted, so the dominant shift wins
  and the strays are dropped (Makelele {10: 22, 11: 4}, Lucho Gonzalez
  {17: 12, 18: 1}). A genuine 50/50 split is refused as "no dominant shift"
  (Sergio Conceicao {24: 4, 14: 4}).
- **The author's own Clear** means the grid is authored from scratch, so it is
  replayed from empty like a created player. A Clear that leaves nothing behind
  is a leftover from an old pass and is ignored.
- **A person holding BOTH a created record and a real one** is the "removed then
  rejoined" case (Gudjohnsen, Ashley Cole): FM dropped the person, the legend was
  recreated, and the two records later coexisted. Refused - it needs a hand fix,
  as the user confirmed.
Refusals are listed in the report: no row kept, **the kept career has a hole**,
no dominant shift, two kept rows in one real season at one club, and the mixed
created/real case. That last one matters: a hole is the symptom of
the kept/deleted split misfiring, which it does when the author's own shift is
small and real years overlap produced years (Szczesny came out with only a Legia
youth season). Refusing keeps the record exactly as it was instead of letting the
Clear delete real seasons.
Ops grow - Clear + insert + fill is ~6 per row - England 27,850 -> 34,568.
**Not reproduced**, and counted per player in the report: the author's edits to
other cells of a real row (apps, goals, youth, division, order) and rows he
inserted or copied that were never deleted again.

**Multi-step relabelling.** A row is not always moved in one go: Sergio
Conceicao's 1992 season went to 2006 in one pass and 2006 to 2016 in the next,
so the first relabel alone reads as a split (four rows +24, four +14) and the
record is refused. When the first relabels have no majority, each row is
followed to the END of its chain instead - a relabel keeps the row's club and
stats, so (year, club, apps, goals) identifies the row at every step - and the
majority test is retried on those. Applied only as a rescue: using chain ends
everywhere loses more records than it saves, because a chained end can be
followed into an unrelated row whose key collides.


**A club the author never touched.** The rebuild only sees rows the author's own
ops mention, so a club he never edited does not exist for it, and the Clear takes
that club's spell away with it (Kolo Toure's ASEC Mimosas). Where the spells grid
holds a first-touch image of a spell at a club the rebuilt career never visits,
begun before the first season the file reveals, that spell is put back at the
head of the chain. The playing rows at that club cannot be recovered - nothing in
the file records them.

**One slot, two images.** Two rows in one season at one club are a real pair
when the database keeps them apart, by competition or by order within the season
(Beckham played four league games and none in Europe for United in 1994). The
SAME slot twice is ONE row seen at two moments, because the author edited a cell
and the later image reads as a second row: Giggs' 1990 appears as 0/0 and again
as 2/1, and 2/1 is the row. Keep the latest image that still records a figure -
a later blank image is him retyping the row, not wiping the season (Sam Field).

**Three refusals that were the model's fault, not the file's.**

- *A row relabelled twice from scratch.* The author re-reads a record from the
  real database in a later edition and relabels the same row again, so one row
  carries two first relabels (Essien's 2002, Mark Hughes' 1985 and 1986). Where
  one of them is the majority shift, that reading is kept; dropping the row
  punched a hole in a career that was perfectly consistent.
- *Two rows in one season at one club.* Legitimate when the database keeps them
  apart, by competition or by order within the season - Beckham played four
  league games and none in Europe for United in 1994. Only the same slot twice
  is a misread (the author edited a cell, and the row's later image reads as a
  second row).
- *A hole in the career.* Refuse only a hole the model MADE, where rows dropped
  as strays leave seasons the Clear would then delete for good. A hole that was
  always there is just a career: Hasselbaink spent 1993 and 1994 at clubs the
  database does not carry.

**A row is never thrown away for being out of step.** Two more ways a real
season hides from the rebuild, both found on Hasselbaink:

- *Parked on the blank year.* The author moves a row to 1900 and restores it a
  pass later (his Atletico season). A park is not a deletion - follow it to
  where the row ends up.
- *Nudged by a different amount.* A row inside the career relabelled by its own
  shift is a real season the author pulled apart from another row of the same
  season (his 1990), not a misread. Keep it where the database has it. Only a
  stray OUTSIDE the career is dropped.

Taking the first reading of a row instead of the majority one was measured and
is equivalent (England 693 vs 694, Spain 684 vs 688, Portugal 164 vs 165) - the
majority rule is kept because it is never worse.

**One club, two id kinds.** Older editors write a club's integer DBID, FM21+
writes the large unique id, and the relation is exact: unique = DBID *
4294967297, verified against every club reference in every file. They are
normalised to the DBID everywhere a club is compared. Before that, one club read
as two: Xabi Alonso's Real Sociedad seasons appeared twice, once under each kind,
which also split his shift count and refused the record.

**Two shifts one year apart are not a disagreement.** A calendar-year league
overlaps a European season, so Solano's 1996 in Peru and his 1997 at Boca are
deliberately the same target year. A shift set spanning at most one year is
accepted without needing a majority. Rows are still placed by ONE shift: placing
each row at the author's own chain-end target was tried and is worse - it
collapsed Beckham's three youth seasons onto one year.

**A record the author deletes.** DELE means the record is gone, so every other
change he typed on it is a guaranteed failure in the editor. Only the deletion
is kept.

**Deleted AND relabelled is kept.** In a cumulative file the same row can carry
both a delete and a relabel, because the delete belongs to a later pass over a
re-imported database. The relabel wins: you do not relabel a row you want gone.
Obeying the delete cost McCarthy a Porto season - two of his Porto rows have the
same 23 appearances, so one delete swallowed both.

**A B team is not a transfer.** If the player never changed main club - his B
team years run straight into the first team's - then the first team's spell
starts when he joined the B team, and the B spell sits inside it exactly like a
loan (Julen Guerrero: Bilbao Athletic 2019, then Athletic Club, so Athletic's
spell opens 1/7/2019). The author's own first-team date, a season later, does
not override it. B teams are recognised from FM's own short names, which the
search index carries as `search_terms`: Bilbao Athletic answers to "A. Bilbao B"
and Athletic Club to "A. Bilbao", so "<parent> B" (also II, C, 2) is the test.
Nothing is keyed on a club id.

**The B-team merge, in full.** After the B years are pulled into the first team,
the first team can sit on BOTH sides of them - Sergi Barjuan's Barcelona 2016 and
his Barcelona 2019 are one spell, not two - so consecutive runs at the same club
are coalesced. The date the player joined the CLUB is the earlier of the two
runs, never the author's own first-team date.

**The four dates on the contract panel.** Proved from Fernando Llorente's record
against the editor:

| Editor field | Property |
|---|---|
| Date Joined | `Pcjd` |
| Date When Moved To Based Nation | `PCNj` |
| Date Last Contract Signed | `Pcsd` |
| Contract Expires | `Pcex` |

**`odvl` is decoration on a scalar change; ORDER is what matters.** A probe set
one field four ways - the editor's own value, empty, no `odvl` element at all,
and the new value itself - and all four took (`FM 26 XML Files/xmls/TEST - date
joined probe.xml`). What actually loses a change is what comes AFTER it: setting
a player's CLUB resets his Date Joined to the game's own date, and the club
change sits later in the file than the rebuild does, so a date written next to
the career is overwritten before the import finishes. The contract dates are
therefore appended at the very END of the file, after every other change.

**The joined-club date follows the spells; the contract is only filled in.**
The author writes his joined-club date in whatever season he was working in, so
it drifts from the spells the rebuild produces (Pantic reads 2016 against a
Panionios spell starting 2021). The spell left OPEN is the current club and the
source of truth.

TWO properties hold that date, `Pcjd` and `PCNj`, and both are forced. Which one
the editor shows is not worth guessing: Bakero came out right with only `Pcjd`
written, while Zidane, Pochettino and Etxeberria stayed wrong, and the one thing
they had that he did not was a `PCNj` - twice CLEARED by the author, which empties
the field and leaves the database's own date on show. Following it only where it
already agreed with `Pcjd` was not enough.

The contract itself is never overruled, only filled in. A start or expiry the
author set is his and gets shifted like every other date. Where the file says
nothing, the FM database's own value stands - the start of the target season for
anyone under contract, which is where all those 1/7/2025 dates came from - so a
plausible one is written instead: the START somewhere between the day he joined
and 1 July of the target season, the EXPIRY at the end of a season two to five
years out. A field the author CLEARS counts as unset. The draw is seeded from
the record id, so the same file always converts to the same dates.

A shifted expiry that lands on or before the target season would leave the player
a free agent the moment the game loads, so it is pushed out to the end of a
season two to five years away, keeping the author's own day and month. This runs
per RECORD after the offset pass, on the last expiry the record carries, which is
the one the game reads.

**The blanked last row is the season he is BASED ON, not a season he played.**
The author clears the apps and goals of the final row - the season about to be
played - and that row does not belong in the rebuilt career: Varela's Estrela
row is his 2008/09 base season, so his history has to end at Huelva. The row is
dropped and the anchor falls on the last season that still records figures,
which is also how the shift comes out right (Varela +2, Capucho +1, whose own
file already ran to 2023). A CLEARED figure elsewhere in the career is still
left alone - see the Solano note above.

**The two grids agree by construction.** The spells are derived first and then
write their dates back onto the rows they came from: the first row of a run
carries the join, the last row the leave date, the rows in between carry neither.
Before this, Varela's 2022 Sporting row said he left on 30/6/2023 while his
Sporting spell ran to 1/7/2025. This covers rebuilt REAL records; a created
player's rows and spells are both the author's own, so they are left as he wrote
them.

**A row's dates belong inside that row's season.** The author edits a row's join
and leave dates in one pass and its year in another, so the two travel
separately and a date can end up decades from the season it sits on - Capucho
joining Vitoria on 1/7/2050, Varela on 1/7/2032, which then leaked into the club
spells because the spells take their dates from the rows. Every rebuilt row's
dates are re-anchored to its own season, day and month kept: month 7 or later
belongs to the row's year, earlier than July to the year after. Both rebuild
paths do it. Records left untouched keep the author's dates, drift included.

**1 January is a year, not a date.** The author's own spell dates are preferred
over a default because they carry real transfer days (Rooney's 31 August, Henry's
18 January). 1 January is the exception: it is what the editor holds when only
the year is known, so taking it literally puts a summer move in the middle of the
previous season. It is refused like a year-only date, and the spell falls back to
1 July of the season the run starts.

A LOAN between the B team and the first team does not break the pair either -
consecutive runs already mean no other main club in between (Voro: Valencia B,
a year on loan at Tenerife, then Valencia, which is one Valencia spell from
1/7/2014).

**The B-team test needs every club looked up FIRST.** `is_b_team` reads the name
cache, and an unfetched club silently is not anyone's B team - which is why the
rule fired for Guerrero (cached from an earlier run) and not for Canales. Every
club the careers and spells mention is now fetched in one sweep before the
rebuild starts, so the answer never depends on what happens to be cached.

Reading the relation off the CAREER instead was tried and abandoned: a season
spent at two clubs with neither on loan is exactly what a MID-SEASON TRANSFER
looks like, and it merged Abbondanzieri's Rosario Central with his Boca. The
club's own name is the only thing that separates the two.

**A rename with no record to rename.** An id that is NOT DBID * 4294967297 was
invented by an editor for a person the author CREATED, in an edition this file
no longer carries. Where all that survives is the rename (names and biography,
no history, no ADDR here), it lands on whoever holds that id now and gives a
stranger's career the legend's name - Luis Figo in the Spain file is two ops, a
surname and a date of birth. Dropped as dead weight.

**Spells the career cannot see.** The rebuilt career drives the spells, so a
club with no playing rows would vanish. Three carve-outs put it back:

- *A club before the career*, taken from the spells grid where the author never
  touched the playing rows (Kolo Toure's ASEC Mimosas).
- *A youth club with no join date in the database*, only a leave date, which
  never reads as a spell at all - the author's own dates for it are in the file
  (Xabi Alonso's Antiguoko).
- *The club whose leave date the author CLEARS*, which is him saying "he is
  there now". If that club has no seasons in the career it is his next move, and
  it becomes the final open spell (Benni McCarthy stops playing at Porto and is
  at Blackburn from the season after).

**Ids have names (`fm_names.py`, `--names`).** A changeset unique id is
DBID * 4294967297 for PEOPLE as well as clubs, and the search index behind
fmref.com is keyed on the DBID, so every record and club in a report can be
named. Endpoint (public search-only key, read it from the site bundle if it ever
stops working):

    POST https://1r3p0ghdzwktqxu9p-1.a1.typesense.net/multi_search?x-typesense-api-key=...
    {"searches":[{"collection":"detailed_game_items","q":"*","query_by":"",
                  "filter_by":"type_id:=person && fm_id:=2003443"}]}   -> David Beckham

50 lookups per request, answers cached in `fm_names_cache.json`, ids stay ids
when offline. `type_id` is one of person / team / competition / nation /
stadium, and fm_id is NOT unique across types, so always filter on both.

**Names settle a bad identity link.** Two ids that resolve to DIFFERENT people
were never the same person, whatever their DOB and club old-values suggested.
Six such links in the England file (Phil Neville fused with Alen Boksic, Ciaran
Clark with Paul Dummett, Andreas Weimann with Ben Osborn), and three of them
were the whole reason the record could not be rebuilt: a fused pair has two
careers, so it never has one dominant shift. Only ids whose name conflicts with
the group's first id are split off, so a legend recreated under several ids
stays whole.

**The author's division edits are replayed (`--rebuild-real-history`).** The
rebuild writes the row the DATABASE holds, so a division the author typed in
himself was being dropped - that is how Steinsson lost three of his. An edit
cites the row as it was, so it is matched on club, appearances and goals, and
where two rows share those, on the year it cites (every year that row has ever
carried is known from its relabel chain). Only unique matches are applied.

ONLY the division and the fee. A figure edit cannot be placed safely: the author
also DUPLICATES rows, and a duplicate is identical to its original at the moment
it is made, so an edit meant for one lands on the other - it put 4 appearances
on the Solano season that has 40. A CLEARED figure is likewise left alone; the
database's own number is the safer answer.

**Every change needs a `db_random_id`.** Each record in the file carries one, and
one written without it does not take - the database's own value stands and reads
like the conversion ignored the field (that is why the joined dates still showed
1/7/2025 after being written). Grid ops get one from `clean_import.wrap`; the
contract dates now get one too, drawn from the record id so a rerun is identical.

**A date of birth that does not fit its career** is listed, never guessed at. The
author moves the birth date and the career separately, edition after edition, and
they drift apart until the record says a seven-year-old played 36 league games
(Genar Andrinua: born 2009, career from 2016). Age is measured at the first
SENIOR season, since a youth row at 15 is normal, and anything under 15 or over
48 goes in the report for a hand fix.

**Naming a refused record.** Real records carry no name in the changeset, only a
unique id, so the report lists every refused record by id together with the
career the file reveals (real years, club id, apps/goals). Open the id in the
editor to recognise the player.


**Costs, accepted by the user:** a row the author never touched is destroyed by
the Clear, and a hole in the run of seasons is the symptom - such records are now
REFUSED rather than rebuilt. **A real record is never renamed, so the file holds
NO name for it**: the report identifies each one by record id, the shifted date of
birth and the club, which is what the editor can be searched by;
an old club id that no longer exists in FM26 leaves a blank club; the kept/deleted
split can misfire when the shift is small; the rewritten file no longer carries
the real-career images, so ALWAYS regenerate from the FM24 source; and a real
person edited in two country files now has his grids cleared twice, so the last
file imported wins outright.

Superseded probes in `scripts/probes/`, kept as a record of what does NOT work - do not resurrect:
`probe_real_replay.py` (42% coherent, 52% invented duplicates),
`probe_real_statements.py` (9%), `probe_real_strict_replay.py` (16%),
`probe_real_shift_model.py` (the model itself, 73% of records fit it).

**Retirements - earlier claim withdrawn.** A person only needs the `PErt` Clear if
a retirement row exists, which the file cannot reveal; Rooney and Ljungberg have
none and are fine.

## 5f. Season calendars - which nation gets 1/1 - 31/12 (v9)

A club's season boundaries are a property of its **NATION**, not its tier: the
Brazilian fourth division runs the same months as the Serie A, so one entry per
country covers every club in it. `CALENDAR_YEAR_NATIONS` in the converter is that
table; everything not in it is European (1/7 - 30/6). It holds Brazil, Bolivia,
Chile, Colombia, Ecuador, Peru, Paraguay, Uruguay, Venezuela and the four Nordics
(Norway, Sweden, Finland, Iceland - spring to autumn, unchanged for a century).
**Argentina is deliberately NOT in it** - see below.

**This governs DERIVED dates only.** A date the author typed himself always wins -
his grid is read first (§5c, `dates_from_spells`). A club whose nation the index
does not resolve falls back to European, which is what every derived date used
before v8, so a cache miss can never move a date that was already right.

**Ties settled by hand: `NATION_OVERRIDES` in `fm_names.py`.** A club FM flags
EXTINCT carries no nation in the index, so v10 reads the competitions on its rows
instead - and where two countries are named in equal measure it reports the tie
rather than guessing. An override supplies the nation for one of those, and is
applied OVER the cache (on load and after every fetch) so a rebuilt cache keeps
it. Only a club the index gives no nation can be overridden, so it can never
contradict FM. Chicago Sting is the first entry: its Italy rows name Italian and
American competitions equally, and FM's own short names say "Chicago (NASL)"
(user, 2026-09-08).

**Why nation and not division.** Both are in the same fmref index record. Division
goes null for a club outside a playable league - defunct, merged, dropped to
regional football - which is disproportionately where a legend's old clubs sit
(Argentina file: nation missing on 6 of 177 clubs, division on 8), and it would
need hundreds of competition names mapped instead of a few dozen countries.

**A nation is only in the table if its calendar never MOVED.** USER RULE
(2026-09-07): a league that has changed its season calendar cannot be described by
one constant, because which boundary is right depends on the SEASON, not the
country. `ERA_CHANGED_NATIONS` holds those, they keep the European default, and a
**real** record whose career touches one is reported instead (see below).
**Argentina is the case in point**: two championships inside one calendar year
through the 70s and 80s (Metropolitano and Nacional), then unified on the European
calendar (Apertura/Clausura), then back to a calendar year. This is also the
correction to an earlier reading of the data - the author dating Argentine clubs
1/7 - 30/6 is not him being sloppy, it is him being RIGHT for the era those
legends played in. **Brazil is the one volatile league the user is confident
enough about** to date 1/1 - 31/12 anyway. Do not add a nation on the strength of
its calendar TODAY without checking whether it has always been that way.

**The table is real-world calendars, NOT induced from the author's files.** The
report's **"Season calendars used for derived dates"** section lists every nation,
the calendar applied, the derived dates written, and what his own dates there
imply, plus a callout where the two disagree - so a wrong entry is visible rather
than silent.

**Judge that evidence on the JOIN date alone.** A spell's leave date belongs to the
club he is going TO, not the one he is leaving - a spell ends exactly when the next
one starts - so a Swede moving abroad correctly leaves on 30 June, and reading that
as European evidence against Sweden is simply wrong. Judging on the join/leave PAIR
put Sweden at 5 against 5 and the user (rightly) challenged it; on the join alone it
is **28 on 1/1 against 3**. Join dates across all five files: Norway 11-0, Sweden
28-3, Brazil 95-20, Uruguay 20-6, **Argentina 60-39** - the split one, which is its
calendar having moved. A callout needs a sample of 5+ AND a 70% lean, or it fires on
noise (Portugal 3-against-2, Romania 2-against-1 were false positives at a looser
threshold; South Africa's 5-0 is real).

**Report: "Real records in a league that changed its calendar".** REAL records
only - created players are the author's own invention and are already coherent, so
they are treated like any others and not listed. Nothing here is repaired or is a
converter fault; it is the shape of the career FM itself holds. Four signals,
built against the three records the user picked out of the Argentina file:
- **more than one row in a year** - Veron's 1996 is Boca 17 apps AND Sampdoria 32,
  an Argentine half-season and a European season sharing a calendar year;
- **apps over 50 in one row** - Bochini's 57 in 1977 is the Metropolitano and the
  Nacional added together (Fillol's 58 in 1974 and 56 in 1976 likewise);
- **no apps and no goals at all** - Celso Ayala's two Olimpia seasons;
- **a gap** - years with no row between two that have one.
Flagged: Spain 35, Italy 30, Argentina 17, England 7, Portugal 5.

**Report: "Club spells that disagree with their own career rows".** CREATED players
only - their spells grid is the author's own and is carried through untouched (only
year-shifted), so a mistake in it survives the conversion. Real records are not
checked: their spells are DERIVED from the career, so the two grids cannot disagree.
The rows at a club and the spell at that club must cover the same seasons; one year
of slack either way is allowed (a European season labelled Y ends on 30/6/(Y+1)).
Three shapes, all reported and never repaired:
- **spell runs past its rows** - Paulo Sergio's Novorizontino reads 2015-2017 against
  a single 2015 row;
- **spell ends before its rows do** (the inverse);
- **spell joins in the wrong season**.
The usual cause is a relabel pass that moved the JOIN dates with the rows and left the
LEAVE dates behind: Paulo Sergio's FM19 pass moved Novorizontino's join 2014 -> 2015
(right) and its leave 1/1/2014 -> 31/12/2017 (wrong), and did the same to Rio Branco.
Counts: Spain 209, England 154, Italy 137, Portugal 80, Germany 57, Argentina 1.

**Same-season joins are SPREAD across the season** (user rule, 2026-09-07). Two runs
starting in one season both derive that season's opening date, and the chain - a
spell ends when the next begins - then leaves the first of them starting and ending
on the same day. Petkovic played for Red Star, Sevilla and Real Madrid in 1995/96 and
Sevilla collapsed to 1/7 -> 1/7. Nothing in a career row says WHEN inside a season a
move happened, so the derived joins are spread evenly in row order - invented exactly
like the 1 July they replace, but ordered and non-degenerate. Two traps, both hit:
- **order by the row order WITHIN that season**, not the run's lowest row order
  overall - a run reaching into the next season is first THERE, which put Real Madrid
  ahead of Sevilla;
- **stop at the next move, not the season end** - the season after a calendar-year
  club opens on 1 January, and spreading to 30 June past it gave Racing Santander a
  two-day spell before Vitoria. A cross-calendar trap: it would hit every South
  American file.
Only DERIVED joins move; a date the author gave, or one read off the real database,
stands. Zero-length spells 366 -> 263 across the seven files. The remainder is NOT
this bug: 175 are the author's own on created players (his grid is carried through
untouched - Paulo Sergio's FM18 Novorizontino was 1/1/2014 -> 1/1/2014) and 88 are
still derived, in two shapes - a return to a former club where one of the two joins
came from the author or the real DB (Del Grosso, Montella), and records whose rebuild
was SKIPPED so the author's grid survives shifted (Causio, Gentile).

**RULE (user, 2026-09-07): a spell date of 0 is FILLED from the playing history.**
`fill_zero_spell_dates`. The author leaves a created player's Date Joined / Date Left
as **0** - FM's unset date - and the row then reads "0" in the editor even though his
PLAYING history carries the dates (Jair Rosa Pinto: all five spells 0, every career row
dated 1/1; Zico's created twin `Arthur Antunes Coimbra`: Flamengo join 0). Where a zero
sits, take the date from the spell the career derives for the same club.
- **Only zeros are written.** A date he typed stands; a blank Date Left on his current
  club stays blank (a blank is not a zero - there is no op to rewrite).
- **Matched as an order-preserving SUBSEQUENCE**, not one-for-one: his grid is often a
  subset of the career, listing the clubs that matter and skipping a loan or a return
  (Moacir Barbosa's grid reads Vasco then Ypiranga against a career of Ypiranga, Vasco,
  Ypiranga). If a row finds no club after the one before it, the whole player is left
  alone - the same all-or-nothing rule as `dates_from_spells`.
- **Rewriting a value means RE-THREADING the `olvl` chain.** Every op cites the row
  state it expects and the editor resolves that to the FIRST row that fits. Change a
  date and the next op on that row still quotes the value you just replaced, so it
  matches nothing and is **silently dropped** - Jair's Date Joined took and every Date
  Left stayed blank. After rewriting, walk that row's own ops in order and rewrite each
  later `olvl` to the state the row actually has. The source file is internally
  coherent; editing it in place is what breaks the chain. **This applies to ANY in-place
  edit of a grid op, not just this rule.**
- **It MUST run after the year shift.** A zero is a SENTINEL, so it survives the shift
  untouched; filling before the shift lets the shift run over the value just written.
  The created-career rebuild happens after the shift loop, so the fill sits at the end
  of that block.
Filled: Brazil 18 on 6 players, England 7 on 5, Argentina 1, Germany 1. Zero dates in
the output: Brazil 39 -> 21, England 27 -> 21, Argentina and Germany to 0. The
remainder is 32 created players whose grid could not be matched to the career and 11
real records whose rebuild was skipped (their grid is the author's, only shifted).

**Verifying a grid edit needs an EDITOR-FAITHFUL replay.** `replay_spells` reads ops in
file order and does NOT model first-match `olvl` resolution, so it showed Jair's dates
as applied when the editor would drop them - which is how the bug reached the user.
A faithful check simulates: `lsop 0` adds a blank row, every other op resolves its
`olvl` to the FIRST matching row, and an op that fits none is dropped. It reproduced
the symptom exactly (4 ops missing, all Date Left blank) and confirmed the fix (0).
Only meaningful for CREATED players - a real record's rows live in FM's database, not
in the file, so a from-empty simulation counts all their ops as misses.
**Finding:** the author's own created-player spell ops miss a lot even untouched -
Spain 343, Portugal 324, England 284, Italy 209, Germany 104, Brazil 8, Argentina 1.

**RULE (user, 2026-09-07): every report ENDS with a "Players to check" table.**
One row per player the report flags ANYWHERE - anomalies, anchorless, era-changed
league, spell/row disagreements, playing history not rebuilt, holes in the career,
all four date-of-birth classes, unreadable dates, ambiguous identity links - with
the **player's name (or id)** and the **club he is at (name or id)**, plus short
reason labels. The point is to work a file from ONE list instead of a dozen
sections; the detail stays in the section each reason names. The club falls back
from `Pcti` (only set where the author moved him) to the open club spell, then the
last spell, then the last club in the playing history; a "-" means the file carries
no club for him at all. Germany: 167 players, 24 without a club.

**Names come from parts as well as `Pfln`.** Plenty of created profiles carry no full
name, only `Pfna`/`Psna`/`Pcna` - Paulo Sergio is one - and reading only `Pfln` left
them all labelled "(existing DB record, no name change)" everywhere in the report.
`person_names` composes from the parts; on the German file that cut unnamed mentions
from 94 to 19.

**`db_random_id` is unseeded** (`clean_import.py`, module-level `random`), so two
runs of the same input are never byte-identical. Comparing outputs means
normalising `<integer id="db_random_id" .../>` out first - otherwise every file
looks changed.

Where the calendar is applied: run joins, B-team joins, loan joins **and loan
leaves** (a calendar-year season ends on 31/12 of its OWN year, a European one on
30/6 of the NEXT), the move after the last season played, both "1/1 means the
year, not the date" coercions (skipped where 1 January really is the season
opening), and the contract start/expiry in `sync_contract_dates`.

## 6. Known limitations (not converter bugs)

- **Year-only dates don't round-trip.** A row whose match key holds a year-only
  date (exported `0/0/YYYY`, stored as `1/1/1901`+year) can't be matched on
  import, so that op reverts and the row keeps original values. Hits the untouched
  source too. `--flag-year-only` lists them; fix by hand if it matters.
- **Source-authoring gaps.** A changeset may transport a row's dates but not its
  `year` cell (e.g. a manager's playing-history years, set only in the DB). The
  shift correctly moves what the changeset contains; it must **not** invent ops
  the author never made. Fix at source.
- **No cross-edition DB import.** The user edits in one editor (currently FM26)
  throughout; converting "for FM27" just bumps values. There is no FM26→FM27
  database, so failures are never edition/DB coupling.

## 7. Environment notes
- Python: use `/usr/bin/python3` (asdf shims fail without `.tool-versions`; same
  for ruby).
- Reddit URLs are not fetchable from Claude Code — ask the user to paste content.

## 8. Reference identifications (from test files, unverified vs a DBID map)
- Profiles decoded: Maradona @ Napoli (cat 4), Doesburg (cat 4, Dutch GK),
  Haaland @ Man City (cat 1), Navas → Levante (cat 2), Augusto Gama @ Rio Ave
  (cat 3, staff→player), Mourinho Benfica→Chelsea (cat 5), Batteux @ Reims (cat 6).
- **Regenerating a report overwrites hand-written preambles** — keep notes here or re-add.
- Converter validated on: the FM26 single-squad file (+1) and the Portugal FM24
  squad file (50k changes, 808 people + 9 clubs; `--target-season 2025` → mostly
  +2, with ~13 earlier-vintage players auto-given +3/+4/+5 and one 2028 data
  error flagged).
- v2 validated on the Spain FM24 cumulative file (143k changes, 3331 ids → 3005
  people, 208 multi-id, builds FM15–FM24): Adelardo +2, Kempes +7, Puchades +8
  as the user read them; 71,170 values shifted, zero unexpected diffs. Output in
  `FM 26 XML Files/xmls/`, report in `FM 26 XML Files/explanations/`. Confirmed
  in FM26 by the user (Adelardo correct). England FM24 file also converted
  (204k changes, 4243 people, mostly FM18/19 vintage).
- **Duplicates are expected**: a legend first adapted from a real "retired
  player" record that FM later removed was recreated from scratch, so both
  records coexist (e.g. Gordon Banks: real record FM16 vintage + created FM18
  vintage; 21 such name pairs in England). Each converts on its own anchor and
  they converge to the same state. Cleaning them is the next step ("clean while
  importing"), not the converter's job.
- 75 England records carry their whole change list twice verbatim (source
  quirk); editor behaviour on replay unverified.

## 9. Example — converting a new file

Bring any file (single or mixed vintage) to the current 25/26 season, shifting
managers too, and list rows needing a hand-check:

```
/usr/bin/python3 scripts/convert_edition.py \
  "IN.xml" "OUT.xml" --target-season 2025 --shift-staff --flag-year-only \
  --report "OUT.md"
```

Then: ask the user to confirm the manager shift before relying on it; read the
printed offset spread and any ANOMALIES; check `OUT.xml.year-only.txt`; and
validate the output against the source (see §3) before importing.

