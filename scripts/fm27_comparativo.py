"""The Comparativo statuses for one country, as a lookup table the sheet matches.

    py scripts/fm27_comparativo.py Portugal

Reads legends/fm27_status.csv and the fixed FM27 file, writes
work/comparativo_<country>.json:
  rows    [key, fm27, youth, ot] per name a legend can go by in the sheet - key is
          "<lower-case name>|<Editor File>"; fm27 the status word (green, orange,
          yellow, red, blue, purple, pink) plus a short note when it is not plain
          green; youth 1 for a player born 2008 or later (under 19 at the end of
          2026 - the sheet's Youth tag wins where it has one); ot his other
          nationalities, "OT: A/B"
  people  one entry per legend, for appending the ones the sheet does not have

How the sheet takes it (user, 2026-11-14): column L "FM27" holds the status, and
seven conditional-format rules colour the row from it; Obs. (K) gets Youth and
OT: where it does not say so already. The matching is done by sheet formulas in a
temporary tab, so no name is ever copied by hand.

Other nationalities: a real record's from FM26's database (the list after the
birth city, CLAUDE.md 5h), a created one's from the file's own P2ni/PNRs changes.
"""
import csv
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "creator"))
import convert_edition as c      # noqa: E402
import fm_names                  # noqa: E402
import fm27_fix as F             # noqa: E402

S = 4294967297
OUT_DIR = r"C:\DBC\FMPT\FM 27 converted files"
NOTE_MAX = 60


def short(obs):
    """The note a non-green row carries: the reasons, not the bookkeeping."""
    keep = [p.strip() for p in obs.split(";") if p.strip() and not p.strip().startswith(
        ("from FM26", "from FM24", "recreated as new player", "reputations from", "PA ",
         # fixes already made, not work left
         "his move opened", "contract joined", "history:", "history from FM24", "career and birth date",
         "club set to", "born ", "already recreated", "not in the squad sheet"))]
    s = "; ".join(LABELS.get(p, p) for p in keep)
    for long_, label in PREFIXES:
        s = s.replace(long_, label)
    return s if len(s) <= NOTE_MAX else s[:NOTE_MAX - 3] + "..."


# the notes most rows share, in a few words (the full text is in fm27_status.csv)
LABELS = {
    "hair colour, hair length and preferred moves not copied yet": "hair + preferred moves by hand",
    "created career never rebuilt by the converter - edit by hand": "career by hand",
    "body type not copied yet": "body type by hand",
    "no attributes in the file or in FM26": "no attributes",
}
PREFIXES = [("profile from ", "profile "), (" - redo by hand", " by hand"),
            ("staff in FM27: made a player first, retirements cleared", "was staff in FM27"),
            ("career reads season", "career ends"),
            ("check age: seasons typed in ", "check age (seasons "), (" after the birth date (", ", birth date "), ("playing history could not be rebuilt - check it", "history to check")]


def other_nations(ed26, d):
    """FM26's other nationalities of a real record: a count at dob+37, then
    16-byte entries with the nation DBID at +43 (Danilo Pereira, Gelson, Nani,
    Deco, Pepe)."""
    if d not in ed26.db.prows:
        return []
    s, e = ed26.db.prows[d]
    r = ed26.db.people[s:e]
    i = F.dob_pos(r)
    if i < 0 or i + 47 > len(r):
        return []
    n = r[i + 37]
    if not 1 <= n <= 4:
        return []
    out = []
    for k in range(n):
        q = i + 43 + 16 * k
        if q + 4 <= len(r):
            v = struct.unpack_from("<I", r, q)[0]
            if 0 < v < 100000:
                out.append(v)
    primary = struct.unpack_from("<I", r, i + 17)[0]
    return [v for v in out if v != primary]


def file_nations(rs):
    out = []
    for r in rs:
        if c.rec_prop(r) in ("P2ni", "PNRs"):
            for el in r.iter():
                if el.get("id") == "Nnat":
                    v = int(el.get("value"))
                    out.append(v // S if v > 10 ** 8 else v)
    return out


def main(country):
    namer = fm_names.Names()
    ed26 = F.Edition(26)
    path = os.path.join(OUT_DIR, "FMPT Legends - %s - target2026.xml" % country)
    tree, changes, created, recs, staff, names = F.scan(path)
    status = [r for r in csv.DictReader(open(os.path.join(ROOT, "legends", "fm27_status.csv"),
                                             encoding="utf-8")) if r["file"] == country]
    rows, people, seen = [], [], set()
    for st in status:
        uid, d = st["uid"], int(st["dbid"]) if st["dbid"] else None
        rs = recs.get(uid, []) + (recs.get(str(d * S), []) if d else [])
        fm27 = st["status"]
        note = short(st["obs"])
        age = "check age" in st["obs"]
        if fm27 != "green" and note:
            fm27 += ": " + note
        elif age:
            p = next(p.strip() for p in st["obs"].split(";") if "check age" in p)
            fm27 += ": check age (seasons %s, birth date %s)" % (p.split("typed in ")[1].split(" ")[0],
                                                                p.split("(")[-1].rstrip(")"))
        born = F.last_dob(rs)
        youth = 1 if born and born[2] >= 2008 and st["role"] == "player" else 0
        nats = other_nations(ed26, d) if d else []
        nats += [n for n in file_nations(rs) if n not in nats]
        if nats:
            namer.fetch([("nation", n) for n in nats])
        # only what the index knows as a nation: for some records those bytes hold
        # club or competition ids (1487, 60), not nationalities
        ot = "/".join(dict.fromkeys(namer.get("nation", n) for n in nats if namer.get("nation", n)))
        ot = "OT: " + ot if ot else ""
        cands = {st["name"]}
        for r in rs:
            if c.rec_prop(r) in ("Pcna", "Pfln"):
                nv = r.find('*[@id="new_value"]')
                if nv is not None and nv.get("value"):
                    cands.add(nv.get("value"))
        for nm in cands:
            key = "%s|%s" % (" ".join(nm.lower().split()), country)
            if key not in seen:
                seen.add(key)
                rows.append([key, fm27, youth, ot])
        people.append({"uid": uid, "name": st["name"], "keys": sorted(
            "%s|%s" % (" ".join(n.lower().split()), country) for n in cands),
            "role": st["role"], "fm27": fm27, "youth": youth, "ot": ot,
            "ca": F.last_int(rs, "PCAB"), "pa": F.last_int(rs, "PPAB")})
    # a key two legends share would colour both rows the same: left out
    dup = {k for k in seen if sum(1 for p in people if k in p["keys"]) > 1}
    rows = [r for r in rows if r[0] not in dup]
    out = os.path.join(ROOT, "work", "comparativo_%s.json" % country.lower())
    namer.save()
    json.dump({"rows": rows, "people": people, "shared_keys": sorted(dup)},
              open(out, "w", encoding="utf-8"), ensure_ascii=False)
    # the same table as tab-separated chunks, for the sheet's paste
    for i in range(0, len(rows), 700):
        with open(os.path.join(ROOT, "work", "comparativo_%s_%d.tsv" % (country.lower(), i // 700)),
                  "w", encoding="utf-8", newline="\n") as fh:
            for r in rows[i:i + 700]:
                fh.write("\t".join(str(x) for x in r) + "\n")
    print("%s: %d legends, %d keys (%d shared, left out) -> %s" % (
        country, len(people), len(rows), len(dup), out))


if __name__ == "__main__":
    main(sys.argv[1])
