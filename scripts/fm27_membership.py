"""Which legends stay in an FM27 file, and which Comparativo row each one is.

The user's rules (2026-11-14), applied to every PLAYER legend of a file:

1. His name is the Common Name, else First + Last name, else the full name.
   Accents and spelling count; nothing is matched on loose words of a full name.
2. His club is the one the latest change in his own record sets (club, else the
   open club spell), else the FM27 database's. Nothing here moves a club.
3. A Comparativo row with his name, his club, a CA within 10 of his CA and a PA
   within 10 of his PA is his row: done.
4. No row: his name at his club in any country squad sheet (Avulsos and youth
   tabs included) means he is added to the Comparativo; found only in a youth tab,
   he is added only when he is 19 or younger on 1 July 2026, else removed. Not in
   any sheet: removed.
5. A record created or updated in FM24/26/27 (its date of birth or seasons were
   written by one of those editors) is never removed: not found anywhere, it is
   kept and added to the Comparativo flagged orange.

decide() returns {uid: {...}} with "how" one of: row, sheet, youth, protected,
removed, and the details behind it.
"""
import re
import unicodedata

FM24 = 3569                           # an FM24 record that fails is asked about, not removed
PROTECTED_FROM = 3733                 # the FM26 editor's build: edited in FM26 or FM27
YOUTH_BORN_AFTER = (2006, 7, 1)       # 19 or younger on 1 July 2026

NEG = {-10: (170, 200), -95: (160, 190), -9: (150, 180), -85: (140, 170), -8: (130, 160), -75: (120, 150),
       -7: (110, 140), -65: (100, 130), -6: (90, 120), -55: (80, 110), -5: (70, 100), -45: (60, 90),
       -4: (50, 80), -35: (40, 70), -3: (30, 60), -25: (20, 50), -2: (10, 40), -15: (5, 35), -1: (1, 30)}

GENERIC = {"sport", "sp", "clube", "club", "futebol", "football", "fc", "sad", "de", "do", "da", "dos",
           "e", "desportivo", "desp", "cf", "sc", "cd", "ud", "ad", "gd", "sl", "ac", "uniao", "the", "and"}


def norm(s):
    """A name as compared: captain marks and spacing gone, case folded, accents KEPT."""
    s = re.sub(r"\((c|vc)\)", " ", str(s or ""), flags=re.I)
    return " ".join(s.split()).casefold()


TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "Ae", "ß": "ss", "đ": "d", "Đ": "D", "ł": "l",
                          "Ł": "L", "ı": "i", "œ": "oe", "Œ": "Oe", "þ": "th", "ð": "d"})


def plain(s):
    s = str(s or "").translate(TRANSLIT)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def fold(s):
    """A name without case, accents or special letters (Frøholdt = Froholdt)."""
    return " ".join(re.split(r"[\s.\-']+", plain(re.sub(r"\((c|vc)\)", " ", str(s or ""), flags=re.I)))).strip()


def name_tier(mine, theirs):
    """With the special characters first, then without them (user, 2026-11-15:
    Pepe and Pepe-with-accents are two players): 4 the same name, 3 the same once
    accents and special letters are gone, 2 the same words in any order or one
    name's words all inside the other's, accents kept (Virgilio = Virgilio Mendes,
    Marcus Abraham = Abraham Marcus), 1 the same without accents, 0 no match."""
    if norm(mine) == norm(theirs):
        return 4
    a, b = fold(mine), fold(theirs)
    if not a or not b:
        return 0
    if a == b:
        return 3
    na, nb = set(norm(mine).split()), set(norm(theirs).split())
    if na <= nb or nb <= na:
        return 2
    wa, wb = set(a.split()), set(b.split())
    return 1 if (wa <= wb or wb <= wa) else 0


def pos_atoms(s):
    """'D/WB R, M/AM RC' -> {(D, R), (WB, R), (M, R), (AM, R), (AM, C), ...}."""
    out = set()
    for part in str(s or "").split(","):
        m = re.match(r"\s*([A-Z/]+)\s*([RLC]*)\s*$", part)
        if not m:
            continue
        for ln in m.group(1).split("/"):
            for sd in (m.group(2) or "-"):
                out.add((ln, "-" if ln in ("GK", "DM", "ST") else sd))
    return out


def tie(L, pos, nation, slots_of=None):
    """Two rows still match: the position, then the nationality (user, 2026-11-15)."""
    mine = L.get("slots") or set()
    theirs = slots_of(pos) if slots_of else pos_atoms(pos)
    score = 0
    if mine and theirs:
        mine_a = set().union(*[pos_atoms(x) for x in mine])
        theirs_a = theirs if slots_of is None else set().union(*[pos_atoms(x) for x in theirs])
        if mine_a & theirs_a:
            score += 2
        elif ("GK", "-") in mine_a and ("GK", "-") not in theirs_a or ("GK", "-") in theirs_a and ("GK", "-") not in mine_a:
            score -= 5
    nat = fold(L.get("nation"))
    if nat and nation:
        n2 = fold(nation)
        if n2 == nat or (len(n2) == 3 and nat.startswith(n2)):
            score += 1
    return score


def club_words(s):
    # 4+ letters: abbreviations (FCP, Est., Vit.) begin too many other clubs' words
    return [w for w in re.split(r"[\s.\-/()'#]+", plain(s)) if len(w) > 3 and w not in GENERIC and not w.isdigit()]


def num(s):
    try:
        return int(float(str(s).replace(",", ".")))
    except Exception:
        return None


def pa_ok(a, b, tol=10):
    """PA against PA: within tol, a negative PA standing for its range."""
    if a is None or b is None:
        return True
    if a > 0 and b > 0:
        return abs(a - b) <= tol
    ra, rb = (NEG.get(a) if a < 0 else None), (NEG.get(b) if b < 0 else None)
    if a < 0 and b < 0:
        return bool(ra and rb) and abs(ra[0] - rb[0]) <= tol
    p, r = (a, rb) if a > 0 else (b, ra)
    return bool(r) and r[0] - tol <= p <= r[1] + tol


def rule_name(got, fallback):
    """got: {Pcna, Pfna, Psna, Pfln} as the file last sets them."""
    if got.get("Pcna"):
        return got["Pcna"]
    if got.get("Pfna") or got.get("Psna"):
        return " ".join(got[k] for k in ("Pfna", "Psna") if got.get(k))
    return got.get("Pfln") or fallback


class Clubs:
    """Does a club written as text (Comparativo Team, a squad sheet) name club id cid?"""

    def __init__(self, namer, resolve):
        self.namer, self.resolve = namer, resolve
        self.pools = {}

    def pool(self, cid):
        if cid not in self.pools:
            e = self.namer.entry("team", cid) or {}
            self.pools[cid] = {w for n in [e.get("n")] + list(e.get("t") or []) if n for w in club_words(n)}
        return self.pools[cid]

    def same(self, text, nation, cid, family):
        if not cid or not text:
            return False
        rid = self.resolve(text, nation)
        if rid is not None and (rid == cid or family(rid, cid)):
            return True
        words, pool = club_words(text), self.pool(cid)
        # every distinctive word of the text begins one of the club's own words
        # (Naval 1o de Maio, SC Salgueiros): the index sometimes resolves such a
        # name to a namesake club
        return bool(words) and bool(pool) and all(any(p.startswith(w) for p in pool) for w in words)


def decide(legends, comp_rows, sheet_players, clubs, family, sheet_nation, aliases=None, sheet_slots=None):
    """legends: {uid: {name, club, ca, pa, dob, protected}} (players only).
    comp_rows: [(row number, name, team, league nation, CA, PA, position, country)].
    sheet_players: [{name, club, youth, sheet, ...}]."""
    aliases = aliases or {}
    by_name = {}
    for r in comp_rows:
        by_name.setdefault(norm(r[1]), []).append(r)
    sheet_by = {}
    for x in sheet_players:
        sheet_by.setdefault(norm(x["name"]), []).append(x)

    out, claims, taken = {}, {}, set()

    def at_club(L, text, nation):
        return any(clubs.same(text, nation, cl, family) for cl in (L["club"], L.get("loan")) if cl)

    # Comparativo rows, best name tier first across every legend, one row each
    cands = []
    for uid, L in legends.items():
        names = [L["name"]] + aliases.get(uid, [])
        for r in comp_rows:
            t = max(name_tier(n, r[1]) for n in names)
            if not t:
                continue
            ca, pa = num(r[4]), num(r[5])
            if L["ca"] is not None and ca is not None and abs(L["ca"] - ca) > 10:
                continue
            if not pa_ok(L["pa"], pa):
                continue
            if not at_club(L, r[2], r[3]):
                continue
            cands.append((-t, -tie(L, r[6], r[7]), abs((L["ca"] or 0) - (ca or 0)), uid, r))
    cands.sort(key=lambda x: (x[0], x[1], x[2]))
    for nt, _tb, _d, uid, r in cands:
        if uid in out:
            if out[uid]["row"] == r[0]:
                continue
            continue
        if r[0] in taken:
            claims.setdefault(r[0], []).append(uid)
            continue
        out[uid] = {"how": "row", "row": r[0], "row_name": r[1], "tier": -nt}
        taken.add(r[0])
        claims.setdefault(r[0], []).append(uid)

    for uid, L in legends.items():
        if uid in out:
            continue
        names = [L["name"]] + aliases.get(uid, [])
        found = []
        for x in sheet_players:
            t = max(name_tier(n, x["name"]) for n in names)
            if t and at_club(L, x["club"], sheet_nation(x)):
                tb = tie(L, x["pos"], x["nation"], sheet_slots)
                if t <= 2 and tb < 0:
                    continue        # a short name and a clashing position (GK vs outfield) is not him
                found.append((t, tb, x))
        found = [x for t, tb, x in sorted(found, key=lambda e: (-e[0], -e[1]))]
        senior = [x for x in found if not x["youth"]]
        if senior:
            out[uid] = {"how": "sheet", "sheet": "%s / %s: %s" % (senior[0]["sheet"], senior[0]["tab"], senior[0]["name"])}
            continue
        if found:
            young = L["dob"] is not None and tuple(L["dob"][::-1]) > YOUTH_BORN_AFTER
            if young:
                out[uid] = {"how": "youth", "sheet": "%s / %s: %s" % (found[0]["sheet"], found[0]["tab"], found[0]["name"])}
                continue
            why = "only in a youth tab (%s / %s: %s) and not 19 or younger" % (found[0]["sheet"], found[0]["tab"], found[0]["name"])
        else:
            why = "not in the Comparativo nor in any squad sheet at his club"
        if L["protected"]:
            out[uid] = {"how": "protected", "why": why}
        elif L.get("fm24"):
            out[uid] = {"how": "ask", "why": why}
        else:
            out[uid] = {"how": "removed", "why": why}
    # two legends on one row: the one whose CA is nearest keeps it, the others are
    # reported (the date of birth is the user's tie-breaker, the Comparativo has none)
    for row, us in claims.items():
        if len(us) > 1:
            for u in us:
                if out[u].get("row") == row:
                    out[u]["shared_row"] = [v for v in us if v != u]
    return out


def moved_back(legends, comp_rows, out, taken_rows):
    """A player FM27's database moved whom the file never re-clubs (Ricardo Velho,
    Farense -> Aris; Trincao, Sporting -> Al Ahli): his Comparativo row at the old
    club - exact name, accents aside at most, CA and PA each within 10 - is his,
    and his club goes back to that team (user, 2026-11-15). Returns
    {uid: (row number, team, league nation)} for the legends it settles."""
    got = {}
    for uid, L in legends.items():
        v = out.get(uid) or {}
        if v.get("how") not in ("sheet", "youth", "protected") or L.get("file_club"):
            continue
        hits = []
        for r in comp_rows:
            if r[0] in taken_rows or name_tier(L["name"], r[1]) < 3:
                continue
            ca, pa = num(r[4]), num(r[5])
            if L["ca"] is not None and ca is not None and abs(L["ca"] - ca) > 10:
                continue
            if not pa_ok(L["pa"], pa):
                continue
            hits.append(r)
        if len(hits) == 1:
            got[uid] = (hits[0][0], hits[0][2], hits[0][3])
            taken_rows.add(hits[0][0])
    return got


STAFF_POS = {"t", "adj", "adj.", "pres", "pres.", "presidente", "treinador", "tr. adj.", "ta"}
HEAD_COACH = 5      # PCJO, the contract job: 1 chairman, 2 director, 4 director of football, 5 manager, 6 assistant


def decide_staff(staff, rows, sheet_players, clubs, family, sheet_nation):
    """The user's rules for staff (2026-11-15), the players' rules otherwise:
    a Staff tab row with his name at his club, CA and PA each within 10 (staff
    ability, Ncra / Npta) is his; no row: his name at his club in any squad sheet
    (staff are listed there as T, Adj., Pres.) keeps him; a record edited in FM26/27
    is kept anyway; anyone else is removed - FM24 ones too (user: Bernardino
    Pedroto, Miguel Leal, Raul Jose, Arnaldo Teixeira, Fernando Ferreira).
    Only head coaches get a NEW row. staff: {uid: {name, club, ca, pa, job,
    protected}}; rows: [(row number, name, role, CA, PA, team)]."""
    cands = []
    for uid, s in staff.items():
        for n, name, _role, ca, pa, team in rows:
            t = name_tier(s["name"], name)
            if not t or not clubs.same(team, None, s["club"], family):
                continue
            ca, pa = num(ca), num(pa)
            if s["ca"] is not None and ca is not None and abs(s["ca"] - ca) > 10:
                continue
            if s["pa"] is not None and pa is not None and abs(s["pa"] - pa) > 10:
                continue
            cands.append((-t, abs((s["ca"] or 0) - (ca or 0)), uid, n))
    cands.sort()
    out, taken = {}, set()
    for _t, _d, uid, n in cands:
        if uid in out or n in taken:
            continue
        out[uid] = {"how": "row", "row": n}
        taken.add(n)
    for uid, s in staff.items():
        if uid in out:
            continue
        hits = []
        for x in sheet_players:
            t = name_tier(s["name"], x["name"])
            as_staff = (x.get("pos") or "").strip().lower() in STAFF_POS
            # a one-word short name is a staff name only where the sheet lists him as
            # staff: Andre Villas-Boas is not FC Porto's midfielder "Andre"
            if t in (1, 2) and not as_staff and min(len(fold(s["name"]).split()), len(fold(x["name"]).split())) < 2:
                continue
            if t and clubs.same(x["club"], sheet_nation(x), s["club"], family):
                hits.append((-t, not as_staff, x))
        hits.sort(key=lambda h: (h[0], h[1]))
        if hits:
            x = hits[0][2]
            pos = (x.get("pos") or "").strip()
            out[uid] = {"how": "sheet", "sheet": "%s / %s: %s (%s)" % (x["sheet"], x["tab"], x["name"], pos),
                        "sheet_pos": pos, "sheet_team": x["club"],
                        # listed as a player: a player by hand (user, 2026-11-15: Rabiola)
                        "sheet_as_player": pos.lower() not in STAFF_POS}
        elif s["protected"]:
            out[uid] = {"how": "protected", "why": "not in the Staff tab nor in any squad sheet at his club"}
        else:
            out[uid] = {"how": "removed", "why": "not in the Staff tab nor in any squad sheet at his club"}
    for uid, v in out.items():
        s = staff[uid]
        coach = s["job"] == HEAD_COACH or (s["job"] is None and (v.get("sheet_pos") or "").upper() == "T")
        v["append"] = v["how"] in ("sheet", "protected") and coach
    return out
