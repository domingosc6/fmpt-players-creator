# FMPT Players Creator

Python tooling for **FMPT Legends**, a Football Manager community database that
brings football legends into the current game. Each legend is "transported"
from his prime season into the target season (FM26, 2025/26), with his career
history shifted so it lines up with the new game.

The tools read and write **Football Manager editor changesets** (the XML files
the FM Editor imports) and, where needed, the FM26 release database itself.

| Tool | Folder | Purpose |
|---|---|---|
| [Edition converter](#edition-converter) | `scripts/` | Moves an older edition's changesets (FM18, FM24) onto a target season: shifts dates, rebuilds careers and club spells, repairs dates of birth, and writes a report per file |
| [Legends Creator](#legends-creator) | `creator/` | Builds FM26 changesets from a spreadsheet: creates the legends FM26 lacks and fixes the ones it already has, using public football data sources |
| [Placements](#placements) | `placements/` | Proposes a club and a squad slot (senior, youth or retired) for each player on a sheet, from FM26 careers, international caps and squad sizes |

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Data that is not in the repository](#data-that-is-not-in-the-repository)
- [Edition converter](#edition-converter)
- [Legends Creator](#legends-creator)
- [Placements](#placements)
- [Repository layout](#repository-layout)
- [Further documentation](#further-documentation)

## Requirements

- **Python 3.10 or newer**, standard library only: no packages to install.
  **Python 3.14** is recommended. It is required to rebuild the FM26 database
  extracts, unless the `zstd` command-line tool is installed.
- **Football Manager 26 Editor**, for the scripts that read the FM26 release
  database. It is found automatically in any Steam library on macOS or
  Windows; set `FM26_EDITOR_DIR` to the editor's folder to use another
  location. Without the editor, copy a populated `creator/cache/` from a
  machine that has it.
- **Internet access**, for the FM search index and the Legends Creator's web
  sources.

Every script can be run from any directory: it locates the repository's data
from its own path. Paths given as command-line arguments are relative to the
current directory.

## Installation

### macOS

```bash
git clone <repository-url>
cd <repository>
python3 creator/create_legends.py --help
```

On macOS, prefer `/usr/bin/python3` or a python.org install. Version-manager
shims (asdf, pyenv) fail when no version is selected for the directory.

### Windows

1. Install **Python 3.14** from [python.org](https://www.python.org/downloads/)
   (select *Add python.exe to PATH*) and **Git for Windows**.
2. Clone the repository: `git clone <repository-url>`.
3. Enable Python's UTF-8 mode once, then open a new terminal:
   ```
   setx PYTHONUTF8 1
   ```
   The data files are UTF-8. `create_legends.py` enables the mode by itself;
   the other scripts rely on this setting.
4. Run the scripts with `py`, for example:
   ```
   py creator\create_legends.py "creator\inputs\<sheet>.csv" --out-dir "creator\out\<team>"
   ```

`scripts/batch/batch_template.sh` is a Bash script; on Windows, run it from Git
Bash.

The repository stores every file byte for byte (`.gitattributes`), so line
endings are identical on every platform.

## Data that is not in the repository

The source data, caches and generated output are excluded by `.gitignore`.
Copy them into a fresh clone as needed:

| Path | Contents | Needed for |
|---|---|---|
| `FM 18 XML Files/`, `FM 24 XML Files/` | the original edition changesets (read-only sources) | the converter |
| `FM 26 XML Files/` | converter output: `converted_xmls/`, `final_xmls/` (the files to import), `explanations/` (reports), `merged/`, `extracts/`, `probes/` (editor test files, never imported) | the converter and its checks |
| `creator/cache/` | FM26 database extracts and every web page already fetched | the Legends Creator (rebuilt on demand from the FM26 Editor, which takes about half a minute) |
| `scripts/fm_names_cache.json` | FM search-index lookups | optional; filled as the converter runs |
| `placements/xlsx/` | the project's squad spreadsheets | Placements |
| `work/` | intermediate files shared by `scripts/index_people.py`, `clubs.py`, `classify*.py`, `report2.py` and `rebuild_lost_records.py` | those scripts only |

### The id ledger

`creator/ids.json` **is** tracked. It records the id of every player the
Legends Creator has created, so the same legend keeps the same id across runs
and machines. There must only ever be one ledger: two diverged copies give the
same player two ids, and FM then shows him twice. When working on more than
one machine, `git pull` before creating players and commit and push
`creator/ids.json` immediately afterwards.

## Edition converter

`scripts/convert_edition.py` moves an edition's changeset onto a target season.
With `--target-season`, it computes a separate offset for each player from his
last playing season, so a file mixing several editions lands on the same
target.

```bash
python3 scripts/convert_edition.py \
  "FM 24 XML Files/FMPT Legends - Italy - Squads - FM24.xml" OUT.xml \
  --target-season 2025 --flag-year-only --rebuild-careers \
  --drop-retired-adaptations --rebuild-real-history --names --report OUT.md
```

| Option | Effect |
|---|---|
| `--target-season YEAR` | make every player current for season YEAR/YEAR+1 (2025 = 2025/26), with a per-player offset |
| `--offset N` | add N years to everyone instead |
| `--rebuild-careers` | created players: replay, clean and rewrite the playing history |
| `--rebuild-real-history` | existing database players: rebuild the playing history with the shift model |
| `--drop-retired-adaptations` | remove changes to FM retired-player entries that the legends were recreated from |
| `--shift-staff` | also shift managers and staff, by the majority player offset (off by default) |
| `--continuations {current,none,all}` | which later ids of the same person count when choosing the anchor season (default `current`) |
| `--flag-year-only` | list rows with year-only dates, which do not round-trip in the editor |
| `--names` | name people and clubs in the report, from the FM search index |
| `--report FILE.md` | write the conversion report |

`scripts/batch/batch_template.sh <scratch dir>` converts every source file into
a scratch directory without touching the published output.

### Validating a build

Before a build replaces the files in `FM 26 XML Files/converted_xmls/`, all
three checks must pass against it:

```bash
python3 scripts/checks/diff_careers.py         <scratch dir>   # 0 regressions
python3 scripts/checks/check_spells_quality.py <scratch dir>   # problem counts must not rise
python3 scripts/checks/check_validated.py      <scratch dir>   # 0 failures
```

`check_validated.py` re-reads a list of records that have been checked by hand
in the editor. It catches regressions that aggregate checks miss, such as a
lost club spell or a transfer date flattened to the default. Add records to its
`VALIDATED` list as they are confirmed.

`checks/diff_spells.py` is only meaningful when club spells are not being
rebuilt on purpose. `checks/join_players_to_fix.py` collects every report's
"players to check" table into `final_xmls/PLAYERS TO FIX.md`.

### Modules

| Module | Role |
|---|---|
| `convert_edition.py` | the converter |
| `clean_import.py` | row model and emitter for playing-history grids |
| `probe_editor_replay.py` | replays a grid exactly as the editor applies it; use it to judge an emitted file |
| `extract_squad.py` | moves a club's people from one changeset into another, and merges |
| `fm_names.py` | club, person and nation names from the FM search index, cached in `fm_names_cache.json` |
| `fm_db_people.py`, `fm_db_world.py`, `fm_db_names.py`, `index_people.py` | readers for the FM release databases |
| `merge_changesets.py`, `rebuild_lost_records.py`, `name_rebuilt_records.py`, `reissue_nwui.py`, `repair_type_change.py`, `type_change_first.py`, `untick_late_youth.py`, `fill_attributes.py`, `fill_city_of_birth.py` | targeted repairs to an emitted changeset |

## Legends Creator

`creator/create_legends.py` turns a spreadsheet of players into FM26 editor
changesets. A player FM26 does not have is **created**; a player it already
has is **fixed** (moved to the chosen club and prime season, with his career
history rewritten).

```bash
python3 creator/create_legends.py "creator/inputs/<sheet>.csv" --out-dir "creator/out/<team>" --import-downloads
```

| Option | Effect |
|---|---|
| `--out-dir DIR` | where the changesets and reports are written |
| `--only NAME` | rebuild only this player (repeatable); the others are merged from the files already in `--out-dir` |
| `--import-downloads [DIR]` | first move saved bookmarklet pages from DIR (default `~/Downloads`) into the cache |
| `--target-season YEAR` | the season the legends move to (default 2025 = 2025/26) |
| `--ids FILE` | the id ledger (default `creator/ids.json`) |

Each run writes one changeset and one Markdown report per player, a merged
`FMPT Legends - <sheet> - all.xml` to import, and a summary.

### Input sheet

A CSV with the columns
`Position, Name, Nation, Team[, Team Id], Season, Website[, alternate_website], Exists[, Id][, CA, PA, CR, HR, WR][, DOB]`.
Examples are in `creator/inputs/`.

| Column | Meaning |
|---|---|
| `Position` | `GK RB CB LB DM CM AM RW LW ST`, or the Portuguese `GR DD DC DE Mdef/MD MC MAC/MO ED EE PL` |
| `Team` | a club name or an FM26 club id (or use the `Team Id` column). `RET` retires the player: no club, retired on 30/6/2024 (`Exists` must hold his FM26 id) |
| `Season` | first year of his prime season (1995 = 1995/96) |
| `Website` | his page on a supported source (below) |
| `Exists` | `N` to create the player; `Y` or his FM26 id to fix him |
| `CA, PA, CR, HR, WR` | current/potential ability and current/home/world reputation (0-200; `PA` may be negative); written only when filled. A fix never changes position or nationality |
| `DOB` | date of birth (`30/10/1975`), used by a fix when no source gives one |

Supported sources: national-football-teams.com, Wikipedia (any language),
carrierecalciatori.it, foradejogo.net, zerozero.pt and bdfutbol.com.

zerozero and bdfutbol block automated requests. For those, open
`creator/bookmarklets/bookmarklets.html` once and drag its two buttons to the
browser's bookmarks bar. Then open each player's page, click the matching
bookmarklet to save it, and run with `--import-downloads`.

### Modules

| Module | Role |
|---|---|
| `create_legends.py` | command-line entry point |
| `build.py`, `fix.py`, `model.py` | creating a player, fixing an existing one, the shared row model |
| `fm26_people.py`, `fm26_world.py`, `fm26_history.py`, `fm26_leagues.py`, `fm26_achievements.py` | FM26 database extracts (dates of birth, cities, playing history, league history, achievements), cached in `creator/cache/` |
| `fm26_install.py` | locates the FM26 Editor and decompresses its database |
| `sources/` | the web sources |
| `bookmarklets/` | the zerozero and bdfutbol bookmarklets; `make.py` regenerates them from `sources/*_extract.js` |
| `verify.py` | replays a person's club spells as the editor would, to check an emitted changeset |
| `club_overrides.json`, `division_overrides.json`, `levels.json` | hand-maintained club and division mappings and league levels |
| `template.xml` | the changeset header and footer |

The rules the creator follows are documented in `creator/PLAN.md`.

## Placements

`placements/` proposes where each player on a sheet should go. Each step writes
a JSON file in `placements/` that the next step reads; these outputs are not
tracked.

| Step | Output |
|---|---|
| `squads.py` | every club's senior and youth names from `xlsx/*.xlsx` → `squads.json` |
| `find_assigned.py` | squad cells that already name a sheet player → `assigned_hits.json` |
| `profiles.py` | FM26 profile per player: nation, date of birth, club, position, career → `profiles.json` |
| `enrich.py`, `levels.py` | club and competition names, nations, reputations and each club's two highest league levels → `comps.json` |
| `caps.py`, `caps2.py` | senior caps from national-football-teams.com → `caps.json` |
| `tm.py`, `wiki_pos.py` | positions and nationality from Transfermarkt and Wikipedia |
| `digest.py` | the per-player digest the proposals are written from |

`xlsx_read.py` is a minimal `.xlsx` reader with no dependencies.
`santa_clara/` runs the same pipeline for one specific sheet.

## Repository layout

```
creator/            Legends Creator
  inputs/           example and working input sheets
  sources/          web data sources
  bookmarklets/     browser helpers for zerozero and bdfutbol
  ids.json          id ledger (tracked)
scripts/            edition converter and database readers
  checks/           build validation
  batch/            batch conversion
placements/         squad placement research
CLAUDE.md           changeset format notes and converter rules
HANDOFF-*.md        working notes
```

## Further documentation

- `CLAUDE.md`: the changeset format, the FM data model and every rule the
  converter applies. Read it before changing a script.
- `creator/PLAN.md`: the Legends Creator's rules.
- `HANDOFF-resume.md`: the decision log, including known pitfalls.
- `HANDOFF-extractor.md`: `extract_squad.py`.
- `HANDOFF-players-to-check.md`: the backlog of records flagged for review.
