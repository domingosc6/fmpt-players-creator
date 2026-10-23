"""Match the sheet's non-bold main-team players to the records in the FM26 file."""
import json, os, re, sys, unicodedata
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm_names

T = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work") + "/"
people = json.load(open(T + "people.json"))
idx = json.load(open(T + "idx_names.json"))

def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\(.*?\)", " ", s)
    return re.sub(r"[^a-z ]", " ", s.lower()).split()

def keys(s):
    w = norm(s)
    return " ".join(w)

# every name a record answers to: what the file writes, what the index knows
by_name = {}
for u, d in people.items():
    cand = []
    s = d["s"]
    for k in ("Pcna", "Pfln"):
        if s.get(k): cand.append(s[k])
    if s.get("Pfna") or s.get("Psna"):
        cand.append((s.get("Pfna", "") + " " + s.get("Psna", "")).strip())
        if s.get("Psna"): cand.append(s["Psna"])
    e = idx.get(u) or {}
    if e.get("n"): cand.append(e["n"])
    for t in e.get("t") or []: cand.append(t)
    for c in cand:
        k = keys(c)
        if k: by_name.setdefault(k, set()).add(u)

# the sheet
rows = []
club = None
for line in open(ROOT + "/FM 26 XML Files/explanations/Primeira Liga Historica - non-bold main team.md",
                encoding="utf-8"):
    if line.startswith("## "):
        club = re.sub(r"\s*_\(.*", "", line[3:]).strip()
    elif line.startswith("| ") and not line.startswith("| Posição") and not line.startswith("|---"):
        p, n, q = [x.strip() for x in line.strip().strip("|").split("|")]
        rows.append((club, p, n, q))

print("sheet players:", len(rows))
hit, miss = [], []
for club, pos, name, nat in rows:
    k = keys(name)
    us = by_name.get(k) or set()
    if not us:                      # a surname the sheet shortens
        parts = k.split()
        us = set()
        for kk, v in by_name.items():
            if kk.split() == parts or (len(parts) == 1 and kk.split()[-1:] == parts):
                us |= v
    (hit if us else miss).append((club, pos, name, nat, sorted(us)))
print("matched:", len(hit), "unmatched:", len(miss))
json.dump({"hit": hit, "miss": miss}, open(T + "match.json", "w"))
for r in miss:
    print("  no record:", r[0], "|", r[2])
