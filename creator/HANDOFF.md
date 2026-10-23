# Creator: where we stopped (2026-10-08)

Read `PLAN.md` first; its "Decided" and "Fix mode" sections hold every rule agreed so far.

## State
- Creator probe (Dainelli, not in FM26): `out/FMPT Legends - creator probe - Dainelli.xml`. NOT yet imported by the user.
- Fix probe (Gattuso, FM26 DBID 3801681, non-player): `out/FMPT Legends - fix probe - Gattuso.xml`,
  prime 2002 at Milan into 2025 (probe default the user has not confirmed). Verified: 135 changes, 0 dropped (now with Pird/Pirc and Pdcn). NOT yet imported.
  Rebuild: `/usr/bin/python3 creator/create_legends.py creator/inputs/fix_probe.csv` from the project root.

## Next
- The user's import results for both probes. For Gattuso, check: type is player, Plhs = FM rows 1992-2001 +23, fees shown as EUR 3,499,092 / 7,615,350, Pnph 4 spells, contract at Milan.
- Sheet format + any nation done 2026-10-08 (test: inputs/sheet_test.csv, 5/6 pass, João Pinto refused as ambiguous). levels.json still Italy-only (fallback only).
- FM26 DOB for non-players (people_db reader only works for players today) - would remove the NFT dependency for DOB.
- Calendar-year nations done 2026-10-08 (Dalbert created: Barra Mansa 2008-2012 inclusive, Fluminense mid-2012).
- bdfutbol done 2026-10-08 (Junquera). carrierecalciatori parser still to do.
- Nicola Berti is NOT in FM26 (57060220 is a different Berti, career 2006-14): he is a creator case.

## Running on another computer
- Bookmarklets for zerozero/bdfutbol: `bookmarklets/bookmarklets.html` + `--import-downloads` (PLAN, "Running without Claude"). Needs FM26 Editor, the zstd CLI, and Python 3.14 only to rebuild the decoded caches (or copy creator/cache/).

## Traps
- `probe_editor_replay` cannot read Pnph. Use `verify.py`.
- FM26 zstd needs Python 3.14 or the zstd CLI; the creator runs on 3.9 and caches decompressed tables in `cache/`.
- `ids.json` re-seeds from ALL of `FM 26 XML Files/` on every run.

## Legends Creator package (2026-10-09)
`python3 creator/make_package.py` builds `FMPT-Legends/Legends Creator/`: the creator, the scripts/
modules it imports, template.xml (changeset header/footer), README. Code is refreshed on every
run; ids.json and cache/ are copied only when the package has none (the carried copies win).
RETIRED 2026-10-23: run from the git repo on both computers instead, and sync
`creator/ids.json` through git (pull before, commit + push after). Running from the package
writes its own ledger, outputs and cache, which then have to be merged back by hand.
create_legends.py restarts itself in
Python's UTF-8 mode (Windows). Without "FM 26 XML Files" beside it, the id ledger keeps the
used ids it already holds.
