#!/usr/bin/env python3
"""Builds "Legends Creator": everything create_legends.py needs, in one folder
that runs on any computer with Python 3.10+ (macOS or Windows).

    python3 creator/make_package.py ["<target folder>"]

Default target: FMPT-Legends/Legends Creator. The code is refreshed on every
run; ids.json and cache/ are copied only when the target has none - the
copies carried between computers are the ones that count, never overwritten
(a new FM26 extract the package's cache lacks is added).
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CREATOR = ["build.py", "create_legends.py", "fix.py", "fm26_history.py", "fm26_leagues.py",
           "fm26_people.py", "fm26_achievements.py",
           "fm26_world.py", "model.py", "verify.py", "make_package.py",
           "club_overrides.json", "division_overrides.json", "levels.json", "template.xml", "PLAN.md"]
SOURCES = ["__init__.py", "bdfutbol.py", "carrierecalciatori.py", "foradejogo.py", "nft.py", "wikipedia.py",
           "zerozero.py", "zerozero_extract.js", "bdfutbol_extract.js"]
BOOKMARKLETS = ["make.py", "bookmarklets.html", "zerozero.bookmarklet.txt",
                "bdfutbol.bookmarklet.txt"]
# what the creator imports from scripts/ (and fm_names' club-name index)
SCRIPTS = ["clean_import.py", "convert_edition.py", "fm_db_people.py", "fm_db_world.py",
           "fm_names.py", "merge_changesets.py", "name_rebuilt_records.py",
           "probe_editor_replay.py", "rebuild_lost_records.py", "repair_type_change.py",
           "fm_names_cache.json"]
CARRIED = ["ids.json"]                     # copied once, then the user's

README = """# Legends Creator

Builds FM26 editor changesets for legends: creates players FM26 lacks, fixes
the ones it has (Exists = Y or an FM26 id).

## Run

macOS:    python3 creator/create_legends.py "<sheet>.csv" --out-dir "creator/out/<team>" --import-downloads
Windows:  py creator\\create_legends.py "<sheet>.csv" --out-dir "creator\\out\\<team>" --import-downloads

Python 3.10 or newer (python.org). Run from this folder. Internet is needed
for national-football-teams, Wikipedia, carrierecalciatori and the FM club search.

## Sheet

Position, Name, Nation, Team[, Team Id], Season, Website[, alternate_website], Exists[, Id][, CA, PA, CR, HR, WR][, DOB]
- Season: first year of the prime season (1995 = 1995/96).
- Exists: Y/Yes, or the player's FM26 id, means fix; N means create.
- Team: a name (found once per sheet) or an FM26 id; or a Team Id column.
  RET retires the player (Exists must hold his FM26 id): no club, one
  retirement on 30/6/2024.
- Position: GK RB CB LB DM CM AM RW LW ST, or GR DD DC DE Mdef/MD MC MAC/MO ED EE PL.
- CA, PA, CR, HR, WR: current/potential ability, current/home/world
  reputation (0-200; PA may be negative). Written only when filled. A fix
  never touches position or nationality.
- DOB (30/10/1975): used by a fix when no linked source dates him and FM26's
  own date can't be read; otherwise his DOB is left unshifted.
- Website columns: national-football-teams, Wikipedia (any language),
  carrierecalciatori, zerozero, bdfutbol.

## zerozero and bdfutbol

Both sit behind Cloudflare. Open creator/bookmarklets/bookmarklets.html once
and drag the two buttons to the bookmarks bar. For each player, open his page
(zerozero.pt in Portuguese; bdfutbol in Spanish - the bookmark switches to
/es/ itself) and click the bookmark. --import-downloads moves the saved files
from Downloads into creator/cache/.

## Carry between computers

- creator/ids.json - the id of every created player. One copy only: a second
  one gives the same player a new id and FM shows him twice.
- creator/cache/ - FM26 database extracts (built on the Mac from the FM26
  Editor install) and every page already fetched.
- Output goes to the --out-dir you give: one merged "... - all.xml" per sheet,
  plus a .xml and .md report per player and a summary.

## Rules

creator/PLAN.md holds every rule the creator follows.
"""


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "Legends Creator")
    out = os.path.join(target, "creator")
    for f in CREATOR:
        copy(os.path.join(HERE, f), os.path.join(out, f))
    for f in SOURCES:
        src = os.path.join(HERE, "sources", f)
        if os.path.exists(src):
            copy(src, os.path.join(out, "sources", f))
    for f in BOOKMARKLETS:
        copy(os.path.join(HERE, "bookmarklets", f), os.path.join(out, "bookmarklets", f))
    for f in SCRIPTS:
        copy(os.path.join(ROOT, "scripts", f), os.path.join(target, "scripts", f))
    for f in CARRIED:
        if not os.path.exists(os.path.join(out, f)):
            copy(os.path.join(HERE, f), os.path.join(out, f))
            print("copied", f)
        else:
            print("kept the package's own", f)
    cache = os.path.join(out, "cache")
    if not os.path.exists(cache):
        shutil.copytree(os.path.join(HERE, "cache"), cache,
                        ignore=shutil.ignore_patterns(".DS_Store"))
        print("copied cache/")
    else:
        # the package's cache is kept; a file it lacks (a new FM26 extract) is added
        added = [f for f in os.listdir(os.path.join(HERE, "cache"))
                 if f.startswith("fm26_") and not os.path.exists(os.path.join(cache, f))]
        for f in added:
            shutil.copy2(os.path.join(HERE, "cache", f), os.path.join(cache, f))
        print("kept the package's own cache/" + (", added %s" % ", ".join(added) if added else ""))
    os.makedirs(os.path.join(out, "out"), exist_ok=True)
    open(os.path.join(target, "README.md"), "w", encoding="utf-8").write(README)
    print("wrote", target)


if __name__ == "__main__":
    main()
