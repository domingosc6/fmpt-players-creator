# fmpt-players-creator

Tooling for **FMPT Legends**: Football Manager editor changesets that bring
legendary players into FM26. Three tools live here:

| folder | what it does |
|---|---|
| [`scripts/`](#edition-converter-scripts) | **Edition converter.** Shifts an older edition's changeset (FM18, FM24) onto the 2025 season, rebuilds careers and club spells, and merges one edition's squads into another |
| [`creator/`](#legends-creator-creator) | **Legends Creator.** Builds FM26 changesets from a spreadsheet: creates the players FM26 lacks and fixes the ones it has, using web sources |
| [`placements/`](#placements-placements) | **Placements research.** Proposes a club and a senior/youth/retire slot for each player on a sheet, from FM26 careers, caps and squad sizes |

`CLAUDE.md` holds the changeset format notes and every converter rule. Read it
before touching a script. `HANDOFF-resume.md` is the running log of decisions
and traps.

## Requirements

- Python 3.10 or newer, standard library only. Run everything with
  `/usr/bin/python3` (or `python3`) **from the repo root**, except `placements/`
  (see below).
- An FM26 Editor install, for the scripts that read the FM26 database
  (`scripts/fm_db_*.py`, `creator/fm26_*.py`).
- Internet access for the FM club/person search and the creator's web sources.

## Not in the repo

The data and everything the scripts regenerate stay out of git (see
`.gitignore`). A fresh clone needs them copied in before it can do real work:

| path | what it is |
|---|---|
| `FM 18 XML Files/`, `FM 24 XML Files/` | the author's original changesets. Read only |
| `FM 26 XML Files/` | converter output: `converted_xmls/`, `final_xmls/` (the 33 files to import), `explanations/`, `merged/`, `probes/` (never import these) |
| `creator/cache/` | FM26 database extracts and every web page already fetched. Rebuilt on demand, but slowly |
| `scripts/fm_names_cache.json` | FM search lookups, filled as the converter runs |
| `placements/xlsx/` | the project's squad spreadsheets |
| `Legends Creator/`, `Legends Creator.zip` | the packaged creator, rebuilt by `creator/make_package.py` |

`creator/ids.json` **is** tracked: it records the id of every created player.
Keep exactly one copy of it. A second copy gives the same player a new id and FM
shows him twice.

## Edition converter (`scripts/`)

| path | what it is |
|---|---|
| `convert_edition.py` | the converter. Shifts an edition onto a target season, rebuilds careers and club spells, repairs dates, writes the report |
| `clean_import.py` | the row model and emitter for a playing-history grid |
| `fm_names.py` | FM search-index lookups (club and person names, nations) over `fm_names_cache.json` |
| `extract_squad.py` | lifts a club's people out of one changeset into another, and merges |
| `probe_editor_replay.py` | editor-faithful grid replay, including Duplicate. Use this to judge an emitted file, never `clean_import.replay` |
| `fm_db_people.py`, `fm_db_world.py`, `fm_db_names.py`, `index_people.py` | readers for the FM release databases |
| `merge_changesets.py`, `rebuild_lost_records.py`, `name_rebuilt_records.py`, `reissue_nwui.py`, `repair_type_change.py`, `type_change_first.py`, `untick_late_youth.py`, `fill_attributes.py`, `fill_city_of_birth.py` | repairs applied to an emitted changeset |
| `checks/` | what must pass before promoting a build |
| `batch/batch_template.sh` | converts every source file to a scratch directory, promoting nothing |

Convert one file:

```
/usr/bin/python3 scripts/convert_edition.py "FM 24 XML Files/FMPT Legends - Italy - Squads - FM24.xml" OUT.xml \
  --target-season 2025 --flag-year-only --rebuild-careers \
  --drop-retired-adaptations --rebuild-real-history --names --report OUT.md
```

Before promoting a build, all three checks must pass:

```
/usr/bin/python3 scripts/checks/diff_careers.py         <scratch dir>   # 0 regressions
/usr/bin/python3 scripts/checks/check_spells_quality.py <scratch dir>   # zeros must not rise
/usr/bin/python3 scripts/checks/check_validated.py      <scratch dir>   # 0 failures
```

`check_validated.py` exists because the other two are not enough: they once
both reported zero problems while Bobby Tambling had lost a club spell and had
a real January transfer flattened to July. Keep its `VALIDATED` list current as
records are confirmed. `checks/diff_spells.py` only means something when spells
are not being deliberately rebuilt. `checks/join_players_to_fix.py` regenerates
`PLAYERS TO FIX.md` from the reports.

## Legends Creator (`creator/`)

```
python3 creator/create_legends.py "<sheet>.csv" --out-dir "creator/out/<team>" --import-downloads
```

The sheet's columns are
`Position, Name, Nation, Team[, Team Id], Season, Website[, alternate_website], Exists[, Id][, CA, PA, CR, HR, WR][, DOB]`.
`Exists` = Y or an FM26 id means fix, N means create. Examples are in
`creator/inputs/`. Each run writes one merged `... - all.xml` per sheet, plus a
`.xml` and `.md` report per player and a summary.

| path | what it is |
|---|---|
| `create_legends.py` | entry point: reads the sheet, creates or fixes each row |
| `build.py`, `fix.py`, `model.py` | building a new player, rewriting an existing one, the shared row model |
| `fm26_*.py` | FM26 database extracts (people, world, history, leagues, achievements), cached in `creator/cache/` |
| `sources/` | web sources: national-football-teams, Wikipedia, carrierecalciatori, foradejogo, zerozero, bdfutbol |
| `bookmarklets/` | zerozero and bdfutbol sit behind Cloudflare. Open `bookmarklets.html`, drag the buttons to the bookmarks bar and click them on a player's page; `--import-downloads` moves the saved files into the cache. `make.py` rebuilds them from `sources/*_extract.js` |
| `club_overrides.json`, `division_overrides.json`, `levels.json`, `template.xml` | hand-kept club and division pins, league levels, changeset header/footer |
| `verify.py` | replays a person's club spells the way the editor applies them, to check an emitted changeset |
| `make_package.py` | builds the portable `Legends Creator/` folder (code, cache, README) for another computer |

`creator/PLAN.md` holds every rule the creator follows; `creator/HANDOFF.md`
is where the creator work last stopped.

## Placements (`placements/`)

These scripts read and write paths relative to `placements/`, so run them from
inside it (`cd placements && python3 squads.py`). Each step writes a JSON file
the next one reads; the JSON outputs are not tracked.

| script | what it produces |
|---|---|
| `xlsx_read.py` | minimal `.xlsx` reader, no openpyxl |
| `squads.py` | every club block (senior and youth names) in `xlsx/*.xlsx` → `squads.json` |
| `find_assigned.py` | every squad cell that already names a sheet player → `assigned_hits.json` |
| `profiles.py` | FM26 profile per sheet player: nation, DOB, club, position, career → `profiles.json` |
| `enrich.py`, `levels.py` | club and competition names, nations, reputations, each club's two highest league levels → `comps.json` |
| `caps.py`, `caps2.py` | senior caps from national-football-teams.com → `caps.json` |
| `tm.py`, `wiki_pos.py` | positions and nationality from Transfermarkt and Wikipedia |
| `digest.py` | joins profiles, squads and existing assignments into the per-player digest the proposal is written from |
| `santa_clara/` | the same pipeline for the Santa Clara sheet, ending in `propose.py` |

The written-up proposals are `Avulsos - placements.md` and
`Avulsos - sheet edits.md`.
