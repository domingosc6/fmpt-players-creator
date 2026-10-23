# FMPT Legends — folder layout

Everything here converts Football Manager editor changeset XML so transported
legends land in the **2025** season, and merges an older edition's squads into a
newer one. `CLAUDE.md` holds the format notes and the converter rules; read it
before touching a script.

## What to import into the FM26 editor

`FM 26 XML Files/final_xmls/` — **33 files, the deliverable.** The 32 country
files plus ONE merged Portugal file. Do not also import the plain Portugal file
or the Portugal FM18 file: the merged one already carries every Portugal FM24 op
verbatim, and the FM18 file is only an extraction source (it edits 13,304 people,
of whom ~1,000 travel).

`FM 26 XML Files/final_xmls/PLAYERS TO FIX.md` — every report's closing table
joined into one list: player, club, reason, record id. Regenerate with
`scripts/checks/join_players_to_fix.py`.

## The rest of `FM 26 XML Files/`

| folder | what it is |
|---|---|
| `converted_xmls/` | the converter's own output, one per source file, plus `old/` archives per build. This is the promotion target; `final_xmls` is a copy of the subset that ships |
| `explanations/` | one report per converted file, each closing with its "Players to check" table |
| `merged/` | the FM24 + FM18 Portugal merge and its report |
| `extracts/` | earlier standalone squad extracts, superseded by `merged/` |
| `probes/` | hand-built editor test files. **Never import these** |

## Sources

`FM 18 XML Files/`, `FM 24 XML Files/` — the author's original changesets. Read
only; nothing writes here.

## `scripts/`

| path | what it is |
|---|---|
| `convert_edition.py` | the converter. Shifts an edition onto a target season, rebuilds careers and club spells, repairs dates, writes the report |
| `clean_import.py` | the row model and emitter for a playing-history grid |
| `fm_names.py` | FM search-index lookups (club and person names, nations) over `fm_names_cache.json` |
| `extract_squad.py` | lifts a club's people out of one changeset into another, and merges |
| `probe_editor_replay.py` | editor-faithful grid replay, INCLUDING Duplicate. Use this to judge an emitted file, never `clean_import.replay` |
| `checks/` | what must pass before promoting a build - see below |
| `batch/batch_template.sh` | converts every source file to a scratch directory, promoting nothing |
| `probes/` | one-off investigation scripts, kept for reference |
| `archive/` | every frozen version. `*_v32.py` is what produced the current files |

Run everything **from the project root**, e.g.

```
/usr/bin/python3 scripts/convert_edition.py "FM 24 XML Files/FMPT Legends - Italy - Squads - FM24.xml" OUT.xml \
  --target-season 2025 --flag-year-only --rebuild-careers \
  --drop-retired-adaptations --rebuild-real-history --names --report OUT.md
```

## Before promoting a build, all three must pass

```
/usr/bin/python3 scripts/checks/diff_careers.py         <scratch dir>   # 0 regressions
/usr/bin/python3 scripts/checks/check_spells_quality.py <scratch dir>   # zeros must not rise
/usr/bin/python3 scripts/checks/check_validated.py      <scratch dir>   # 0 failures
```

`check_validated.py` exists because the other two are not enough: they once both
reported zero problems while Bobby Tambling had lost a club spell and had a real
January transfer flattened to July. Keep its `VALIDATED` list current as records
are confirmed. `checks/diff_spells.py` is kept but is only meaningful when spells
are NOT being deliberately rebuilt.

## Handoff notes

`HANDOFF-resume.md` is the running log of decisions and traps - the most
important file here after `CLAUDE.md`. `HANDOFF-extractor.md` covers
`extract_squad.py`; `HANDOFF-players-to-check.md` covers the flagged-record
backlog.
