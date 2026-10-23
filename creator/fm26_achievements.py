"""Every FM26 person's achievements (the editor's PACL grid: trophies won,
places, promotions), read from the release database - used to drop the ones
from before a fixed player's chosen season (user, 2026-10-22).

server_db.dat (a `tad` header and zstd frames) holds one table of 36-byte
records, introduced by `tad.` + 2 bytes + the row count (u32). Found
2026-10-22 against achievement rows the Legends changesets carry as `olvl`
(Lazio's Serie A and Coppa Italia 2000, Cup Winners' Cup 1999):

    doy:u16 year:u16 person:u32 team:u32 competition:u32 other_team:u32
    plac:u8 ajob:u8 prom:u8 row_id:u32 ?:u32 ?:u32 wgps:u8

doy/year is the date (doy 0: no date, the year alone); 0xffffffff is a null
reference. row_id runs 0..count-1. The year is the season's END year (1999/00
is 2000).

`refresh()` decodes once into cache/fm26_achievements.json.gz (Python 3.14,
zstd) - carried with cache/ to a computer without the FM26 Editor.
"""
import datetime
import gzip
import json
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "fm26_achievements.json.gz")
DB_DIR = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/Football Manager 26 Editor"
    "/shared/data/database/db/2620/2620_fm")
NIL = 0xFFFFFFFF
REC = 36
MAGIC = bytes.fromhex("28b52ffd")


def _load(path):
    from compression import zstd
    raw = open(path, "rb").read()
    out, pos = [], raw.find(MAGIC)
    while pos >= 0:
        d = zstd.ZstdDecompressor()
        out.append(d.decompress(raw[pos:]))
        pos = raw.find(MAGIC, len(raw) - len(d.unused_data))
    return b"".join(out)


def _table(buf):
    """(start, count) of the achievements table: the `tad.` header whose
    count is followed by that many records with row ids 0, 1, 2..."""
    i = buf.find(b"tad.")
    while i >= 0:
        count = struct.unpack_from("<I", buf, i + 6)[0]
        start = i + 12
        if 1000 < count and start + count * REC <= len(buf):
            rid = lambda k: struct.unpack_from("<I", buf, start + k * REC + 23)[0]
            if rid(0) == 0 and rid(1) == 1 and rid(count - 1) == count - 1:
                return start, count
        i = buf.find(b"tad.", i + 4)
    raise ValueError("achievements table not found in server_db")


def _build():
    buf = _load(os.path.join(DB_DIR, "server_db.dat"))
    start, count = _table(buf)
    out = {}
    for k in range(count):
        doy, year, person, team, comp, otea, plac, ajob, prom = struct.unpack_from(
            "<HHIIIIBBB", buf, start + k * REC)
        wgps = buf[start + k * REC + 35]
        row = [doy, year, None if team == NIL else team, None if comp == NIL else comp,
               None if otea == NIL else otea, plac, ajob, prom, wgps]
        out.setdefault(str(person), []).append(row)
    with gzip.open(CACHE, "wt", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))


def refresh():
    subprocess.run(["/opt/homebrew/bin/python3", os.path.abspath(__file__), "--build"], check=True)


_DATA = None


def rows(dbid):
    """The person's achievements: dicts with date (d, m, y) or None, year,
    team, competition, other_team, plac, ajob, prom, wgps."""
    global _DATA
    if _DATA is None:
        if not os.path.exists(CACHE):
            refresh()
        with gzip.open(CACHE, "rt", encoding="utf-8") as fh:
            _DATA = json.load(fh)
    out = []
    for doy, year, team, comp, otea, plac, ajob, prom, wgps in _DATA.get(str(dbid), []):
        date = None
        if doy:
            d = datetime.date(year, 1, 1) + datetime.timedelta(days=doy - 1)
            date = (d.day, d.month, d.year)
        out.append({"date": date, "year": year, "team": team, "competition": comp,
                    "other_team": otea, "plac": plac, "ajob": ajob, "prom": bool(prom),
                    "wgps": bool(wgps)})
    return out


def season_of(row, calendar=False):
    """The start year of the season the achievement belongs to. A club in a
    calendar-year league (`calendar`): the year itself. Otherwise a date from
    July on opens a season, before July closes the previous one, and a bare
    year is the season's end year."""
    if calendar:
        return row["date"][2] if row["date"] else row["year"]
    if row["date"]:
        d, m, y = row["date"]
        return y if m >= 7 else y - 1
    return row["year"] - 1


if __name__ == "__main__" and "--build" in sys.argv:
    _build()
