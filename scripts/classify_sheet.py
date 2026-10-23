"""Split a sheet's players by what the FM26 changeset can still do for them.

Four outcomes, the ones the author asked for:

  new add              no record anywhere - nothing to do
  player -> staff      the person is still in FM26 but as a non-player; the
                       record is already in the type-change repair
  staff -> player      the record converts a non-player to a player, but the
                       PERSON is gone from FM26's database, so it imports
                       against nothing
  player gone          same, without the conversion

A person's unique id is (DBID << 32) | nwui; the two halves match for a record
FM ships and differ for one the author invented. Whether the person still
exists is asked of FM26's own decompressed table, not of the fmref index -
fmref is a directory of names, not a statement about this edition.
"""
import json, os, re, struct, sys, unicodedata, urllib.parse, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm_names

S = fm_names.UID_SCALE

def flat(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\(.*?\)", " ", s)
    return [w for w in re.sub(r"[^a-z ]", " ", s.lower()).split()]

def fmref(name, cache):
    if name in cache:
        return cache[name]
    url = (fm_names.HOST + "/collections/detailed_game_items/documents/search"
           "?q=%s&query_by=name,search_terms&filter_by=type_id:=person&per_page=20"
           "&x-typesense-api-key=%s" % (urllib.parse.quote(name), fm_names.KEY))
    req = urllib.request.Request(url, headers={"User-Agent": "fmpt-legends/1.0"})
    try:
        hits = json.load(urllib.request.urlopen(req, timeout=30)).get("hits") or []
    except Exception:
        hits = []
    cache[name] = [(h["document"].get("name"), h["document"].get("fm_id"))
                   for h in hits if h["document"].get("fm_id", "").isdigit()]
    return cache[name]

def main():
    T = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work") + "/"
    people = json.load(open(T + "people.json"))
    careers = json.load(open(T + "careers.json"))
    sys.path.insert(0, os.path.join(ROOT, "creator"))
    import build
    DB = build.people_db()
    lives = lambda d: DB.find(struct.pack("<II", d, d)) >= 0

    by_dbid = {}
    for u in people:
        by_dbid.setdefault(int(u) >> 32, []).append(u)

    repaired = set(re.findall(r"^\| [^|]+ \| (\d+) \|",
                              open(ROOT + "/FM 26 XML Files/explanations/Portugal FM26 - "
                                   "repair after type change.md", encoding="utf-8").read(),
                              re.M))

    # names the file itself writes, for records FM never had
    file_named = {}
    for u, d in people.items():
        s = d["s"]
        for cand in (s.get("Pcna"), (s.get("Pfna", "") + " " + s.get("Psna", "")).strip(),
                     s.get("Pfln")):
            if cand:
                file_named.setdefault(" ".join(flat(cand)), set()).add(u)

    # fmref also names the records FM ships, which the file leaves unnamed
    idx = json.load(open(T + "idx_names.json"))
    for u, e in idx.items():
        for cand in [e.get("n")] + (e.get("t") or []):
            if cand:
                file_named.setdefault(" ".join(flat(cand)), set()).add(u)

    namer = fm_names.Names()
    namer.fetch([("team", int(c)) for v in careers.values() for c in v]); namer.save()
    STOP = set(flat("sport sporting clube club futebol associacao desportivo uniao"))

    def career_words(u):
        w = set()
        for c in careers.get(u, []):
            w |= set(flat(namer.club(str(int(c) * S)))) - STOP
        return w

    rows, cache = [], {}
    club = None
    for line in open(ROOT + "/FM 26 XML Files/explanations/Primeira Liga Historica - "
                     "non-bold main team.md", encoding="utf-8"):
        if line.startswith("## "):
            club = re.sub(r"\s*_\(.*", "", line[3:]).strip()
        elif line.startswith("| ") and not line.startswith(("| Posição", "|---")):
            pos, name, nat = [x.strip() for x in line.strip().strip("|").split("|")]
            key = " ".join(flat(name))
            cands = set(file_named.get(key, ()))
            if not cands:            # the sheet shortens a surname
                for kk, v in file_named.items():
                    if kk.split()[-1:] == key.split()[-1:] and len(key.split()) == 1:
                        cands |= v
            for hit_name, fid in fmref(name, cache):
                if " ".join(flat(hit_name)) == key or key in " ".join(flat(hit_name)):
                    cands |= set(by_dbid.get(int(fid), ()))
            rows.append((club, pos, name, nat, sorted(cands)))

    def pick(sheet_club, us):
        if len(us) < 2:
            return us[0] if us else None
        want = set(flat(sheet_club)) - STOP
        return max(us, key=lambda u: (len(want & career_words(u)), people[u]["n"]))

    out = []
    for club, pos, name, nat, us in rows:
        u = pick(club, us)
        if u is None:
            out.append(("new add", club, pos, name, "", 0, ""))
            continue
        d, dbid = people[u], int(u) >> 32
        made_up = int(u) % S != 0
        alive = (not made_up) and lives(dbid)
        to_player = any(o not in (None, "2") and n == "2" for o, n in d["ptyp"])
        if u in repaired and alive:
            k = "player -> staff (repaired)"
        elif made_up:
            k = "created person (nothing missing)"
        elif alive:
            k = "person alive, record not repaired"
        else:
            k = "GONE: staff -> player" if to_player else "GONE: player"
        out.append((k, club, pos, name, u, d["n"], "%d" % dbid + ("" if len(us) < 2 else " (%d cand.)" % len(us))))
    json.dump(out, open(T + "final.json", "w"))
    from collections import Counter
    print(Counter(r[0] for r in out))
    return out

if __name__ == "__main__":
    main()
