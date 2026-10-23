"""Each FM26 person's date of birth, read from the release database - only
used when no linked source gives one (user, 2026-10-10: a fix player listed
by id alone; Wikipedia, NFT and the rest still win when there is a link).

people_db.dat, one record per person (framing read by
scripts/fm_db_people.walk_people). The date sits right after the name block:

    00 fna:u32 00 sna:u32 00 cna:u32 00 len:u32 full_name[len] doy:u16 year:u16

first/second/common name ids (ffffffff = none), then the full name in UTF-8
(len 0 when there is none), then the date as day of year and year (1/1900 is
the null date). Checked 2026-10-10 against 17 people whose real date we hold:
16 equal, the 17th (Stinga) is a date FM26 itself holds differently. Found
for 95% of a 20,000-person sample.

`refresh()` decodes once into cache/fm26_people_dob.json (Python 3.14, zstd)
- carried with cache/ to a computer without the FM26 Editor.
"""
import datetime
import json
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "fm26_people_dob.json")
# every DBID people_db holds: playing history and the site index also name
# people FM26 no longer has (Kali 7002246, user 2026-10-22: "Record not found")
IDS_CACHE = os.path.join(HERE, "cache", "fm26_people_ids.json.gz")
DB_DIR = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/Football Manager 26 Editor"
    "/shared/data/database/db/2620/2620_fm")


def record_dob(rec):
    """(day, month, year) from one people_db record, or None."""
    for i in range(len(rec) - 24):
        if rec[i] or rec[i + 5] or rec[i + 10] or rec[i + 15]:
            continue
        n = struct.unpack_from("<I", rec, i + 16)[0]
        if n > 120 or i + 20 + n + 4 > len(rec):
            continue
        name = rec[i + 20:i + 20 + n]
        if n and min(name) < 32:
            continue
        try:
            name.decode("utf-8")
        except UnicodeDecodeError:
            continue
        doy, year = struct.unpack_from("<HH", rec, i + 20 + n)
        if 1850 <= year <= 2015 and year != 1900 and 1 <= doy <= 366:
            d = datetime.date(year, 1, 1) + datetime.timedelta(days=doy - 1)
            return (d.day, d.month, d.year)
    return None


def _build():
    """Python 3.14 only: decode people_db, write the cache."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
    import fm_db_people
    buf = fm_db_people.load(os.path.join(DB_DIR, "people_db.dat"))
    out = {}
    rows = fm_db_people.walk_people(buf)
    for dbid, (start, end) in rows.items():
        d = record_dob(buf[start:end])
        if d:
            out[str(dbid)] = d
    json.dump(out, open(CACHE, "w"))
    import gzip
    with gzip.open(IDS_CACHE, "wt") as fh:
        json.dump(sorted(rows), fh, separators=(",", ":"))


def refresh():
    subprocess.run(["/opt/homebrew/bin/python3", os.path.abspath(__file__), "--build"], check=True)


_DATA = None


def dob(dbid):
    """FM26's (day, month, year) of birth for a person, or None."""
    global _DATA
    if _DATA is None:
        if not os.path.exists(CACHE):
            refresh()
        _DATA = json.load(open(CACHE))
    d = _DATA.get(str(dbid))
    return tuple(d) if d else None


_IDS = None


def exists(dbid):
    """Whether FM26's people_db holds this DBID."""
    global _IDS
    if _IDS is None:
        import gzip
        if not os.path.exists(IDS_CACHE):
            refresh()
        with gzip.open(IDS_CACHE, "rt") as fh:
            _IDS = set(json.load(fh))
    return int(dbid) in _IDS


if __name__ == "__main__" and "--build" in sys.argv:
    _build()
