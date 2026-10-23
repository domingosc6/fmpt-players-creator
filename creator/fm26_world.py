"""Each FM26 city's nation, so a city of birth is matched in the country he
was born in (Luanda is the Angolan one, not the Kenyan town; Brazil's cities
are named "Rio de Janeiro (RJ)").

client_db.dat, read with `fm_db_world.sections` (Python 3.14, zstd):
  table 2    cities, 43-byte rows from offset 12: lat f32 @3, lon f32 @7,
             nation INDEX u16 @12, DBID @36 (Porto, Lisboa, Viseu: 162)
  table 11   nations, rows [index][DBID][DBID] (162 -> 788 Portugal,
             189 -> 1651 Brazil, 30 -> 35 Mozambique)
Found 2026-10-08. `refresh()` decodes once into cache/fm26_city_nation.json.
"""
import json
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "fm26_city_nation.json")
DB_DIR = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/Football Manager 26 Editor"
    "/shared/data/database/db/2620/2620_fm")
CITY_TABLE, NATION_TABLE, ROW, START = 2, 11, 43, 12


def _build():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
    sys.path.insert(0, HERE)
    import fm_db_world
    from fm26_leagues import index_map
    secs = fm_db_world.sections(os.path.join(DB_DIR, "client_db.dat"))
    nations = index_map(secs[NATION_TABLE])
    s = secs[CITY_TABLE]
    count = struct.unpack_from("<I", s, 8)[0]
    out = {}
    for i in range(count):
        o = START + ROW * i
        nation_i = struct.unpack_from("<H", s, o + 12)[0]
        dbid = struct.unpack_from("<I", s, o + 36)[0]
        if nation_i in nations:
            out[str(dbid)] = nations[nation_i]
    json.dump(out, open(CACHE, "w"))


def refresh():
    subprocess.run(["/opt/homebrew/bin/python3", os.path.abspath(__file__), "--build"], check=True)


_DATA = None


def city_nation(dbid):
    """The nation DBID of an FM26 city, or None."""
    global _DATA
    if _DATA is None:
        if not os.path.exists(CACHE):
            refresh()
        _DATA = json.load(open(CACHE))
    return _DATA.get(str(dbid))


if __name__ == "__main__" and "--build" in sys.argv:
    _build()
