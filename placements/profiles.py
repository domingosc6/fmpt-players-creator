"""FM26 profile per sheet player: nation, DOB, club, position and career."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "creator"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import build, fm26_history, fm26_people, fm26_leagues
import xlsx_read as X

names = build._names()
hist = fm26_history.History()
out = []
SRC = sys.argv[1] if len(sys.argv) > 1 else None
OUT = sys.argv[2] if len(sys.argv) > 2 else "profiles.json"
src_rows = ([["", n, "", "", "", "", str(d), "", str(ca), str(pa)] for d, n, ca, pa in json.load(open(SRC))]
            if SRC else X.rows(X.read("xlsx/Players for script.xlsx")["Avulsos"])[1:])
for r in src_rows:
    if not r[1]:
        continue
    dbid = int(float(r[6]))
    hits = build.search("fm_id:=%d" % dbid, by="name", q="*", n=1)
    doc = hits[0]["document"] if hits else {}
    rows = []
    for h in hist.rows(dbid):
        rows.append({"year": h["year"], "club": h["club"], "club_name": names.get("club", h["club"]) if h["club"] else None,
                     "club_nation": names.nation(h["club"]) if h["club"] else None,
                     "divi": h["divi"], "divi_name": names.get("competition", h["divi"]) if h["divi"] else None,
                     "apps": h["apps"], "goals": h["gols"], "youth": h["ytht"], "loan": h["onln"]})
    out.append({"name": r[1], "dbid": dbid, "ca": r[8], "pa": r[9],
                "fm_name": doc.get("name"), "nation": (doc.get("nation") or {}).get("name"),
                "club_now": (doc.get("team") or {}).get("name"), "club_now_id": (doc.get("team") or {}).get("fm_id"),
                "classification": doc.get("classification_id"), "dob": fm26_people.dob(dbid),
                "career": rows})
json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
for p in out:
    print("%-20s %-10s %-12s dob=%s now=%s rows=%d" % (p["name"], p["dbid"], p["nation"], p["dob"], p["club_now"], len(p["career"])))
