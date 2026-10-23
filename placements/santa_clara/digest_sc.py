import json, re, unicodedata, collections
P = [p for p in json.load(open("santa_clara/profiles.json")) if p["name"] not in ("Gabriel Batista","Sidney Lima","Gabriel Silva","Vinícius Lopes","Pedro Ferreira")]; B = json.load(open("squads.json")); hits = []
GENERIC = set("clube club futebol football fc cf cd gd sc sd ud ac ad as sl cs sporting sport grupo desportivo deportivo de da do dos das del la el le les fk nk sk if bk kv kas rc rcd real atletico atlético associação associacao sociedade sad união uniao uniao united city 1893 1911 1910 1904 1919 1906 calcio ssc ss us futbol fútbol kulübü kulubu spor sportif olympique athletic sv tsv vfb vfl".split())
def norm(t):
    t = unicodedata.normalize("NFKD", t or ""); return re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in t if not unicodedata.combining(c)).lower())
def toks(t): return {w for w in norm(t).split() if w not in GENERIC and len(w) > 2}
def blocks_for(club):
    k = toks(club); out = []
    if not k: return out
    for b in B:
        if b["kind"] != "grid": continue
        bt = toks(b["club"])
        if bt and (bt <= k or k <= bt):
            out.append("%s/%s: %s (%d senior, %d youth)" % (b["file"], b["sheet"], b["club"], len(b["senior"]), len(b["youth"])))
    return out
def age(dob, y):
    return None if not dob else y - dob[2] - (1 if (dob[1], dob[0]) > (7, 1) else 0)
for p in P:
    print("\n" + "=" * 100)
    print("%s | FM26 %s | nat %s | dob %s | CA %s PA %s | now %s" % (p["name"], p["dbid"], p["nationality"], p["dob"], p["ca"], p["pa"], p["club_now"]))
    by = collections.OrderedDict()
    for r in p["career"]:
        c = by.setdefault(r["club_name"] or "?", {"years": [], "apps": 0, "count": 0, "levels": set(), "youth": [], "loan": False, "nation": r["club_nation"], "id": r["club"]})
        c["years"].append(r["year"]); c["apps"] += r["apps"] or 0
        if r["counts"]: c["count"] += r["apps"] or 0
        if r["divi_level"]: c["levels"].add(r["divi_level"])
        if r["youth"] or (age(p["dob"], r["year"]) is not None and 15 <= age(p["dob"], r["year"]) <= 18): c["youth"].append(age(p["dob"], r["year"]))
        c["loan"] |= bool(r["loan"])
    for name, c in by.items():
        print("  %-42s %-12s %s-%s apps %3d counted %3d %s%s%s | top2 %s" % (name[:42], (c["nation"] or "")[:12], min(c["years"]), max(c["years"]), c["apps"], c["count"],
              "YOUTH(ages %s) " % sorted({a for a in c["youth"] if a is not None}) if c["youth"] else "", "loan " if c["loan"] else "",
              "; ".join(sorted(c["levels"]))[:60], p["club_top2"].get(str(c["id"]))))
        for bl in blocks_for(name)[:4]: print("      sheet:", bl)
    nh = [h for h in hits if h["player"] == p["name"]]
    for h in nh: print("  NAME IN SQUADS:", h["file"], "/", h["sheet"], "/", h["club_block"], "| row", h["row"][:5])
