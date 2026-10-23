"""Names for FM database ids, from the search index behind fmref.com.

Every unique id in a changeset is DBID * 4294967297 exactly - people as well as
clubs - so a record's name is one lookup away. Answers are cached on disk; the
dataset only moves when FM ships new data.
"""
import json
import os
import time
import urllib.request

UID_SCALE = 4294967297
HOST = "https://1r3p0ghdzwktqxu9p-1.a1.typesense.net"
KEY = "ItfYDIz1mGDuZVXzvkYj0jYJ4avarL02"          # public search-only key
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fm_names_cache.json")
BATCH = 50


# A club FM flags EXTINCT carries no nation in the index, so the converter reads
# the competitions on its rows instead - and where two countries are named in
# equal measure it reports the tie rather than guessing. These are the ties
# settled by hand. FM's own short names are the evidence: Chicago Sting answers
# to "Chicago (NASL)", an American league, so it is not the European default its
# Italian rows would have left it on. USER DECISION 2026-09-08.
# Applied over the cache, not into it by hand, so a rebuilt cache keeps them.
NATION_OVERRIDES = {
    ("team", 72023998): "The United States of America",   # Chicago Sting (NASL)
}

def dbid(uid):
    """DBID behind a changeset unique id, or None if it is not one."""
    try:
        n = int(uid)
    except (TypeError, ValueError):
        return None
    return n // UID_SCALE if n > 0 and n % UID_SCALE == 0 else (n if 0 < n < UID_SCALE else None)


class Names:
    def __init__(self, offline=False):
        self.offline = offline
        self._names_idx = None
        self.cache = {}
        if os.path.exists(CACHE):
            with open(CACHE) as fh:
                self.cache = json.load(fh)
        self._override()

    def save(self):
        with open(CACHE, "w") as fh:
            json.dump(self.cache, fh, indent=0, sort_keys=True, ensure_ascii=False)

    def fetch(self, want):
        """want: iterable of (type_id, dbid). Fills the cache; misses cache as ''."""
        want = [k for k in want if k and k[1] is not None]
        todo = [k for k in dict.fromkeys(want) if self._stale("%s:%s" % k)]
        if not todo or self.offline:
            return
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            body = {"searches": [{"collection": "detailed_game_items", "q": "*", "query_by": "",
                                  "filter_by": "type_id:=%s && fm_id:=%d" % (t, d)} for t, d in chunk]}
            req = urllib.request.Request(HOST + "/multi_search?x-typesense-api-key=" + KEY,
                                         data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json",
                                                  "User-Agent": "fmpt-legends/1.0"})
            res = None
            for attempt in range(3):
                try:
                    res = json.load(urllib.request.urlopen(req, timeout=30))["results"]
                    break
                except Exception:
                    time.sleep(0.5 * (attempt + 1))
            if res is None:
                continue                             # this batch stays unnamed
            for key, out in zip(chunk, res):
                hits = out.get("hits") or []
                if not hits:
                    self.cache["%s:%s" % key] = ""
                    continue
                d = hits[0]["document"]
                # the search terms carry FM's own short names ("A. Bilbao B"),
                # which is the only place a B team announces itself
                e = {"n": d["name"], "t": d.get("search_terms") or []}
                # a club's nation decides its season calendar (SEASON_CALENDAR in
                # the converter). Always written, so an entry from an older build
                # is distinguishable from a club FM files under no nation.
                e["na"] = ((d.get("nation") or {}).get("name")) or ""
                self.cache["%s:%s" % key] = e
            self._override()
            self._names_idx = None                   # new clubs, rebuild the index
            self.save()                              # progress survives a failure
            time.sleep(0.1)

    def _override(self):
        """Write the hand-settled nations onto the cache. A club with no nation
        of its own is the only case; an entry that already names one is left
        alone, so an override can never contradict the index."""
        for (kind, d), na in NATION_OVERRIDES.items():
            key = "%s:%s" % (kind, d)
            v = self.cache.get(key)
            if isinstance(v, str):
                v = {"n": v, "t": []}
            if not isinstance(v, dict):
                continue
            if v.get("na"):
                continue
            v["na"] = na
            self.cache[key] = v

    def _stale(self, key):
        """Not cached, or cached by a build that stored no nation. A miss is the
        empty string and stays a miss - it is not re-asked."""
        v = self.cache.get(key)
        if v is None:
            return True
        return isinstance(v, dict) and "na" not in v

    def person_nation(self, uid):
        """The person's own nation. Present for anyone already in FM's database;
        a created player is not in the index, so the file has to say (`Pnti`)."""
        return ((self.entry("person", uid) or {}).get("na")) or None

    def nation(self, cid):
        """The club's nation, or None when unknown - an id the index does not
        resolve, or a club FM files under no nation (every EXTINCT club).

        A B team with no nation of its own takes its PARENT's: the index drops
        the nation for `Brondbyernes Idraetsforening II` but not for
        `Brondbyernes Idraetsforening`, and a reserve side plays in its parent's
        country by definition, so the parent's season calendar is the right one
        (user rule 2026-09-08)."""
        own = ((self.entry("team", cid) or {}).get("na")) or None
        if own:
            return own
        parent = self.parent_of(cid)
        return (((self.entry("team", parent) or {}).get("na")) or None) if parent else None

    def _by_name(self):
        """name (lowercased) -> club ids that answer to it, over the whole cache.
        Built once; only clubs already fetched can be found, which is why the
        parent of a B team resolves when the file mentions the first team too."""
        if self._names_idx is None:
            idx = {}
            for key, v in self.cache.items():
                if not key.startswith("team:") or not isinstance(v, dict):
                    continue
                cid = int(key.split(":", 1)[1]) * UID_SCALE
                for t in list(v.get("t") or []) + [v.get("n") or ""]:
                    t = (t or "").strip().lower()
                    if t:
                        idx.setdefault(t, set()).add(cid)
            self._names_idx = idx
        return self._names_idx

    @staticmethod
    def _squash(name):
        return "".join(ch for ch in (name or "").lower() if ch.isalnum())

    def parent_of(self, cid):
        """The club this one is the B team of, or None. FM's own short names are
        the evidence, the same ones `is_b_team` reads: strip the B suffix and the
        first team is what is left. Only a candidate that carries a nation is
        accepted, and `is_b_team` has to agree.

        The parent's FULL NAME must also sit inside the child's. `is_b_team`
        matches on short names too, and three-letter ones collide across
        countries: it made Chemnitzer FC II ("CFC II") the B team of Coritiba
        ("CFC") in Brazil, and Mattersburg Amateure ("SVM") of SV Meppen. The
        cost of the guard is a real pair spelled differently (FC Wacker
        Innsbruck against Fussballclub Wacker Innsbruck II), which simply keeps
        the European default it had before - a wrong nation writes a wrong date,
        a missed one changes nothing."""
        e = self.entry("team", cid)
        if not e:
            return None
        d = dbid(cid)
        mine = self._squash(e.get("n"))
        for t in list(e.get("t") or []) + [e.get("n") or ""]:
            t = (t or "").strip().lower()
            for suf in self.B_SUFFIX:
                if not t.endswith(suf):
                    continue
                base = t[:-len(suf)].strip()
                for cand in self._by_name().get(base, ()):
                    if dbid(cand) == d:
                        continue
                    ce = self.entry("team", cand) or {}
                    if not (ce.get("na") or None):
                        continue
                    theirs = self._squash(ce.get("n"))
                    if not theirs or not mine or theirs not in mine:
                        continue
                    if self.is_b_team(cid, cand):
                        return cand
        return None

    def entry(self, kind, ident):
        d = dbid(ident)
        v = self.cache.get("%s:%s" % (kind, d)) if d is not None else None
        return {"n": v, "t": []} if isinstance(v, str) else v

    def get(self, kind, ident):
        v = self.entry(kind, ident)
        return (v or {}).get("n") or None

    B_SUFFIX = (" b", " ii", " c", " 2")

    @staticmethod
    def _is_acronym(name):
        """A bare short code like "CFC" or "SVM" - one token, four characters or
        fewer. Not enough to identify a club: these collide across countries."""
        n = (name or "").replace(".", "").strip()
        return " " not in n and len(n) <= 4

    def is_b_team(self, child, parent):
        """Is `child` the B team of `parent`? FM's short names say so: Bilbao
        Athletic answers to "A. Bilbao B", Athletic Club to "A. Bilbao".

        Two things disqualify a match. A base that is a bare ACRONYM, because
        three-letter codes are not unique across FM's world: "CFC II" made
        Chemnitzer FC II the B team of Coritiba, and "SVM II" made Mattersburg
        Amateure the B team of SV Meppen. And a NATION that contradicts - a
        reserve side plays in its parent's country, so two known and different
        nations mean these are two clubs that merely share a short name.
        A real pair always has a fuller name in common ("a. bilbao")."""
        a, b = self.entry("team", child), self.entry("team", parent)
        if not a or not b:
            return False
        na, nb = a.get("na") or None, b.get("na") or None
        if na and nb and na != nb:
            return False
        pt = {t.strip().lower() for t in b["t"] + [b["n"] or ""] if t}
        for t in a["t"] + [a["n"] or ""]:
            t = (t or "").strip().lower()
            for suf in self.B_SUFFIX:
                if not t.endswith(suf):
                    continue
                base = t[:-len(suf)].strip()
                if base and not self._is_acronym(base) and base in pt:
                    return True
        return False

    def person(self, uid):
        return self.get("person", uid)

    def club(self, cid):
        return self.get("team", cid)
