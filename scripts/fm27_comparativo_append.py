"""Full Comparativo rows for the legends the sheet lacks (fm27_comparativo.py first):
Player, Position (only ratings 18+, FM style "M/AM C"), CA, PA, DB (blank), Country,
Team (the sheet's own short name when it lists the club - work/sheet_team_names.json),
League (the club's nation), Editor File, Obs., FM27.

    py scripts/fm27_comparativo_append.py Portugal [extra uid ...]
"""
import os, sys, json, csv, struct
ROOT = r"C:\DBC\FMPT\fmpt-players-creator"
sys.path[:0] = [os.path.join(ROOT, "scripts"), os.path.join(ROOT, "creator")]
import convert_edition as c, fm_names, fm27_fix as F

S = 4294967297
country = sys.argv[1] if len(sys.argv) > 1 else "Portugal"
LINE = {"Pgoa": ("GK", ""), "Pdls": ("D", "L"), "Pdce": ("D", "C"), "Pdrs": ("D", "R"),
        "Pwbl": ("WB", "L"), "Pwbr": ("WB", "R"), "Pdmc": ("DM", ""), "Pmls": ("M", "L"),
        "Pmce": ("M", "C"), "Pmrs": ("M", "R"), "Paml": ("AM", "L"), "Pamc": ("AM", "C"),
        "Pamr": ("AM", "R"), "Pace": ("ST", "")}
ORDER = ["GK", "D", "WB", "DM", "M", "AM", "ST"]


def pos_string(r):
    lines = {}
    for p, v in r.items():
        if p in LINE and v and v >= 18:
            ln, sd = LINE[p]
            lines.setdefault(ln, set()).add(sd)
    parts, prev = [], None
    for ln in ORDER:
        if ln not in lines:
            continue
        sides = "".join(s for s in "RLC" if s in lines[ln])
        # M and AM (or D and WB) with the same sides read "M/AM C"
        if prev and prev[1] == sides and sides and {prev[0], ln} in ({"M", "AM"}, {"D", "WB"}):
            parts[-1] = "%s/%s %s" % (prev[0], ln, sides)
            prev = None
            continue
        parts.append(ln + (" " + sides if sides else ""))
        prev = (ln, sides)
    return ", ".join(parts)


def last_val(rs, prop):
    v = None
    for r in rs:
        if c.rec_prop(r) == prop:
            nv = r.find('*[@id="new_value"]')
            if nv is not None and nv.get("value") not in (None, ""):
                v = nv.get("value")
    return v


def last_ref(rs, prop):
    v = None
    for r in rs:
        if c.rec_prop(r) == prop:
            ref = c.club_of(r.find('*[@id="new_value"]'))
            if ref:
                v = int(ref[1])
                v = v // S if v > 10 ** 8 else v
    return v


def nat_of(rs):
    for r in reversed(rs):
        if c.rec_prop(r) == "Pnti":
            for el in r.iter():
                if el.get("id") in ("Nnat", "DBID") and el.get("value"):
                    v = int(el.get("value"))
                    return v // S if v > 10 ** 8 else v
    return None


NATION = {"The Islamic Republic of Iran": "Iran", "The Democratic Republic of the Congo": "DR Congo",
          "Korea Republic": "South Korea", "Republic of Ireland": "Ireland"}


def nation_name(n):
    n = n or ""
    n = NATION.get(n, n)
    return n[4:] if n.startswith("The ") else n


_CLUB_NATION = {}


def club_country(cid, namer):
    """The nation an FM27 club row names (u32 row index right after its first
    byte: Benfica, Porto and Sporting all read 162), for the extinct clubs the
    name index gives no nation. FM27's own nation table does not decode
    (fm_db_world reads FM18-style files), so a row index is named by the
    clubs the index DOES place: the nation most of them share."""
    if not _CLUB_NATION:
        import pickle, collections, fm_db_world, fm26_install
        sys.path.insert(0, os.path.join(ROOT, "comparativo"))
        from fm26_leagues import index_map
        from club_fields import rows_by_dbid
        cache = os.path.join(ROOT, "work", "fm27_server_secs.pkl")
        if os.path.exists(cache):
            secs = pickle.load(open(cache, "rb"))
        else:
            secs = fm_db_world.sections(os.path.join(fm26_install.db_dir(27), "server_db.dat"))
            pickle.dump(secs, open(cache, "wb"))
        rows = rows_by_dbid(secs[3], index_map(secs[3]))
        idx = {d: struct.unpack_from("<I", r, 1)[0] for d, r in rows.items() if len(r) > 5}
        votes = collections.defaultdict(collections.Counter)
        for d, i in idx.items():
            na = (namer.entry("team", d) or {}).get("na")
            if na:
                votes[i][na] += 1
        names = {i: v.most_common(1)[0][0] for i, v in votes.items()}
        _CLUB_NATION.update({d: names.get(i, "") for d, i in idx.items()})
    return _CLUB_NATION.get(cid) or ""


_KIT = {}


def club_colours(cid):
    """(background RGB, text RGB) of an FM27 club: the last 8 bytes of its row in
    client table 4 (rows by club index, opening with index u32 + founding year
    u16 + ffffffff), two colours of alpha, red, green, blue. Benfica red on
    white text... read as (207,28,44) then (250,250,250); the sheet's own cells
    show white text on the club colour, so the first is the background
    (user's probe, Infesta: properties tbcl/ttcl, client fields)."""
    if not _KIT:
        import pickle, fm_db_world, fm26_install
        sys.path.insert(0, os.path.join(ROOT, "comparativo"))
        from fm26_leagues import index_map
        cache = os.path.join(ROOT, "work", "fm27_client_secs.pkl")
        if os.path.exists(cache):
            cl = pickle.load(open(cache, "rb"))
        else:
            cl = fm_db_world.sections(os.path.join(fm26_install.db_dir(27), "client_db.dat"))
            pickle.dump(cl, open(cache, "wb"))
        m = index_map(cl[3])
        t, starts, pos = cl[4], [], 12
        for k in range(len(m) + 1):
            key = struct.pack("<I", k)
            q = t.find(key, pos)
            while q >= 0 and t[q + 6:q + 10] != b"\xff\xff\xff\xff":
                q = t.find(key, q + 1)
            if q < 0:
                break
            starts.append(q)
            pos = q + 10
        starts.append(len(t))
        for i, d in m.items():
            if i + 1 < len(starts):
                e = starts[i + 1]
                c8 = t[e - 8:e]
                _KIT[d] = (tuple(c8[1:4]), tuple(c8[5:8]))
    return _KIT.get(cid)


def sheet_names(country):
    """{club id: [(display name, words)]} from the squad sheet extract: the name
    as the sheet writes it, captain marks (C)/(VC) dropped (user, 2026-11-14)."""
    import re as _re
    raw = json.load(open(os.path.join(ROOT, "work", "%s_sheet_clubs.json" % country.lower()), encoding="utf-8"))
    ids = F.sheet_clubs(country)
    out = {}
    for name, ents in raw.items():
        if name.startswith("_"):
            continue
        disp = " ".join(_re.sub(r"\((C|VC)\)", " ", name, flags=_re.I).split())
        words = {w for w in F.norm_name(name).split() if len(w) > 2}
        for cl, _y in ids.get(F.norm_name(name), []):
            out.setdefault(F.as_dbid(cl), []).append((disp, words))
    return out


def main():
    namer = fm_names.Names()
    ed17, ed24, ed26, ed27 = F.Edition(17), F.Edition(24), F.Edition(26), F.Edition(27)
    path = os.path.join(r"C:\DBC\FMPT\FM 27 converted files", "FMPT Legends - %s - target2026.xml" % country)
    tree, changes, created, recs, staff, names = F.scan(path)
    status = {r["uid"]: r for r in csv.DictReader(open(F.STATUS, encoding="utf-8")) if r["file"] == country}
    miss = json.load(open(os.path.join(ROOT, "work", "comparativo_%s_missing.json" % country.lower()), encoding="utf-8"))
    people = {q["uid"]: q for q in json.load(open(os.path.join(ROOT, "work", "comparativo_%s.json" % country.lower()), encoding="utf-8"))["people"]}
    # the current statuses: a legend the fix no longer carries (an old twin) drops out
    miss = [people[p["uid"]] for p in miss if p["uid"] in people]
    for u in sys.argv[2:]:
        if u in people and all(u != p["uid"] for p in miss):
            miss.append(people[u])
    by_club = sheet_names(country)
    sheet_team = json.load(open(os.path.join(ROOT, "work", "sheet_team_names.json"), encoding="utf-8"))
    sheet_set = set(sheet_team)
    docs = F.index_docs([int(status[p["uid"]]["dbid"]) for p in miss if status[p["uid"]]["dbid"]])
    rows = []
    for p in miss:
        st = status[p["uid"]]
        d = int(st["dbid"]) if st["dbid"] else None
        rs = recs.get(p["uid"], []) + (recs.get(str(d * S), []) if d else [])
        # positions: the database's, overruled by what the file sets
        rat = dict(ed27.player_block(d)) if d and ed27.has(d) else {}
        for ed in (ed26, ed24, ed17):
            if not rat and d and ed.has(d):
                rat = dict(ed.player_block(d))
        for prop in LINE:
            v = last_val(rs, prop)
            if v is not None:
                rat[prop] = int(v)
        pos = pos_string(rat) if p["role"] == "player" else ""
        # CA/PA: the file's, else the database's (u16 at bytes 11 and 13 in FM17,
        # FM24, FM26 and FM27 alike - FM24-built odvl and the editions agree)
        ca, pa = F.last_int(rs, "PCAB"), F.last_int(rs, "PPAB")
        for ed in (ed27, ed26, ed24, ed17):
            if d and ed.has(d) and ed.type(d) in (2, 3):
                s0 = ed.db.prows[d][0]
                dca, dpa = struct.unpack_from("<hh", ed.db.people, s0 + 11)[0], struct.unpack_from("<h", ed.db.people, s0 + 13)[0]
                if not ca and 0 < dca <= 200:
                    ca = dca
                if not pa and dpa and -200 <= dpa <= 200:
                    pa = dpa
                if ca and pa:
                    break
        # nationality: the file's, else FM26's database
        nat = nat_of(rs)
        for ed in (ed27, ed26, ed24, ed17):
            if nat is None and d and ed.has(d):
                bb = ed.birth_block(d)
                nat = bb["nation"] if bb and 0 < bb["nation"] < 10 ** 7 else None
        # club: what the fix wrote (Pcti / open spell), else FM27's own
        pcti, spell, _ = F.file_club(rs)
        club = pcti or spell
        club = int(club) // S if club and int(club) > 10 ** 8 else (int(club) if club else None)
        doc = docs.get(d) if d else None
        if club is None and doc and doc.get("team"):
            club = int(doc["team"]["fm_id"])
        namer.fetch([("nation", nat), ("team", club)])
        team, league = "", ""
        if club:
            e = namer.entry("team", club) or {}
            cands = [e.get("n")] + list(e.get("t") or [])
            hit = next((t for t in cands if t in sheet_set), None)
            if not hit:
                # a sheet name of two or more words that abbreviates this club
                # ("Vit. Guimaraes" for Vitoria Sport Clube, known as Vitoria Guimaraes)
                import unicodedata as _u
                def _w(x):
                    x = _u.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
                    return [t for t in x.replace(".", " ").split() if t]
                pool = set(_w(e.get("n") or "")) | {t for term in (e.get("t") or []) for t in _w(term)}
                fits = [sn for sn in sheet_team if len(_w(sn)) >= 2 and not sn.endswith(" B")
                        and all(any(f.startswith(x) for f in pool) for x in _w(sn))]
                hit = fits[0] if len(fits) == 1 else None
            if not hit:
                # FM's short name: a term whose every word starts a word of the
                # full name ("Estrela Amadora", "Vit. Setúbal"), not a nickname
                import unicodedata
                def w(x):
                    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
                    return [t for t in x.replace(".", " ").split() if t]
                full = w(e.get("n") or "")
                short = [t for t in (e.get("t") or []) if t and t[0].isupper() and not t.isupper()
                         and t != e.get("n") and w(t) and all(any(f.startswith(x) for f in full) for x in w(t))]
                hit = min(short, key=len) if short else e.get("n") or ""
            # the club's distinctive word when the sheet knows it by that alone
            # ("Boavista Futebol Clube - SAD" is "Boavista"), and a few by hand
            GENERIC = {"sport", "clube", "club", "futebol", "fc", "sad", "de", "do", "da", "dos", "e",
                       "desportivo", "cf", "sc", "-", "cd", "sporting"}
            rest = [t for t in (e.get("n") or "").split() if t.lower() not in GENERIC]
            if hit not in sheet_set and len(rest) == 1 and rest[0] in sheet_set:
                hit = rest[0]
            hit = {"Estoril Praia": "Estoril", "Olympiacos": "Olympiakos", "Alverca SAD": "Alverca",
                   "Sport Lisboa e Benfica B": "Benfica B"}.get(hit, hit)
            # an extinct club carries no nation in the index: its country from the
            # competitions it played in (fm_names.nation), as the league (user,
            # 2026-11-14: "use that country as the league")
            team, league = hit, e.get("na") or namer.nation(club) or nation_name(club_country(club, namer))
        # the squad sheet's own name for him at that club (Pedro Barbosa for
        # Pedro Alexandre Santos Barbosa): every word of it one of his
        disp = p["name"]
        if club:
            mine = {w for n in [p["name"]] + list(F.name_parts(rs)[0]) + list(F.name_parts(rs)[1])
                    for w in F.norm_name(n).split() if len(w) > 2}
            fits = [dn for dn, ws in by_club.get(club, []) if ws and ws <= mine]
            if fits:
                disp = max(fits, key=len)
        kit = club_colours(club) if club else None
        rows.append({"uid": p["uid"], "name": disp, "file_name": p["name"], "kit": kit, "role": p["role"], "pos": pos,
                     "ca": ca, "pa": pa, "country": nation_name(namer.get("nation", nat)) if nat else "",
                     "team": team, "league": league, "file": country,
                     "obs": "/".join(x for x in ("Youth" if p["youth"] else "", p["ot"]) if x),
                     "fm27": p["fm27"]})
    namer.save()
    json.dump(rows, open(os.path.join(ROOT, "work", "comparativo_%s_append_full.json" % country.lower()), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    for r in rows[:25] + [r for r in rows if r["role"] == "staff"][:5]:
        print("%-28s %-14s %-12s %-22s %-10s %s" % (r["name"][:28], r["pos"], r["country"], r["team"][:22], r["league"], r["role"]))
    print(len(rows), "no pos", sum(1 for r in rows if r["role"] == "player" and not r["pos"]),
          "no team", sum(1 for r in rows if not r["team"]), "no country", sum(1 for r in rows if not r["country"]))


main()
