"""Position and nationality from Transfermarkt's quick search: the row whose
club matches FM26's current club, else whose age matches FM26's birth year."""
import json, re, time, unicodedata, urllib.parse, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
def norm(t):
    t = unicodedata.normalize("NFKD", t or ""); return re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in t if not unicodedata.combining(c)).lower())
GEN = set("fc cf cd sc club clube futebol football sport sporting de da do the ac".split())
def toks(t): return {w for w in norm(t).split() if w not in GEN and len(w) > 2}
P = {p["name"]: p for p in json.load(open("profiles.json"))}
T = json.load(open("targets.json")) + ["Rafael Brito"]
out = {}
for name in T:
    p = P[name]
    time.sleep(2)
    html = urllib.request.urlopen(urllib.request.Request("https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query=" + urllib.parse.quote(name), headers=UA), timeout=40).read().decode("utf-8", "replace")
    rows = []
    for m in re.finditer(r'<td class="hauptlink"><a title="([^"]*)" href="(/[^"]*/profil/spieler/\d+)">.*?<tr><td>(?:<a title="([^"]*)")?.*?<td class="zentriert">([^<]*)</td>.*?<td class="zentriert">(\d*)</td>(.*?)</tr>', html, re.S):
        nats = re.findall(r'class="flaggenrahmen"[^>]*>|title="([^"]+)" alt="[^"]+" class="flaggenrahmen"', m.group(6))
        nats = [n for n in re.findall(r'title="([^"]+)" alt="[^"]+" class="flaggenrahmen"', m.group(6))]
        rows.append({"tm_name": m.group(1), "url": m.group(2), "club": m.group(3), "pos": m.group(4).strip(), "age": int(m.group(5) or 0), "nations": nats})
    want_age = (2026 - p["dob"][2]) if p.get("dob") else None
    club_now = p.get("club_now") or ""
    def score(r):
        s = 0
        if toks(r["club"]) & toks(club_now): s += 2
        if want_age and abs(r["age"] - want_age) <= 1: s += 1
        if norm(r["tm_name"]).split()[-1:] == norm(name).split()[-1:]: s += 1
        return s
    rows.sort(key=score, reverse=True)
    best = rows[0] if rows and score(rows[0]) >= 2 else None
    out[name] = {"best": best, "score": score(rows[0]) if rows else 0, "n": len(rows)}
    print("%-20s %s" % (name, "%s | %s | %s | age %s | %s" % (best["tm_name"], best["pos"], "/".join(best["nations"]), best["age"], best["club"]) if best else "NO MATCH (%d rows)" % len(rows)))
json.dump(out, open("tm.json", "w"), ensure_ascii=False, indent=1)
