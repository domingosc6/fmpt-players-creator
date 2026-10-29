"""Club editor fields for the Comparativo sheet's Teams tab, read from FM26's
own database: stadium, capacity, morale, training, the four youth ratings,
balance, transfer budget and wages.

    python3.14 comparativo/club_fields.py OUT.json

OUT.json maps "Team|Country" (the sheet's columns A and B) to the fields.
Which FM club a row is comes from fm_ids.json next to this script (DBIDs,
matched by hand against fmref in 2026-10). Reputation is NOT here: it was
taken from the fmref index (`scripts/fm_names.py` endpoint, field
`reputation`). Writing the sheet is done separately, and never over a cell
the user already filled.

Layouts found 2026-10-29 on FM26 (2620) by comparing editor exports
(`odvl` = the database's value) for Argentinos, Liverpool, Borac Banja Luka,
Motherwell, Rudar Prijedor and Al-Shabab. CHECK THEM AGAIN for a new edition
with a fresh probe export; pick clubs with unusual values (1-5, 20).

  server 3    clubs, key [idx][DBID][DBID] at the row END. Balance = i64
              8 bytes before the first run of three null dates (01 00 6c 07).
  server 4    club extras. Two 6-byte blocks per club, the first at
              P[2*idx]: youth importance 14 bytes before it; youth
              facilities/coaching/recruitment after `01 00 6c 07 00x8`
              (TAIL); training + morale right after the club's own idx u32,
              98 or 117 bytes before the block (HEAD).
              Corporate facilities was NOT found.
  server 22   stadiums, 181-byte rows from 12: +2 capacity, R-7 DBID.
  server 28   teams, key at END; +17 home stadium index.
  server 39   finance, 79-byte rows from 12: +13 team idx, +23 transfer
              budget, +28 weekly wages.
  2600 lang_db  stadium names: [DBID][len][name][len][alt]ff ff 00.

Money is stored in the database's own unit; F converts it to euros (from
Argentinos' balance), wages are written per month.
"""
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "creator"))
import fm26_install  # noqa: E402
import fm_db_world  # noqa: E402
from fm26_leagues import index_map  # noqa: E402

F = 3854746 / 3331298
NULL_DATES = b"\x01\x00\x6c\x07" * 3
BLOCK = re.compile(rb"\xff{8}([\x01-\x14]{6})\x00{6}")
TAIL = re.compile(rb"\x01\x00\x6c\x07\x00{8}(.)(.)(.)\xfe\xff{5}", re.S)
STADIUM_ROW, FINANCE_ROW = 181, 79


def rows_by_dbid(s, idx2db):
    """{DBID: row bytes} for a table whose rows END with [idx][DBID][DBID]."""
    out, pos = {}, 12
    for i in range(len(idx2db)):
        db = idx2db[i]
        k = s.find(struct.pack("<III", i, db, db), pos)
        if k < 0:
            break
        out[db] = s[pos:k]
        pos = k + 12
    return out


def stadium_names():
    base = os.path.dirname(os.path.dirname(fm26_install.db_dir()))
    buf = b"".join(fm_db_world.sections(
        os.path.join(base, "2600", "2600_fm", "lang_db.dat")))

    def row(p):
        if p < 0 or p + 12 > len(buf):
            return None
        d, n = struct.unpack_from("<II", buf, p)
        if not 0 < n <= 150:
            return None
        q = p + 8 + n
        if q + 4 > len(buf):
            return None
        n2 = struct.unpack_from("<I", buf, q)[0]
        if n2 > 150 or buf[q + 4 + n2:q + 7 + n2] != b"\xff\xff\x00":
            return None
        try:
            return d, buf[p + 8:q].decode("utf-8"), q + 7 + n2
        except UnicodeDecodeError:
            return None

    start = buf.find(b"Anfield") - 8      # any row of the table, then walk back
    while True:
        back = next((b for b in range(15, 320)
                     if (r := row(start - b)) and r[2] == start), None)
        if back is None:
            break
        start -= back
    out, p = {}, start
    while r := row(p):
        out[r[0]] = r[1]
        p = r[2]
    return out


def main(out_path):
    secs = fm_db_world.sections(os.path.join(fm26_install.db_dir(), "server_db.dat"))
    s3, s4, s22, s28, s39 = (secs[i] for i in (3, 4, 22, 28, 39))
    clubs = index_map(s3)
    db2club = {d: i for i, d in clubs.items()}
    club_rows = rows_by_dbid(s3, clubs)
    teams = index_map(s28)
    team_rows = rows_by_dbid(s28, teams)
    names = stadium_names()
    blocks = [m.start(1) for m in BLOCK.finditer(s4)]

    finance = {}
    for i in range(struct.unpack_from("<I", s39, 8)[0]):
        r = s39[80 + FINANCE_ROW * i:80 + FINANCE_ROW * (i + 1)]
        if len(r) < FINANCE_ROW:
            break
        db = teams.get(struct.unpack_from("<I", r, 13)[0])
        if db is not None:
            finance.setdefault(db, (struct.unpack_from("<i", r, 23)[0],
                                    struct.unpack_from("<i", r, 28)[0]))

    def stadium(db):
        r = team_rows.get(db)
        if not r or len(r) <= 21:
            return None, None
        i = struct.unpack_from("<I", r, 17)[0]
        if not 0 <= i < struct.unpack_from("<I", s22, 8)[0]:
            return None, None
        row = s22[12 + STADIUM_ROW * i:12 + STADIUM_ROW * (i + 1)]
        cap = struct.unpack_from("<I", row, 2)[0]
        return names.get(struct.unpack_from("<I", row, STADIUM_ROW - 7)[0]), cap or None

    def extras(db):
        ci = db2club.get(db)
        if ci is None or 2 * ci + 2 >= len(blocks):
            return {}
        a = blocks[2 * ci]
        out = {"youth_importance": s4[a - 14] if s4[a - 9] == 3 and s4[a - 12] == 255 else None}
        m = TAIL.search(s4, a, blocks[2 * ci + 2])
        if m:
            out["youth_facilities"], out["youth_coaching"], out["youth_recruitment"] = (
                g[0] for g in m.groups())
        for k, v in out.items():                # 0 and 255 = unset
            if v is not None and not 1 <= v <= 20:
                out[k] = None
        head = re.compile(re.escape(struct.pack("<I", ci))
                          + rb"([\x00-\x14])([\x00-\x14])\x00\x00\x00\x01")
        hits = list(head.finditer(s4, max(0, a - 600), a))
        if hits and hits[-1].group(1)[0]:     # training 0 = empty record
            out["training"], out["morale"] = hits[-1].group(1)[0], hits[-1].group(2)[0]
        return out

    def balance(db):
        seg = club_rows.get(db)
        k = seg.find(NULL_DATES) if seg else -1
        return round(struct.unpack_from("<q", seg, k - 8)[0] * F) if k >= 8 else None

    ids = json.load(open(os.path.join(HERE, "fm_ids.json"), encoding="utf-8"))
    result = {}
    for key, fid in ids.items():
        db = int(fid)
        name, cap = stadium(db)
        fin = finance.get(db)
        result[key] = {
            "fm_id": db, "stadium": name, "capacity": cap,
            **extras(db),
            "balance": balance(db),
            "transfer_budget": round(fin[0] * F) if fin else None,
            "wages_month": round(fin[1] * F * 52 / 12) if fin else None,
        }
    json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(result)} teams -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
