import json, collections, os
PLACEMENTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = {p["name"]: p for p in json.load(open(os.path.join(PLACEMENTS, "santa_clara/profiles.json")))}
PROP = [  # name, kind, club-name substring
 ("Gabriel Batista","A","Santa Clara"),("Sidney Lima","A","Santa Clara"),("Gabriel Silva","A","Santa Clara"),
 ("Vinícius Lopes","A","Santa Clara"),("Pedro Ferreira","A","Santa Clara"),
 ("MT","?","Vasco"),("Darlan Mendes","S","Wuhan"),("Lucas Soares","Y","Cruzeiro"),("Serginho","S","Oliveirense"),
 ("Bruno Almeida","S","Trofense"),("Rildo","Y","Grêmio"),("Paulo Victor","R","Nova Iguaçu"),
 ("Matheusinho","S","América"),("Klismahn","Y","Estoril"),("Pedro Pacheco","S","Amarante"),
 ("Welinton Torrão","S","Athletic Club"),("Brenner","Y","Taubaté"),("Henrique Silva","Y","Cruzeiro"),
 ("Gonçalo Paciência","Y","Futebol Clube do Porto"),("Reinaldo","Y","Criciúma"),("Anthony Carter","S","Oliveirense"),
 ("Diogo Calila","S","B-SAD"),("João Bravim","R","Santos"),("João Costa","R","Loures"),("Djé","R","Alverca B"),
 ("Andrey","S","Avaí"),("Miguel Pires","Y","Alverca"),("Edney","Y","Palmeiras"),("Jader","Y","Paranaense"),
 ("Thauan Lara","Y","Internacional"),("Daniel Borges","Y","Mineiro"),("Luis Fernando","Y","Cruzeiro")]
def age(dob, y): return None if not dob else y - dob[2] - (1 if (dob[1], dob[0]) > (7, 1) else 0)
for name, kind, sub in PROP:
    p = P[name]; rows = [r for r in p["career"] if sub in (r["club_name"] or "") and not (sub=="Futebol Clube do Porto" and "B" == r["club_name"][-1])]
    if sub == "Alverca": rows = [r for r in rows if r["club_name"].endswith("Alverca")]
    ids = sorted({r["club"] for r in rows}); names = sorted({r["club_name"] for r in rows})
    if kind in ("S","A"):
        apps = collections.Counter()
        for r in rows: apps[r["year"]] += r["apps"] or 0
        season = max(sorted(apps), key=lambda y: apps[y]) if apps else None
    else:
        ys = [r["year"] for r in rows if age(p["dob"], r["year"]) is None or age(p["dob"], r["year"]) >= 14]
        season = min(ys) if ys else None
    print("%-18s %s %-45s ids %s season %s age %s" % (name, kind, "; ".join(names)[:45], ids, season, age(p["dob"], season) if season else None))
