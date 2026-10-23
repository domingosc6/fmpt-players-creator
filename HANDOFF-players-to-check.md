# Handoff — the flagged-records backlog (re-run of 2026-09-08 15:03)

Read `CLAUDE.md` in this folder for the format and converter rules. This note is
only about the flagged-records backlog.

## Where things stand

All 33 files were re-converted **2026-09-08 15:03**, XMLs and reports together, in
`FM 26 XML Files/xmls/` with the reports in `explanations/`. That run carries the
Chicago Sting fix below. Flagged rows **2,575** (the earlier v10 run had 2,697).

Numbers below are all from the 15:03 reports. Re-derive them after any re-run -
they move.

Every report ends with a "Players to check" table (one row per flagged person,
with the club he is at and short reason labels). Nothing in it has been repaired
and none of it is necessarily wrong.

## Q1 — DECIDED (2026-09-08): four reason families are closed, no work

These are by design. They are reported so the record is visible, not because
anything is pending. **They close 1,026 of the 2,575 rows outright** — every
reason those rows carry is one of these.

| flags | reason | why it is closed |
|---|---|---|
| 1082 | no anchor, dates left unshifted (incl. `anchor reads YYYY`) | no last-season anchor to compute a per-person offset from; the standing preference is an unshifted record over a guessed one |
| 253 | DOB never edited, add the years by hand | no `Pdob` op means no `odvl`, and the FM index carries no dates of birth, so there is nothing for the converter to write onto. The report already states the exact years — editor work, not code work |
| 130 | league changed calendar (Argentina) | `ERA_CHANGED_NATIONS`; deliberately reported, never re-dated |
| 48 | date the editor cannot read | year < 1000 (FM's unset 0, or his typos: 198, 201, 209). Nothing in the file says which digit he dropped |

## What is actually left: 1,549 rows, of which 1,102 are workable

| flags | reason | note |
|---|---|---|
| 670 | playing history NOT rebuilt | **only 220 are workable** — see below |
| 519 | club spells disagree with career rows | CREATED players only; the largest tractable bucket |
| 199 | DOB still does not fit the career | repaired DOB implausible against the first senior season |
| 122 | hole in the rebuilt career | a gap where a row the author never touched may have been |
| 66 | identity link not made | two ids that may be one person |
| 29 | DOB correction refused by the age guard | computed DOB gave an implausible age |

Dropping the refusals with nothing in the file to work from leaves **1,102 rows**,
**946 of them with both a name and a club** — that is the hand-workable list.
Heaviest: Spain 290, Italy, England, Other Nations, Germany, France, Portugal.

## Q2 — the 670 refusals, grouped (open)

Parsed from every report's `### Left untouched` section. The 15:03 run added a
refusal class that v10 did not have: *every id for this person was invented by an
editor, so FM's database holds no record to rebuild*.

| count | refusal | material in the file? |
|---|---|---|
| 426 | no row is kept — **"no readable season"** | none |
| 68 | no row is kept — a real career IS listed | yes |
| 86 | every id invented by an editor — a career IS listed | yes |
| 24 | every id invented by an editor — no readable season | none |
| 65 | no dominant shift | yes |
| 1 | the kept career has a hole | yes |

450 of 670 reveal no season at all, so no code recovers them. The workable slice
is **220**, not 670.

**Recommended before those 220: the 519 spell disagreements.** The reports state
the fix themselves — *"Real records are not listed: their spells are derived from
the career, so the two grids cannot disagree."* The 519 are all created players,
whose careers are already fully rebuilt by replay, which is the same input the
real path derives from. §5d says `Pnph` is simply not rebuilt for them yet, and
half the machinery is already wired (created careers take join/leave dates from
his spells grid where available and derive the rest). Extending §5e's derivation
there removes the category by construction rather than by guessing which of his
two grids he meant, and §5e's preference order (his own value for that club when
it fits the run) is what keeps the records already verified by hand — Denis Law,
Trautmann, Woodcock, Pallister — unchanged.

Risk: it touches every created player, not only the 519 flagged spells, so it
needs a before/after diff on those verified names before going near the clean
files.

## Q3 — DECIDED (2026-09-08): Chicago Sting is American

The club is EXTINCT so the index gives it no nation, and its rows name Italian
and American competitions in equal measure, so v10 reported the tie and left it
on the European default. FM's own short names settle it: `team:72023998` answers
to **"Chicago (NASL)"**.

Fixed in `fm_names.py` as `NATION_OVERRIDES` — applied *over* the cache on load
and after every fetch, so a rebuilt cache keeps it, rather than a hand edit
buried in the 7 MB cache file.

Verified by re-converting Italy (`/usr/bin/python3`, same flags, to a scratch
path). The whole report diff was: the tie bullet gone, a new
`The United States of America | calendar year | 4` row, and the 4 dates leaving
the unknown/European bucket. Nothing else moved.

**Shipped.** The 15:03 run regenerated every file, and the Italy report now
carries the USA calendar-year row. Nothing left to do here.

## Useful commands

```
# same flags v10 used (note --names: without it the namer is off and every
# nation falls back to the European default)
/usr/bin/python3 convert_edition.py \
  "FM 24 XML Files/FMPT Legends - Italy - Squads - FM24.xml" "OUT.xml" \
  --target-season 2025 --flag-year-only --rebuild-careers \
  --rebuild-real-history --drop-retired-adaptations --names --report "OUT.md"
```

Aggregating the backlog: parse each report's `## Players to check` table and
split the reason cell on `;`; the refusal groups come from `### Left untouched`
(Bulgaria writes its bucket line without a trailing colon — allow for that).

Do not start repairs on the remaining categories without the user's decision.
