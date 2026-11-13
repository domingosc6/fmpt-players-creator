"""Index every person the FM27 converted files change: which file, which record,
who he is and which club the file puts him at, plus his type in FM26 and FM27.

One row per (file, record id), written to legends/players_index.csv at the
repository root (tracked: Part 2 of the FM27 work - which file's changes win for
a player edited in several - reads it, and so will later editions).

    py scripts/legends_index.py "C:/DBC/FMPT/FM 27 converted files"

Columns
  file        country, as in "FMPT Legends - <country> - target2026.xml"
  uid         the record id the changes target
  dbid        the FM database id when the record is a real one (uid = DBID * 4294967297)
  kind        created (an ADDR row in the file), real, or session (an id an editor
              session invented; neither registered here nor a database person)
  role        player or staff (staff = created as a non-player, or carries non-player
              attributes and is never made a player)
  legend      yes when the record is a legend rather than a squad clean-up: created,
              has a playing history in the file, or is made a player by it
  name        the file's own name changes, else the FM name index (real records)
  club / club_name  the club the file sets (Pcti), else his open club spell; empty
              when the file leaves the club to the database
  changes     how many changes the file makes to the record
  fm26 / fm27 the person's type in each release database: 1 non-player, 2 player,
              3 player and non-player; empty when the database does not have him
"""
import csv
import glob
import os
import re
import sys
from collections import Counter, defaultdict
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "creator"))
import convert_edition as c          # noqa: E402
import fm_db_people                  # noqa: E402
import fm_names                      # noqa: E402
import fm26_install                  # noqa: E402

S = 4294967297
OUT = os.path.join(ROOT, "legends", "players_index.csv")
COLS = ["file", "uid", "dbid", "kind", "role", "legend", "name", "club", "club_name",
        "changes", "fm26", "fm27"]


def people_types():
    """{edition: {dbid: person type}} from each release database's people_db."""
    out = {}
    for ed in (26, 27):
        db = fm_db_people.PeopleDB(fm26_install.db_dir(ed),
                                   cache=os.path.join(ROOT, "work", "fm%d_people.pkl" % ed))
        out[ed] = {d: db.people[s + 4] for d, (s, _) in db.prows.items()}
    return out


def dbid_of(uid):
    n = int(uid)
    return n // S if n and n % S == 0 else None


def records(path):
    """(record id -> its person changes in file order, created ids, staff ids, names)."""
    changes = ET.parse(path).getroot().find('list[@id="db_changes"]')
    created, recs = set(), defaultdict(list)
    for rec in changes:
        if c.rec_prop(rec) == "ADDR":
            for nv in rec.findall('record[@id="new_value"]'):
                u = nv.find('large[@id="db_unique_id"]')
                if u is not None:
                    created.add(u.get("value"))
        t = rec.find('integer[@id="database_table_type"]')
        if t is not None and t.get("value") == "1":
            recs[c.rec_uid(rec)].append(rec)
    return recs, created, c.detect_staff(changes), c.person_names(changes)


def club_in_file(rs):
    """The club the file puts him at: its last Pcti, else his open club spell."""
    pcti = None
    for r in rs:
        if c.rec_prop(r) == "Pcti":
            ref = c.club_of(r.find('*[@id="new_value"]'))
            pcti = ref[1] if ref else None
    if pcti:
        return pcti
    spells = c.replay_spells([r for r in rs if c.rec_prop(r) == "Pnph"])
    open_sp = next((sp for sp in reversed(spells) if sp["left"] is None), None)
    return open_sp["team"][1] if open_sp and open_sp.get("team") else None


def makes_player(rs):
    return any(c.rec_prop(r) == "Ptyp" and r.find('*[@id="new_value"]') is not None
               and r.find('*[@id="new_value"]').get("value") == "2" for r in rs)


def index_file(path, types, namer):
    country = re.sub(r"^FMPT Legends - (.*) - target\d+.*$", r"\1", os.path.basename(path)[:-4])
    recs, created, staff, names = records(path)
    namer.fetch([("person", d) for d in (dbid_of(u) for u in recs) if d])
    rows = []
    for uid, rs in recs.items():
        d = dbid_of(uid)
        kind = "created" if uid in created else ("real" if d else "session")
        props = {c.rec_prop(r) for r in rs}
        club = club_in_file(rs)
        rows.append({
            "file": country, "uid": uid, "dbid": d or "", "kind": kind,
            "role": "staff" if uid in staff else "player",
            "legend": "yes" if (kind == "created" or "Plhs" in props or makes_player(rs)) else "",
            "name": names.get(uid) or (namer.person(uid) if d else "") or "",
            "club": club or "", "club_name": "",
            "changes": len(rs),
            "fm26": types[26].get(d, "") if d else "", "fm27": types[27].get(d, "") if d else "",
        })
    namer.fetch([("team", int(r["club"])) for r in rows if str(r["club"]).isdigit()])
    for r in rows:
        if r["club"]:
            r["club_name"] = namer.club(r["club"]) or ""
    return rows


def main(argv=None):
    folder = (argv or sys.argv[1:] or [r"C:\DBC\FMPT\FM 27 converted files"])[0]
    files = sorted(glob.glob(os.path.join(folder, "FMPT Legends - * - target2026.xml")))
    if not files:
        raise SystemExit("no 'FMPT Legends - * - target2026.xml' in %s" % folder)
    types = people_types()
    namer = fm_names.Names()
    rows = []
    for f in files:
        got = index_file(f, types, namer)
        rows += got
        print("%-55s %6d records, %5d legends" % (os.path.basename(f), len(got),
                                                  sum(1 for r in got if r["legend"])))
    namer.save()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["file"], r["name"].lower(), r["uid"])))
    print("%d rows -> %s" % (len(rows), OUT))
    print(Counter((r["kind"], r["role"]) for r in rows if r["legend"]))


if __name__ == "__main__":
    main()
