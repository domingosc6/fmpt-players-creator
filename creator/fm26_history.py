"""FM26's own playing history, read from the release database.

Three files in `2620_fm/`, each a short `tad` header and a zstd stream:
  pl_hist_index.dat  u32 count, then (person DBID, slot) pairs
  pl_hist_id.dat     two u32 per slot: offset of the first and the last row
  pl_hist_dt.dat     44-byte rows, each ending in the offset of the next
                     (0xFFFFFFFF on the last)

Row layout, checked against the editor on Gattuso and Maldini (2026-10-08):
  0  u16 year           2  u16 year the row ends in (not written)
  4  u8  flags          bit 0 loan, bit 1 youth, bit 2 tribunal (0x40 always set)
  5  u8  apps           6  u8 goals          255 = blank
  7  i32 fee            raw, the unit a changeset writes; -1 = none
  11 u32 club  x2       15 u32 division x2   FM26 DBIDs
  27 u8  order          the editor's Order column (0-8, not only 0/1/2)
  28 (u16 day of year, u16 year) x3: join, leave, unused; year 1900 = empty
Each file is decompressed once into cache/ (`fm26_install.decompress`).
"""
import datetime
import os
import struct

import fm26_install

HERE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = fm26_install.db_dir()
NONE = 0xFFFFFFFF          # an empty club or division cell
HEADER = {"pl_hist_dt": 8, "pl_hist_id": 8, "pl_hist_index": 12}


def _load(name):
    path = os.path.join(HERE, "cache", "fm26_%s.bin" % name)
    if not os.path.exists(path):
        raw = open(os.path.join(DB_DIR, name + ".dat"), "rb").read()[HEADER[name]:]
        open(path, "wb").write(fm26_install.decompress(raw))
    return open(path, "rb").read()


def _date(doy, year):
    if year == 1900:
        return None
    d = datetime.date(year, 1, 1) + datetime.timedelta(days=doy - 1)
    return (d.day, d.month, d.year)


class History:
    def __init__(self):
        idx = _load("pl_hist_index")
        n = struct.unpack_from("<I", idx, 0)[0]
        pairs = struct.unpack_from("<%dI" % (2 * n), idx, 4)
        self.slot = dict(zip(pairs[0::2], pairs[1::2]))
        ids = _load("pl_hist_id")
        self.offs = struct.unpack("<%dI" % (len(ids) // 4), ids)
        self.dt = _load("pl_hist_dt")

    def rows(self, dbid):
        """The person's rows in database order, or [] when FM26 has none."""
        s = self.slot.get(dbid)
        if s is None:
            return []
        out, o = [], self.offs[2 * s]
        while True:
            r = self.dt[o:o + 44]
            year, flags, apps, goals = struct.unpack_from("<HxxBBB", r, 0)
            fee = struct.unpack_from("<i", r, 7)[0]
            club = struct.unpack_from("<I", r, 11)[0]
            divi = struct.unpack_from("<I", r, 19)[0]
            dates = struct.unpack_from("<HHHH", r, 28)
            out.append({
                "year": year, "yror": r[27],
                "club": None if club == NONE else club, "divi": None if divi == NONE else divi,
                "apps": None if apps == 255 else apps,
                "gols": None if goals == 255 else goals,
                "onln": bool(flags & 1), "ytht": bool(flags & 2), "trib": bool(flags & 4),
                "cash": None if fee == -1 else fee,
                "join": _date(dates[0], dates[1]), "leaving": _date(dates[2], dates[3]),
            })
            nxt = struct.unpack_from("<I", r, 40)[0]
            if nxt == 0xFFFFFFFF:
                return out
            o = nxt
