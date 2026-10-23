import json, random
P = {p["name"]: p for p in json.load(open("santa_clara/profiles.json"))}
TM_DOB = {"MT": [1, 3, 2001], "Lucas Soares": [4, 5, 1998], "Bruno Almeida": [9, 9, 1996], "Rildo": [21, 1, 2000], "Jader": [24, 7, 2003]}
YOUTH = {"MT": 339, "Lucas Soares": 321, "Serginho": 2389, "Bruno Almeida": 2386, "Rildo": 324, "Klismahn": 2390,
         "Welinton Torrão": 314, "Brenner": 311036, "Henrique Silva": 321, "Gonçalo Paciência": 1478, "Reinaldo": 320,
         "Anthony Carter": 7540205, "Diogo Calila": 1487, "Andrey": 107208, "Miguel Pires": 2391, "Edney": 329,
         "Jader": 107206, "Thauan Lara": 326, "Daniel Borges": 314, "Luis Fernando": 321}
SENIOR = {"Darlan Mendes": 2024, "Matheusinho": 2019, "Pedro Pacheco": 2019}
def age(dob, y): return y - dob[2] - (1 if (dob[1], dob[0]) > (7, 1) else 0)
def neg(pa):
    mids = [95, 105, 115, 125, 135]; best = min(mids, key=lambda m: (abs(pa - m), -m))
    return {95: -55, 105: -6, 115: -65, 125: -7, 135: -75}[best]
rng = random.Random(20261022)
out = {}
for name, club in YOUTH.items():
    p = P[name]; dob = p["dob"] or TM_DOB[name]
    ys = sorted({r["year"] for r in p["career"] if r["club"] == club})
    at = {y: age(dob, y) for y in ys}
    ok = [y for y in ys if at[y] in (17, 18)]
    season = ok[0] if ok else min(ys, key=lambda y: (abs(at[y] - 17.5), y))
    ca, pa = int(p["ca"]), int(p["pa"])
    nca = ca if ca < 80 else ca - rng.randint(20, 30)
    npa = pa if pa < 0 else neg(pa)
    out[name] = (season, nca, npa)
    print("%-18s Y club %-8s season %s (age %s; ages there %s) CA %s->%s PA %s->%s" % (name, club, season, at[season], sorted(set(at.values())), ca, nca, pa, npa))
for name, season in SENIOR.items():
    p = P[name]; ca, pa = int(p["ca"]), int(p["pa"]); a = age(p["dob"], season)
    nca, npa = ca - 5, (neg(pa) if a <= 21 else pa - 5)
    out[name] = (season, nca, npa)
    print("%-18s S season %s age %s CA %s->%s PA %s->%s" % (name, season, a, ca, nca, pa, npa))
json.dump(out, open("santa_clara/ratings.json", "w"), ensure_ascii=False, indent=1)
