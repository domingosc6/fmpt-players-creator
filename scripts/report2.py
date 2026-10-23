import json, os, re, sys, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import fm_names
T = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work") + "/"
people = json.load(open(T + "people.json")); idx = json.load(open(T + "idx_names.json"))
m = json.load(open(T + "match.json"))
namer = fm_names.Names()
cids = {d["club"] for d in people.values() if d["club"]}
namer.fetch([("team", c) for c in cids]); namer.save()

def flat(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return set(w for w in re.sub(r"[^a-z ]", " ", s.lower()).split() if len(w) > 2)

# the sheet writes clubs short; the index writes them long. Overlap on the words
# that carry the club - "Braga" in "Sp. Braga" and "Sporting Clube de Braga".
STOP = flat("sport sporting clube club futebol futbol associacao desportivo de da do dos das")
def clubname(u):
    c = people[u]["club"]
    return namer.club(str(int(c) * fm_names.UID_SCALE)) if c else None

def pick(sheet_club, us):
    if len(us) == 1:
        return us[0], "only"
    want = flat(sheet_club) - STOP
    best = [(len(want & (flat(clubname(u)) - STOP)), people[u]["n"], u) for u in us]
    best.sort(reverse=True)
    return best[0][2], ("club" if best[0][0] else "changes")

rows = []
for club, pos, name, nat, us in m["hit"]:
    u, how = pick(club, us)
    d = people[u]
    live = bool((idx.get(u) or {}).get("n"))
    fm26 = "3733" in d["v"]
    to_player = any(o != "2" and n2 == "2" for o, n2 in d["ptyp"])
    b = ("player -> staff" if live and fm26 else
         "live, untouched in FM26" if live else
         "gone (staff -> player)" if to_player or d["n"] >= 100 else "gone (player)")
    rows.append((b, club, name, u, d["n"], how, clubname(u), len(us)))

from collections import Counter
print(Counter(r[0] for r in rows))
for b in ("player -> staff", "gone (staff -> player)", "gone (player)", "live, untouched in FM26"):
    print("\n== %s" % b)
    for r in sorted(x for x in rows if x[0] == b):
        print("   %-16s %-22s %-20s ch=%-4d via=%-7s club=%s" % (r[1], r[2], r[3], r[4], r[5], r[6]))
json.dump(rows, open(T + "rows.json", "w"))
