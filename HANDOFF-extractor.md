# Handoff — `extract_squad.py`, the squad extractor (built 2026-09-08)

Read `CLAUDE.md` in this folder for the changeset format. This note is only about
the extractor.

## What it does

Lifts a club's people out of one changeset and adds them to another, without
disturbing what the target already says.

```
extract_squad.py OLD.xml NEW.xml OUT.xml --clubs "Benfica,102890" --report R.md
                 [--clubs-file f] [--dry-run] [--scalars-only]
                 [--allow-cross-edition]
```

- **Who is selected**: everyone the OLD file places at a named club. Club comes
  from `Pcti` (contract club) first — that op exists only where the author MOVED
  someone, which is 492 of 808 people in the Portugal file and **100% of created
  players** — then the grid fallback: open spell -> last spell -> last club in the
  playing history. A B team counts as its parent club.
- **Clubs by id or name.** Names resolve through the fmref index, which still
  names an EXTINCT club even though it drops its nation.
- **What moves**: every op on the person, in file order (order carries meaning —
  a club change resets Date Joined, so contract dates must land after it),
  including the `ADDR` record that creates a player. Staff included.
- **Conflicts**: if the target already changes the same person+property, nothing
  is written and it is reported. Never overwritten.
- **Authoring builds are reported** (added 2026-09-08 after the first guard was
  found unsound). A grid op is a cell edit matched to a row by its `olvl`
  snapshot; a snapshot that fits no row is dropped **silently**. Lifting does not
  change that — the editor applies each op against the loaded GAME database, not
  the file — so what matters is the build that AUTHORED the op, not either file's
  header. The report tables every authoring build and flags the grid ops older
  than the target file.

## EXTRACT FROM THE CONVERTED `- clean` FILE, NOT THE RAW FM24 ONE

Measured on Liverpool out of England:

| source | grid ops at build 3569 | old-build grid ops (at risk) |
|---|---|---|
| raw `FM 24 XML Files/...England...FM24.xml` | 1,051 | **2,796** |
| v10 `FM 26 XML Files/xmls/...England...clean.xml` | 3,516 | **710** |

The rebuild re-emits careers as fresh build-3569 ops, so 75% of the silent-drop
risk disappears. The 710 left are records the rebuild refused plus created
players whose grids are carried as authored. The converted file also selects a
slightly different population (61 people vs 50) because rebuilt spells give the
open-spell fallback more to work with.

## Proof run (Benfica: Portugal FM24 -> Spain FM24)

61 people (44 created, 17 existing), **8,214 ops carried**, 2 conflicts (`PLcl`
on Gonçalo Guedes and João Félix). Verified on the output: target's 143,279 ops
untouched and in order; all 44 ADDR records carried and each is its person's
FIRST op; fresh `db_random_id` on every emitted op. Named legends include Béla
Guttmann (342 changes) and Cosme Damião, confirming staff come across.

## Three bugs found while building it — do not reintroduce

1. **An `ADDR` record is table type 55 and its outer `db_unique_id` is a constant
   `4294967297`, shared by every creation in every file.** The person created is
   the `db_unique_id` NESTED in `new_value`. Keying on the outer id made all 186
   creations in a file look like one change and **silently dropped every created
   player**. `op_key()` exists for this.
2. **Never update the conflict set while emitting.** A history grid is hundreds of
   cell ops sharing one (person, property) key, so a running set makes a person's
   second op collide with his own first and carries a broken half-career. Decide
   once, against the target's ORIGINAL contents.
3. **Created legends cannot be named from the index** (invented ids). Use
   `ce.person_names(changes)` on the FILE — it reads name PARTS (`Pfna`/`Psna`/
   `Pcna`), not just `Pfln`.

## Known gaps / next steps

- **Not yet tested against a real target the user cares about.** The proof runs
  used Spain (raw and converted) as a stand-in target. Still need to know what
  the real target file is.
- **Not yet loaded in the FM26 editor.** Nothing here is confirmed against the
  editor — that is the real test, especially the carried ADDR + grid combination.
- **Club-table (type 3) changes are not carried** — only people. If a lifted
  squad depends on the club record itself being edited, that is missing.
- `--scalars-only` and `--dry-run` are implemented but untested.
  `--allow-cross-edition` was REMOVED: the header-build guard it belonged to could
  never fire, because `convert_edition.py` never rewrites headers, so a converted
  FM26-ready file still reports the FM24 build 3569 that saved it.
- **Club name ambiguity is refused, with the nations named.** `Liverpool` matches
  the English club (676) and Liverpool Futbol Club of Uruguay (1920) - different
  season calendars - so the script asks for an id rather than picking.
- Whether a lifted person's dates should be re-shifted to a different target
  season has not been considered; today the ops carry their dates as-is, which is
  correct only when both files are on the same season.
