# Resume note — updated 2026-09-09

Read `CLAUDE.md` first for the format and converter rules. This note is only
about where the work stopped.

## What is on disk and safe to load

**All 34 files (33 countries + the FM18 Portugal file) are promoted to v26** in
`FM 26 XML Files/xmls/`, reports in `explanations/`, previous build archived in
`old/` as `- v22`. The user has loaded and tested the v26 Portugal merge.

Merged file, tested in the FM26 editor:
`FM 26 XML Files/merged/FMPT Legends - Portugal FM24 + FM18 - target2025 - merged.xml`

## Frozen versions

| file | what it is |
|---|---|
| `convert_edition_v26.py` / `clean_import_v26.py` | what produced every promoted file |
| `convert_edition_v27.py` | **v26 + three fixes, NOT yet batched or promoted** |
| `extract_squad_v3.py` | what produced the tested merge |
| `extract_squad_v4.py` | **+ the authored-grid change, not yet used for a shipped merge** |

The working copies (`convert_edition.py`, `clean_import.py`, `extract_squad.py`)
are at v27 / v4 - ahead of what is promoted.

## STOP: the next step is a batch + diff, then promote

```
# 1. convert all 34 to scratch, promoting nothing
./resume/batch_template.sh <scratch-dir>        # writes <scratch>/batch23/*.xml + .md

# 2. diff every career against the promoted files, per identity group
/usr/bin/python3 resume/diff_careers.py <scratch>/batch23
#    -> must print "0 regressions". Do NOT promote otherwise.

# 3. re-cut the merge
/usr/bin/python3 extract_squad.py \
  "FM 26 XML Files/xmls/FMPT Legends - Portugal FM18 - target2025 - clean.xml" \
  "FM 26 XML Files/xmls/FMPT Legends - Portugal - target2025 - clean.xml" \
  --clubs-file resume/pt_clubs.txt --contract-only --merge-identities \
  --normalise-addr --out "...merged.xml" --report "...merged.md"
```

`resume/fm18-v28b.xml` is the FM18 file already converted on v27, if a re-run of
that 113 MB file is not wanted. `resume/pt_clubs.txt` is the 102 resolved club
ids (Unidos de Lisboa and Uniao Santarem are SKIPPED by the user's decision -
FM has no record answering to either).

## The three fixes waiting in v27 / v4

All three came out of the user's editor test of the merged file.

1. **Year-only spell dates showed as `0`.** `fill_zero_spell_dates` only helps a
   person whose career was REBUILT. Everyone else kept `0/0/2024`, which FM
   displays as `0` - Danilo Pereira's six spells named the right clubs with no
   dates at all. `fill_spell_dates_from_calendar` now derives the day and month
   from the club's own season. NOTE the leave rule: a leave in year Y ends the
   season FINISHING in Y (that is what makes multi-year spells chain), EXCEPT
   where he wrote the same year for join and leave, which means one season.
2. **A date FM cannot read poisons its whole row.** Eduardo Luis has
   `join = 0/0/7`. The editor rejects the write, so every later op on that row
   cites a state that never existed and is dropped in silence. Those writes are
   now removed (even the row's last one) and the row falls back to the last date
   FM can hold. 14 writes on 14 people in the Portugal file.
3. **An existing record's UNREBUILT grid must not be carried by the merge**
   (`extract_squad --keep-authored-grids` puts it back). Those ops describe FM's
   database as it was in the SOURCE edition, so in the target they insert on top
   of a career the game already holds: Danilo Pereira gained a year-1900 row,
   duplicate 2016 Parma rows and twin 2022 Estoril youth rows; Jose Martins
   gained 1993 four times. 2,862 ops on 109 people now stay behind and the
   silent-drop risk falls from 2,943 ops to 81.

   **The user knows the cost**: Jose Joao's carried career was CORRECT and he is
   in those 109, so he falls back to FM's own record. Awaiting no decision - the
   trade was stated and not objected to, but confirm before shipping if it comes up.

## Verification rules — both of these bit me today

- **`clean_import.replay` ignores `lsop=4` (Duplicate).** Judge an emitted file
  with `probe_editor_replay.replay`.
- **A name-keyed id lookup only finds ids that SET a name in that file.** Group
  by identity the way the converter does (`extract_squad.people_index`) and
  replay the whole member set. Both mistakes made Thomas Finney look unchanged
  when he had lost half his career.

## Still open

- **The user's editor test of the NEXT merge** is the gate on all three fixes.
- Eduardo Luis: his playing history is **missing the division on the Benfica
  row** - reported, not yet looked at.
- Jose Martins was also **left unshifted** (rows still 1983-1997) on top of the
  duplicate-row problem. Worth checking after fix 3 removes the duplicates.
- Marco Silva, Jaime Pacheco, Vitor Pontes, Carlos Brito are MANAGERS - the user
  is handling them himself.
- Dito, Bosingwa, Rui Vieira, Arnaldo Correia de Carvalho and Ewerton are not in
  the FM26 database at all (removed between editions). Nothing to fix.
- 19 name-only carries in the merge report - the user has not said any are
  duplicates yet.
- The 493 spell-disagreement rows: the reports already list them per player, per
  club, with the wrong value and what the career says. The user called that
  format fine. The one improvement offered and not yet done: state the exact
  DATE to type, not just the year.
- `convert_edition.py` draws `db_random_id` blind, so its own output carries a
  few collisions (3 in 59,350 Portugal ops). The extractor seeds from the target
  and draws unused ids; the converter still does not.


---

# 2026-09-09 — the spell-date fixes were ABANDONED. Do not retry them blind.

Converter is back on **v26** (`convert_edition.py` == `convert_edition_v26.py`,
`clean_import.py` == `clean_import_v26.py`). All 34 clean files stay on v26,
untouched. Only the EXTRACTOR moved, frozen as `extract_squad_v5.py`.

## Why: a spell row's identity IS its snapshot

Three attempts at filling year-only spell dates each damaged grids elsewhere, in
different places, and the cause is structural: `Pnph` rows are resolved by
matching the `olvl` snapshot, so ANY date the author left half-written can still
be the thing that tells two rows apart. Rewrite it and his `team` op lands on the
wrong row, the club is lost, and `replay_spells_ops` drops the row entirely.

Measured damage, per attempt (all against the v26 files):

| attempt | damage |
|---|---|
| year-only + `1/1` coercion, per-row re-thread | Candido de Oliveira 11 spells -> 4, Pedroto 14 -> 11, Guttmann 24 -> 21, ~80 records over the batch |
| same, re-thread moved into `replay_spells_ops` (correct for Duplicate rows) | unchanged - the re-thread was never the cause |
| year-only ONLY, no `1/1` | 45 problems in the FM18 file - Armando Fati lost 8 dates |
| **unreadable-date drop alone**, nothing else | still 47 problems |

Even the last one - just removing 14 writes with year < 1000 - moves rows. There
is no version of "rewrite the spells grid" that is safe without a per-person
proof, and the shape guard I wrote (`_spell_shape` + roll back) did NOT catch it
all, so the guard is not sound either.

The abandoned code is kept at
`<scratch>/ce-abandoned-spellfix.py` and `<scratch>/ce-with-fill.py` for
reference only. If this is ever picked up again: the ONLY safe shape is
Clear-and-rewrite the whole grid (what `--rebuild-real-history` already does for
careers), never an in-place edit of the author's snapshots.

## What actually fixed the user's three records

`extract_squad_v5.py` - the merge no longer carries an EXISTING record's history
grid unless the converter REBUILT it (a rebuild opens with a Clear, so its cells
land on rows it made itself). Plus: **`Plhs` and `Pnph` travel together** for an
existing record - carrying a rebuilt spells grid beside a dropped playing history
leaves the two describing different careers. 11 records in the Portugal merge are
split that way. `Pacl` is judged alone (achievements say nothing about seasons);
pairing it would have cost ~50 good rebuilt careers for nothing.

Verified in the re-cut merge: Danilo Pereira, Jose Martins, Jose Joao, Rui Vieira
and the REAL Eduardo Luis (dbid 4101439) carry no `Plhs`/`Pnph` at all - only
attributes, contract and the `Pcti` club move. Created legends are untouched
(Djukic 14 rows gap-free, Ziad 10, Tavares 11, Serafim 7, Barbosa 9).

**Careful with names**: there are TWO Eduardo Luis records - the real FM person
(17615546375640383) and a created one (3890043253036842494). The created one
keeps his grids by design. Always check `fm_names.dbid()` before concluding a
drop failed.

## Merge as it stands (awaiting the user's editor test)

`FM 26 XML Files/merged/FMPT Legends - Portugal FM24 + FM18 - target2025 - merged.xml`
190,424 ops (was 193,455) - the FM24 block verbatim and in order, 1,069 people,
2,861 authored grid ops left behind on 109 people, silent-drop risk down from
2,943 ops to 81.

## Still open

- Year-only spell dates still show as `0` for CREATED players the career cannot
  date. Unfixed by choice - see above. It is not a regression; v26 always did this.
- The 493 spell-disagreement rows (reports already list them per player/club).
- `convert_edition.py` draws `db_random_id` blind (3 collisions in 59,350 ops).


---

# 2026-09-09 later — four rules added, Portugal + Portugal FM18 on v29

Frozen: `convert_edition_v29.py`, `clean_import_v26.py` (unchanged),
`extract_squad_v7.py`. **Only Portugal and Portugal FM18 are promoted to v29**
(the user asked for a merge-only run); the other 32 files are on **v26**. A v28
batch WAS promoted across all 34 earlier in the day and then rolled back for
these two - if the other 32 ever need v29, re-run and diff them.

## The four rules

1. **`authored_date_ok` - a `1/1` join is a placeholder only on the career's
   FIRST run.** There it is an undated youth arrival, and taking it literally puts
   the arrival in the following season (Lucho Gonzalez: Huracan 1/1/2015 against a
   row labelled 2014, now 1/7/2014). Anywhere later it is a real winter transfer
   and is KEPT - Djukic left Vojvodina 31/12/2016 and joined Sutjeska 1/1/2017.
   Refusing lets the derived date stand, which is computed from the run's start
   year; coercing in place could not, since 1/1/2015 would become 1/7/2015.
2. **`ERA_CHANGED_NATIONS` is now empty.** Argentina's membership never changed a
   date - it is not in `CALENDAR_YEAR_NATIONS`, so its clubs always derived
   European boundaries - it only flagged 161 rows for a hand check. USER DECISION.
3. **`spells_need_rebuild` - created players' spells are rebuilt only when the
   author's own grid is DEFICIENT**: no spells, a date the editor draws as 0, or
   clubs that disagree with the career. Rebuilding all of them (560 people)
   regressed Djukic, whom the user had validated; the narrow rule is 187 people
   and fixes Eduardo Luis's zeros plus the 493-row disagreement class.
   The decision is taken BEFORE the shift loop, because a grid we do NOT rebuild
   must keep being shifted like any other.
4. **The contract club outranks the spells.** Where `Pcti` names a club he only
   ever appeared at ON LOAN there is no definitive join, and the fallback was the
   parent club's (Tulipa's Date Joined read 1/7/2019, the day he joined Porto).
   Now: Date Joined = the target season's opening day, the spell he is leaving
   closes 30/6 the day before, and a second spell opens at the new club - so a
   loan turned permanent ends with TWO rows at that club. 418 people across all
   files, 10 in FM24 Portugal, 59 in FM18 Portugal. Runs BEFORE `emit_spells`.

## Extractor: a spell for a moved person

`spell_add_ops` appends one open spell at the contract club for a person whose own
grid was left behind (55 in the Portugal merge). Add, then club, then join date,
each citing the state the row is really in - the editor resolves a blank-row
snapshot to the LAST match, which is the row we just added, so it does not depend
on the target's contents. `Ttea` carries the club's DBID, NOT the scaled uid
(writing the scaled value showed `6339371730372` instead of the club name), and
the join date comes from his own `Pcjd` where he set one.

**Known limit, stated to the user**: the club he is LEAVING cannot be closed from
the merge - finding his open spell means matching a row only the target game
knows. So Danilo Pereira shows a Marítimo spell AND his Al-Ittihad spell open.
`--no-move-spell` opts out.

## Verification gap worth knowing

`diff_spells.py` is USELESS once spells are rebuilt on purpose - every row
legitimately changes. Use `resume/check_spells_quality.py`, which asks absolute
questions instead: how many spell dates does the editor draw as 0, and do the
spells name clubs the career does not. The Djukic regression slipped past BOTH
`diff_careers.py` (it reads only `Plhs`) and `diff_spells.py`; it was found by
reading the record. Read the validated names after any spell change.

Portugal pair, v26 -> v29: 18 careers changed with 0 regressions; spell dates
shown as 0 went 223 -> 115, club mismatches 287 -> 278.

## Merge as it stands (awaiting the user's editor test)

190,798 ops, FM24 block verbatim and in order, 486 ADDR creations each its
person's first op, 1,069 people. Verified in it: Tulipa (both Salgueiros spells,
Date Joined 1/7/2025), Danilo (Marítimo 1/7/2023), Eduardo Luis created (real
dates), Lucho (1/7/2014), Djukic (14 rows, unchanged from what the user
validated).

## 2026-09-09 — v30: blank divisions filled from his own career

`convert_edition_v30.py`. Portugal + Portugal FM18 promoted (v29 archived); the
other 32 files remain on v26.

`fill_blank_divisions(rows)` gives a career row with no DIVISION the one his
other rows at that CLUB use, most common wins. Nothing is invented and no
external table is consulted - Eduardo Luis's first Benfica season (a youth year)
had none while his later Benfica row carried the Portuguese Premier League, so
the value came from his own record. A legend's old club outside any playable
league still gets nothing, which is correct: that is why the field is null there.
Runs in BOTH rebuild paths. 21 rows in FM24 Portugal, 94 in FM18 Portugal.

v29 -> v30: 69 careers changed, 0 regressions, spells untouched (223->115 zeros
and 278 club mismatches both unchanged, as expected).

## Danilo Pereira: what the source actually contains

Asked by the user 2026-09-09. His FM18 record has **50 `Plhs` ops that resolve to
exactly ONE row**: 2024 Clube Sport Maritimo, 28 apps, 1 goal, Portuguese Premier
League, no join or leave date. The other 44 ops resolve to nothing - they cite
FM18 rows that do not exist in FM26 - and they were the "garbage" he saw.

So the career he wants is NOT in the file: only that single season is. It could
be appended with the same Add-based shape `spell_add_ops` uses (safe, does not
depend on the target's contents). NOT implemented - the user was told and said
"if so, no problem". Offer it again if he asks.

## 2026-09-09 — v32 promoted to ALL 34 files

`convert_edition_v32.py` + `clean_import_v26.py` + `extract_squad_v7.py`.
Every clean file is on v32; the v26 archives are in `old/`.

**A correction to the note above**: the v28 batch WAS promoted across all 34 and
only rolled back for the Portugal pair, so 32 files sat on v28 (the over-broad
spell rebuild) for part of the day. All 34 were restored to the v26 archive to
give the diffs a true baseline before v32 went out.

### `spells_need_rebuild` narrowed AGAIN — dates only

The club-mismatch trigger had to go. It is the 493-row "spells disagree with the
career" class, but rebuilding on it repairs the disagreement by DELETING what
disagrees, and what disagrees is often real: **Bobby Tambling** lost Cork City,
where he went with no playing record, and his genuine mid-season move to Crystal
Palace (1/1/2022, the career has him at both clubs in 2021) came out 1/7/2021
because `fits` refuses 1 January categorically for a rebuilt spell.

So the trigger is: no spells at all, or a date the editor draws as 0. 872 spells
rebuilt across the batch, down from 8,951 on the broad rule.

**The 493 disagreements stay REPORTED, not repaired.** Repairing them needs a rule
that ADDS career rows to match the spells, never one that deletes spells to match
the career.

### Checks, all against the true v26 baseline

- `resume/diff_careers.py` — 465 careers changed, **0 regressions**
- `resume/check_spells_quality.py` — spell dates drawn as 0: **251 -> 122**;
  spells naming a club the career does not 1379 -> 1486 (the +107 is the 419
  definitive spells the loan rule now ADDS at contract clubs)
- `resume/check_validated.py` — **0 of 18 validated records failed**

### `check_validated.py` exists because the other two lied

Tambling was broken while every aggregate check reported zero problems:
`diff_careers.py` reads only `Plhs`, and the spell diff is meaningless once
spells are rebuilt on purpose. The new script re-reads the records the user has
personally validated and FAILS on a career row lost, a new hole, a dropped op,
**a spell count dropping** (the one that let Tambling through), or a usable spell
date becoming unusable. Keep its VALIDATED dict up to date as he confirms records.

### The reports' closing table

`## Players to check` is the last section in all 34 reports: Player, Record id,
Club, What to check (reasons joined with `;`). 2,806 players flagged in total,
113 without a name and 448 without a club - in those the file says nothing and
the index has no entry, so the record id is the identifier. 12 reason classes,
heaviest: no anchor 1,164, playing history not rebuilt 696, spells disagree 587,
DOB does not fit 319, DOB never edited 290, hole in the career 141.

Added this session: the year-only match-key classes (`Pnph` 35, `Plhs` 7) had
sections of their own but never reached the table. The name resolver now tries
EVERY member id against the index, not just the primary.

## 2026-09-09 — folder reorganised, deliverable assembled

See `README.md` for the layout. Three things changed on disk:

1. **All scripts live in `scripts/`** - the five working modules at the top,
   `checks/`, `batch/`, `probes/`, `inputs/`, and `archive/` (54 frozen
   versions). `fm_names_cache.json` moved with them: `fm_names.py` resolves it
   from `__file__`, so it must stay beside that module. Hardcoded
   `sys.path.insert` lines and the `FM 26 XML Files/xmls` paths inside the checks
   and probes were repaired for the move; the ARCHIVE copies were not - they
   still carry the old paths and will not run without `scripts/` on the path.
   Run everything from the project ROOT.

2. **`FM 26 XML Files/final_xmls/` is the deliverable**: 33 files, 0.84 GB - the
   32 country files plus the ONE merged Portugal file. The plain Portugal file and
   the Portugal FM18 file are deliberately excluded. Three `TEST - *.xml` probe
   files were found loose in `xmls/` (one of them writes Wayne Rooney) and moved
   to `FM 26 XML Files/probes/` - never import those. The user renamed `xmls/` to
   `converted_xmls/` himself; the checks were updated to match.

3. **`final_xmls/PLAYERS TO FIX.md`** joins all 34 closing tables: 2,635 players,
   columns File / Player / Club / Reason to fix / Record id, plus by-file and
   by-reason summaries. Portugal FM18 is FILTERED to the people the merge actually
   carried (204 rows, not ~370) - the rest of that file never reaches the game.
   Regenerate with `scripts/checks/join_players_to_fix.py`, which reads the
   merged report's "People carried" table to do the filtering.

Import order is the user's own manual step - 49 people have a history grid
written by two files and the last import wins; the list is in the session notes.
