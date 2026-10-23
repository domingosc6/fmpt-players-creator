"""Names, nations and league reputations for every club and competition in the careers."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "creator")); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import fm_names, build
names = fm_names.Names()
P = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "profiles.json"))
want = [("person", p["dbid"]) for p in P]
for p in P:
    for r in p["career"]:
        if r["club"]: want.append(("team", r["club"]))
        if r["divi"]: want.append(("competition", r["divi"]))
names.fetch(want)
reps = {}
comps = {r["divi"] for p in P for r in p["career"] if r["divi"]}
for c in comps:
    h = build.search("type_id:=competition && fm_id:=%d" % c, by="name", q="*", n=1)
    d = h[0]["document"] if h else {}
    reps[c] = {"name": d.get("name"), "rep": d.get("reputation"), "nation": (d.get("nation") or {}).get("name"),
               "kind": d.get("classification_id")}
for p in P:
    p["nationality"] = names.person_nation(p["dbid"])
    for r in p["career"]:
        r["club_name"] = names.club(r["club"]) if r["club"] else None
        r["club_nation"] = names.nation(r["club"]) if r["club"] else None
        c = reps.get(r["divi"]) or {}
        r["divi_name"], r["divi_rep"] = c.get("name"), c.get("rep")
json.dump(P, open(sys.argv[1] if len(sys.argv) > 1 else "profiles.json", "w"), ensure_ascii=False, indent=1)
json.dump({str(k): v for k, v in reps.items()}, open("comps.json", "w"), ensure_ascii=False, indent=1)
print(len(comps), "competitions;", sum(1 for p in P for r in p["career"] if r["club"] and not r["club_name"]), "club rows unnamed")
