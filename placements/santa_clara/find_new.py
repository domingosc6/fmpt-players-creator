import json, os, sys, collections
sys.path.insert(0, os.path.expanduser("~/Documents/FMPT-Legends/creator"))
sys.path.insert(0, os.path.expanduser("~/Documents/FMPT-Legends/scripts"))
import build, fm26_history, fm26_people
names = build._names(); hist = fm26_history.History()
NEW = [("GR","Marco Pereira","Portugal"),("GR","Serginho","Portugal"),("DC","Kali","Angola"),("DC","Mikel Villanueva","Venezuela"),
       ("DD","Portela","Portugal"),("DD","Rafael Ramos","Portugal"),("DE","Mansur","Brazil"),("Mdef","Paiva","Portugal"),
       ("MAC","Ricardinho","Portugal"),("ED","George","Brazil"),("PL","Clemente","Portugal"),("PL","Carlos Junior","Brazil"),
       ("PL","Thiago Santana","Brazil")]
for pos, name, nat in NEW:
    hits = build.search("", by="name,search_terms", q=name, n=250)
    print("\n== %s %s (%s): %d hits" % (pos, name, nat, len(hits)))
    for h in hits:
        d = h["document"]
        if d.get("type_id") != "person": continue
        if not d.get("fm_id"): continue
        dbid = int(d["fm_id"]); rows = hist.rows(dbid)
        sc = [r for r in rows if r["club"] == 2448]
        n = (d.get("nation") or {}).get("name")
        if not sc and (n != nat or d.get("classification_id") != "non_player"): continue
        by = collections.Counter()
        for r in rows: by[(r["year"], r["club"])] += r["apps"] or 0
        peak = max(by, key=by.get) if by else None
        scy = collections.Counter()
        for r in sc: scy[r["year"]] += r["apps"] or 0
        print("  %-10s %-28s %-8s %-10s dob %s now %s | SC seasons %s | peak %s %s (%s apps)" % (
            dbid, d["name"][:28], d.get("classification_id"), n, fm26_people.dob(dbid), (d.get("team") or {}).get("name"),
            dict(sorted(scy.items())), peak and peak[0], (names.get("club", peak[1]) or peak[1]) if peak else None, peak and by[peak]))
