"""FM26's team league history (the editor's History > Team League History):
which competition a club played in, season by season. The creator takes a
row's division from here, so it names the competition of THAT era (Portuguese
Second Division - Central in 1983) instead of mapping a level to today's.

server_db.dat and client_db.dat are one zstd stream per table, laid end to end
(`fm_db_world.sections`). Three tables are used, found 2026-10-08 on Academico
de Viseu (FM26 2620):

  server table 75   league history, 40-byte rows from offset 14:
                    0 u32 competition index   4 u32 team index   8 i32 -1
                    12 u16 year  14 u8 position  15 u8 played  16-18 u8 W/D/L
                    19 u16 goals for  21 u16 against  23 u16 points
                    25 u8 order  26 u8 max teams
  server table 28   teams, client table 5 competitions: each row carries
                    [its own index u32][DBID u32][DBID u32], in index order

Decoding needs Python 3.14 (zstd); `refresh()` runs it once and caches a json
the 3.9 creator reads.
"""
import json
import os
import struct
import subprocess
import sys

import fm26_install

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "fm26_league_history.json")
DB_DIR = fm26_install.db_dir()
HISTORY, TEAMS, COMPS = ("server", 75), ("server", 28), ("client", 5)


def index_map(s):
    """{index: DBID} for a table whose rows carry [index][DBID][DBID] in order."""
    count = struct.unpack_from("<I", s, 8)[0]
    out, pos = {}, 12
    for i in range(count):
        key = struct.pack("<I", i)
        p = s.find(key, pos)
        while p >= 0 and s[p + 4:p + 8] != s[p + 8:p + 12]:
            p = s.find(key, p + 1)
        if p < 0:
            break
        out[i] = struct.unpack_from("<I", s, p + 4)[0]
        pos = p + 12
    return out


def _build():
    """Python 3.14 only: decode the three tables, write the cache."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
    import fm_db_world
    secs = {name: fm_db_world.sections(os.path.join(DB_DIR, name + "_db.dat"))
            for name in ("server", "client")}
    teams = index_map(secs[TEAMS[0]][TEAMS[1]])
    comps = index_map(secs[COMPS[0]][COMPS[1]])
    s = secs[HISTORY[0]][HISTORY[1]]
    hist = {}
    for off in range(14, len(s) - 39, 40):
        comp_i, team_i = struct.unpack_from("<II", s, off)
        year = struct.unpack_from("<H", s, off + 12)[0]
        team, comp = teams.get(team_i), comps.get(comp_i)
        if team is None or comp is None:
            continue
        hist.setdefault(str(team), []).append([year, comp, s[off + 25]])
    json.dump({"teams": len(teams), "comps": len(comps), "history": hist},
              open(CACHE, "w"))


def refresh():
    subprocess.run(fm26_install.zstd_python() + [os.path.abspath(__file__), "--build"], check=True)


_DATA = None


def division(club, season, calendar_year=False):
    """(competition DBID, note) for `club` in the season starting in `season`;
    (None, why) when FM26 has no row. A European season is filed under the
    year it ENDS (Viseu's 1978/79 Premier League row reads 1979; checked on
    ~5,000 player rows, 2026-10-08), a calendar-year nation's under its own
    year. Two rows in one season (a split or re-grouped league) take the one
    with the lowest order and say so."""
    global _DATA
    if _DATA is None:
        if not os.path.exists(CACHE):
            refresh()
        _DATA = json.load(open(CACHE))["history"]
    year = season if calendar_year else season + 1
    rows = [r for r in _DATA.get(str(club), []) if r[0] == year]
    if not rows:
        return None, "no league history row for club %s in %d" % (club, year)
    rows.sort(key=lambda r: r[2])
    note = None if len(rows) == 1 else "club %s has %d league rows in %d, took order %d" % (
        club, len(rows), year, rows[0][2])
    return rows[0][1], note


if __name__ == "__main__" and "--build" in sys.argv:
    _build()
