"""Senior caps from national-football-teams.com: the search's JSON endpoint,
the exact name (accents ignored), confirmed by date of birth when both have one."""
import json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "creator"))
import sources.nft as nft
UA = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}
def get(url):
    time.sleep(1.2)
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf-8", "replace")
def norm(t):
    t = unicodedata.normalize("NFKD", t or ""); return re.sub(r"[^a-z ]", "", "".join(c for c in t if not unicodedata.combining(c)).lower()).strip()
P = json.load(open(os.path.join(HERE, "profiles.json")))
out = {}
for p in P:
    res = {"candidates": []}
    try:
        hits = json.loads(get("https://www.national-football-teams.com/search.html?primarySearchType=0&ajax=true&term=" + urllib.parse.quote(p["name"])))
    except Exception as e:
        res["error"] = str(e); out[p["name"]] = res; continue
    for h in hits:
        if h.get("category") != "player" or norm(h["label"]) != norm(p["name"]):
            continue
        html = get("https://www.national-football-teams.com/player/%s.html" % h["value"])
        dob = nft.dob(html)
        ms = nft.matches(html)
        nat = re.search(r"<title>[^<]*?\(([^)]+)\)", html)
        res["candidates"].append({"id": h["value"], "dob": dob, "caps": len(ms), "goals": sum(g for _, g in ms),
                                  "title": re.search(r"<title>([^<]*)</title>", html).group(1).strip() if "<title>" in html else None,
                                  "dob_match": bool(dob and p["dob"] and tuple(dob) == tuple(p["dob"]))})
    out[p["name"]] = res
    best = [c for c in res["candidates"] if c["dob_match"]] or res["candidates"]
    print("%-20s %s" % (p["name"], "; ".join("%s caps=%d dob=%s%s" % (c["title"], c["caps"], c["dob"], " MATCH" if c["dob_match"] else "") for c in best) or "-"))
json.dump(out, open(os.path.join(HERE, "caps.json"), "w"), ensure_ascii=False, indent=1)
