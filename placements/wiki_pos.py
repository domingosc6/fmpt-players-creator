import json, re, time, urllib.parse, urllib.request, os
UA={"User-Agent":"fmpt-legends/1.0 (research)"}
def api(lang, **q):
    q.update(format="json", formatversion=2)
    time.sleep(0.5)
    return json.load(urllib.request.urlopen(urllib.request.Request("https://%s.wikipedia.org/w/api.php?%s"%(lang,urllib.parse.urlencode(q)),headers=UA),timeout=30))
P=json.load(open("profiles.json"))
keep=set(json.load(open("targets.json"))) if os.path.exists("targets.json") else None
out={}
for p in P:
    if keep and p["name"] not in keep: continue
    best=None
    for lang in ("en","pt","es"):
        try:
            res=api(lang,action="query",list="search",srsearch="%s footballer"%p["name"] if lang=="en" else "%s futebolista"%p["name"] if lang=="pt" else "%s futbolista"%p["name"],srlimit=3)["query"]["search"]
        except Exception: continue
        for r in res:
            t=api(lang,action="parse",page=r["title"],prop="wikitext")["parse"]["wikitext"]
            dob=p.get("dob")
            if dob and str(dob[2]) not in t[:4000]: continue
            clubs=[c["club_name"] for c in p["career"] if c["club_name"]]
            hits=sum(1 for c in clubs if c and c.split()[-1] in t)
            if hits<2: continue
            pos=re.search(r"\|\s*(position|posição|posicion|posición)\s*=\s*([^\n|]+)",t,re.I)
            nat=re.search(r"\|\s*(nationalteam\d*|selecaonacional\d*|selecciónnacional\d*)\s*=\s*([^\n|]+)",t,re.I)
            cty=re.search(r"\|\s*(birth_place|local_nascimento|lugar de nacimiento|nascimento_local)\s*=\s*([^\n]+)",t,re.I)
            best={"lang":lang,"title":r["title"],"position":pos.group(2).strip() if pos else None,
                  "national_team":nat.group(2).strip() if nat else None,"birth_place":cty.group(2).strip()[:120] if cty else None}
            break
        if best: break
    out[p["name"]]=best
    print("%-20s %s"%(p["name"],best and "%s | pos=%s | nt=%s | born=%s"%(best["title"],best["position"],best["national_team"],best["birth_place"])))
json.dump(out,open("wiki_pos.json","w"),ensure_ascii=False,indent=1)
