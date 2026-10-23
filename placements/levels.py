"""For each club in the careers: its two highest league levels over FM26's whole
league history (user rule: only games in the top two divisions a club has ever
played count). A level is a competition name with any group suffix removed
("Portuguese Second Division - South" -> "Portuguese Second Division"),
ranked by the best reputation among its competitions."""
import json, os, re, sys
sys.path.insert(0, os.path.expanduser("~/Documents/FMPT-Legends/creator")); sys.path.insert(0, os.path.expanduser("~/Documents/FMPT-Legends/scripts"))
import build, fm26_leagues
fm26_leagues.division(0, 2000)                    # loads _DATA
H = fm26_leagues._DATA
P = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "profiles.json"))
comps = {int(k): v for k, v in json.load(open("comps.json")).items()}
clubs = {r["club"] for p in P for r in p["career"] if r["club"]}
need = {row[1] for c in clubs for row in H.get(str(c), [])} - set(comps)
for c in need:
    h = build.search("type_id:=competition && fm_id:=%d" % c, by="name", q="*", n=1)
    d = h[0]["document"] if h else {}
    comps[c] = {"name": d.get("name"), "rep": d.get("reputation"), "nation": (d.get("nation") or {}).get("name"),
                "kind": d.get("classification_id")}
json.dump({str(k): v for k, v in comps.items()}, open("comps.json", "w"), ensure_ascii=False, indent=1)

def level(cid):
    n = (comps.get(cid) or {}).get("name") or str(cid)
    n = re.sub(r"\s*[-–]\s*(Group|Grupo|Série|Serie|Zone|Zona|North|South|East|West|Central|Norte|Sul|Centro)\b.*$", "", n, flags=re.I)
    n = re.sub(r"\s+(Group|Grupo|Gr\.?)\s*\w+$", "", n, flags=re.I)      # "Third Division Group 7"
    n = re.sub(r"(Division B)\d$", r"\1", n)                             # "Second Division B1"
    return re.sub(r"\s+[A-Z]$", "", n) if re.search(r"First Division [A-Z]$", n) else n

top2 = {}
for c in clubs:
    lv = {}
    for year, comp, order in H.get(str(c), []):
        l = level(comp)
        lv[l] = max(lv.get(l, -1), (comps.get(comp) or {}).get("rep") or 0)
    ranked = sorted(lv, key=lambda l: -lv[l])
    top2[c] = ranked[:2]
for p in P:
    for r in p["career"]:
        r["divi_level"] = level(r["divi"]) if r["divi"] else None
        r["counts"] = bool(r["club"] and r["divi"] and r["divi_level"] in top2.get(r["club"], []))
    p["club_top2"] = {str(c): top2[c] for c in {r["club"] for r in p["career"] if r["club"]}}
json.dump(P, open(sys.argv[1] if len(sys.argv) > 1 else "profiles.json", "w"), ensure_ascii=False, indent=1)
print("clubs", len(clubs), "extra comps", len(need))
