import json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
sys.path.insert(0, os.path.expanduser("~/Documents/FMPT-Legends/creator"))
import sources.nft as nft
UA = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}
os.makedirs("nft_cache", exist_ok=True)
def get(url):
    path = os.path.join("nft_cache", re.sub(r"[^A-Za-z0-9]", "_", url)[-150:])
    if os.path.exists(path):
        return open(path, encoding="utf-8").read()
    for attempt in range(3):
        try:
            time.sleep(1.2)
            t = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf-8", "replace")
            open(path, "w", encoding="utf-8").write(t)
            return t
        except Exception:
            time.sleep(5 * (attempt + 1))
    return ""
def norm(t):
    t = unicodedata.normalize("NFKD", t or ""); return re.sub(r"[^a-z ]", "", "".join(c for c in t if not unicodedata.combining(c)).lower()).strip()
def nation(html):
    m = re.search(r'<a[^>]+href="/country/\d+/[^"]*"[^>]*>\s*([^<]+?)\s*</a>', html)
    return m.group(1) if m else None
P = json.load(open("profiles.json")); C = json.load(open("caps.json"))
for p in P:
    res = C[p["name"]]
    terms = [p["name"]] + ([p["name"].split()[-1]] if len(p["name"].split()) > 1 else [])
    seen = {c["id"] for c in res["candidates"]}
    for t in terms:
        try:
            hits = json.loads(get("https://www.national-football-teams.com/search.html?primarySearchType=0&ajax=true&term=" + urllib.parse.quote(t)))
        except Exception:
            continue
        for h in hits:
            if h.get("category") != "player" or h["value"] in seen:
                continue
            ln, pn = norm(h["label"]).split(), norm(p["name"]).split()
            if not (set(pn) & set(ln)):
                continue
            seen.add(h["value"])
            html = get("https://www.national-football-teams.com/player/%s.html" % h["value"])
            dob = nft.dob(html)
            if p["dob"] and dob and tuple(dob) != tuple(p["dob"]):
                continue
            if not p["dob"] and norm(h["label"]) != norm(p["name"]):
                continue
            ms = nft.matches(html)
            res["candidates"].append({"id": h["value"], "label": h["label"], "dob": dob, "caps": len(ms), "goals": sum(g for _, g in ms),
                                      "dob_match": bool(dob and p["dob"] and tuple(dob) == tuple(p["dob"]))})
    for c in res["candidates"]:
        if "nation" not in c:
            html = get("https://www.national-football-teams.com/player/%s.html" % c["id"])
            c["nation"] = nation(html)
            c["label"] = c.get("label") or c.get("title")
    best = [c for c in res["candidates"] if c["dob_match"]] or ([] if p["dob"] else res["candidates"])
    res["best"] = best
    print("%-20s %s" % (p["name"], "; ".join("%s [%s] %s caps dob=%s%s" % (c["label"], c["nation"], c["caps"], c["dob"], " MATCH" if c["dob_match"] else "") for c in best) or "- no senior caps on NFT"))
json.dump(C, open("caps.json", "w"), ensure_ascii=False, indent=1)
