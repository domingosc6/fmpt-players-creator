"""Builds one created-player changeset from a resolved Profile.

Reuses (imports, never copies):
  clean_import.emit_rows / new_row / blank_row   - the Plhs grid
  rebuild_lost_records.addr_row / type_change / free_ids
  name_rebuilt_records.string_op / nation_op / split_name
  repair_type_change.hg_ops / home_grown / nation_ids / age_on_1_july
  convert_edition.sync_contract_dates / CALENDAR_YEAR_NATIONS
  fm_names.Names
  probe_editor_replay.replay / grid   - verification only
"""
import json
import os
import random
import re
import sys
import zlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import clean_import as ci
import convert_edition as c
import fm_names
import name_rebuilt_records as nrr
import rebuild_lost_records as rlr
import repair_type_change as rtc

import fm26_install
import model

BUILD = "3733"
NULL_DATE_EL_ATTRS = dict(day="1", month="1", year="1900", time="0")


# ------------------------------------------------------------- lookups ------

def search(filt, by="", q="*", n=10):
    url = (fm_names.HOST + "/collections/detailed_game_items/documents/search?q=%s&query_by=%s"
           "&filter_by=%s&per_page=%d&x-typesense-api-key=%s"
           % (urllib.parse.quote(q), by, urllib.parse.quote(filt), n, fm_names.KEY))
    req = urllib.request.Request(url, headers={"User-Agent": "fmpt-legends/1.0"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30)).get("hits") or []
    except Exception:
        return []


CLUB_CACHE_PATH = os.path.join(HERE, "cache", "club_lookup.json")


def _club_cache():
    if os.path.exists(CLUB_CACHE_PATH):
        return json.load(open(CLUB_CACHE_PATH))
    return {}


def _club_cache_save(cache):
    json.dump(cache, open(CLUB_CACHE_PATH, "w"), indent=0, sort_keys=True, ensure_ascii=False)


CLUB_PREFIXES = {"ss", "ssd", "ac", "acf", "us", "usd", "as", "asd", "fc", "cf",
                 "ud", "uc", "u.s.", "a.c.", "a.s.", "s.s.", "s.s.d.", "a.c.f.",
                 "sc", "cd", "gd", "sl", "ad", "cs", "ca", "sd", "rcd", "rc", "ue"}


def _squash(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in s.lower() if ch.isalnum() and not unicodedata.combining(ch))


def same_club_name(a, b):
    """One club under two sources' names: equal once squashed, or one held in
    the other ("Barco" in "SC Barco"; four letters at least)."""
    a, b = _squash(a), _squash(b)
    return a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a))


def _words(d):
    """A candidate's name and aliases as whole squashed words: "milan" must
    not match inside "milano"."""
    out = set()
    for t in [d.get("name")] + list(d.get("search_terms") or []):
        for w in re.split(r"[\s\-./'()]+", t or ""):
            if _squash(w):
                out.add(_squash(w))
        out.add(_squash(t))
    return out


def _core(name):
    """Drop a leading club-type abbreviation ("SS Cavese" -> "Cavese",
    "U.S.Pecciolese Calcio" -> "Pecciolese Calcio", no space needed after the
    dots) - the search index ranks by token overlap and a bare "SS"/"AC" pulls
    in clubs from anywhere the abbreviation also fits (Cavese, Fiorentina)."""
    import re
    m = re.match(r"^(?:[A-Za-z]\.)+\s*", name)
    rest = name[m.end():] if m and _squash(m.group(0)) in CLUB_PREFIXES else name
    parts = rest.split()
    while parts and parts[0].lower().strip(".") in CLUB_PREFIXES:
        parts = parts[1:]
    return " ".join(parts) or name


NATION_ALIAS = {"Netherlands": "The Netherlands", "Holland": "The Netherlands",
                "Turkey": "Türkiye", "USA": "United States", "South Korea": "Korea Republic",
                "Ireland": "Republic of Ireland", "China": "China PR", "Czech Republic": "Czechia",
                "Ivory Coast": "Côte d'Ivoire", "Cote d'Ivoire": "Côte d'Ivoire",
                "Congo DR": "DR Congo", "Bosnia-Herzegovina": "Bosnia and Herzegovina"}
GENERIC_TOKENS = {"club", "clube", "futebol", "football", "calcio", "sport", "sporting",
                  "portugal", "estrela",
                  "associacao", "associazione", "sociedade", "desportiva", "desportivo",
                  "recreativo", "recreativa", "grupo", "uniao", "gremio", "deportivo",
                  "deportiva", "sociedad", "olympique", "athletic", "atletico",
                  "real", "union", "united", "city", "the", "and", "de", "do", "da", "dos"}


# a club-type abbreviation as the words FM's full names use ("Vitória FC" is
# Vitória Futebol Clube, Setúbal; "Vitória SC" is Vitória Sport Club, Guimarães)
ABBREVIATIONS = {"fc": "Futebol Clube", "sc": "Sporting Clube Sport Club", "cd": "Clube Desportivo",
                 "est": "Estrela", "cp": "Clube de Portugal",
                 "gd": "Grupo Desportivo", "ud": "União Desportiva", "sl": "Sport Lisboa",
                 "ad": "Associação Desportiva", "ac": "Atlético Clube", "cf": "Clube de Futebol",
                 "sd": "Sociedade Desportiva", "ca": "Clube Atlético", "ec": "Esporte Clube",
                 "se": "Sociedade Esportiva", "cr": "Clube de Regatas", "oaf": "Coimbra"}


def expand(name):
    return " ".join(ABBREVIATIONS.get(_squash(w), w) for w in name.split())


def fm_nation(name):
    return NATION_ALIAS.get(name, name) if name else None


def resolve_club(name, nation, cache, prefer=None):
    """Best team match for `name` in `nation` (None = anywhere), from the
    fmref search index. Not server-side filterable by nation (filter_by on the
    nested field 400s), so hits are fetched by name/alias relevance and
    filtered client-side; a hit with no nation on record (index gap - Brescia
    Calcio 1113 carries none) stays a candidate.

    Tried as both the full name and its "core" (prefix stripped): a bare
    abbreviation token ("SS", "AC") pulls in clubs from anywhere it fits. Each
    candidate scores the query's words found in its name and aliases, a
    distinctive word counting double ("Benfica" over "Lisboa", "Sporting CP
    Lisboa" must not land on Sporting Braga); ties go to the lowest fm_id, an
    established entry rather than an auto-numbered regional one - after the
    club's reputation, so a bare "Milan" is A.C. Milan (8350) and not an
    extinct EC Milan (1). None when no candidate shares a word."""
    nation, prefer = fm_nation(nation), fm_nation(prefer)
    key = "%s|%s|%s" % (name, nation, prefer)
    if key in cache:
        return cache[key]
    core = _core(name)
    hits = {}
    bare_words = " ".join(w for w in name.split() if _squash(w) not in ABBREVIATIONS)
    state = re.search(r"(?:-|\()([A-Z]{2})\)?$", name.strip())
    # "América-RN" is indexed as "América (RN)"
    spelled = re.sub(r"-([A-Z]{2})$", r" (\1)", name.strip()) if state else name
    for q in dict.fromkeys([name, spelled, core, expand(name), bare_words]):
        if not q.strip():
            continue
        for h in search("type_id:=team", by="name,search_terms", q=q, n=50):
            d = h["document"]
            if d.get("fm_id", "").isdigit():
                hits[int(d["fm_id"])] = d
    # the words a candidate is scored on: the name with its abbreviations
    # spelled out, so "FC" tells Futebol Clube from Sport Club
    words = [_squash(w) for w in re.split(r"[\s\-./]+", expand(name)) if len(_squash(w)) >= 3]
    # a Brazilian state suffix decides between namesakes: "América-RN" is
    # América (RN), not America (RJ)
    if state:
        words.append(state.group(1).lower())

    def score(d):
        text = _words(d)
        # a distinctive word outweighs any number of generic ones ("Covilhã"
        # decides; "Sporting Clube" only breaks a tie)
        return sum((1 if w in GENERIC_TOKENS else 10) for w in words if w in text)
    pool = [d for d in hits.values() if d.get("gender") != "womens"
            and (nation is None or (d.get("nation") or {}).get("name") in (nation, None))]
    distinct = [w for w in words if w not in GENERIC_TOKENS]
    text_of = _words
    pool = [d for d in pool if score(d) > 0]
    # a candidate sharing a distinctive word beats one sharing only "Clube" or
    # "Sporting"; with none of those the generic match stands, marked weak
    strong = [d for d in pool if any(w in text_of(d) for w in distinct)]
    pool = strong or pool

    def reserve(d):
        """A B side, reserves or youth team: only when the query names one."""
        n = " " + (d.get("name") or "") + " "
        return bool(re.search(r" (B|II|III|C|[2-9]|U\d\d|Reserves|Juniors|Youth|Sub-\d\d) ", n)) \
            and not re.search(r" (B|II|III|[2-9]|U\d\d)$", name.strip())
    result = None
    if pool:
        best = max(pool, key=lambda d: (not reserve(d), score(d),
                                        (d.get("nation") or {}).get("name") in {nation, prefer} - {None},
                                        d.get("reputation") or 0, -int(d["fm_id"])))
        text = _words(best)
        # a match that leaves a distinctive word of the query unexplained is
        # reported for a look ("Olympique de Marselha" -> some other Olympique)
        result = {"id": int(best["fm_id"]), "name": best["name"],
                  "weak": any(w not in text for w in distinct)}
    cache[key] = result
    return result


def person_name(profile, namer=None):
    """Split first/last/common/full from the sources - the record has no FM
    search-index entry of its own (created player), so this comes straight
    from the site data, not `split_name` (that reads an existing index doc)."""
    return profile.first, profile.last, profile.common, profile.full


# ------------------------------------------------------------- ids ---------

FM26_DIR = os.path.join(os.path.dirname(HERE), "FM 26 XML Files")
PEOPLE_DB = os.path.join(HERE, "cache", "fm26_basic_people_db.bin")
FM26_PEOPLE_DAT = os.path.join(fm26_install.db_dir(), "basic_people_db.dat")
UID_RE = re.compile(r'id="db_unique_id" value="(\d+)"')


def seed_id_ledger(path):
    """Every created id any FM26 file uses - final_xmls, extracts, merged,
    probes, archives - so a new person never shares a word with one the user
    may import next to it (the first probe collided with the Portugal rebuilt
    records, which live in extracts/). Ids the creator minted are kept."""
    used_hi, used_lo = set(), set()
    for root, _, files in os.walk(FM26_DIR):
        for f in files:
            if not f.endswith(".xml"):
                continue
            with open(os.path.join(root, f), encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    for m in UID_RE.finditer(line):
                        n = int(m.group(1))
                        if n >= 2 ** 32:
                            used_hi.add(n >> 32)
                            used_lo.add(n & 0xFFFFFFFF)
    data = json.load(open(path)) if os.path.exists(path) else {}
    # on a computer without the FM 26 XML Files folder, the ids seen on the
    # one that has it stay in the ledger (carried in ids.json)
    used_hi.update(data.get("used_hi", []))
    used_lo.update(data.get("used_lo", []))
    for u in data.get("created", []):
        used_hi.add(int(u) >> 32)
        used_lo.add(int(u) & 0xFFFFFFFF)
    data["used_hi"], data["used_lo"] = sorted(used_hi), sorted(used_lo)
    # LF on Windows too: ids.json is shared through git, byte for byte
    json.dump(data, open(path, "w", newline="\n"), indent=0, sort_keys=True)


def people_db():
    """FM26's person table, decompressed once; the high word of a new id must
    not name a real person."""
    if not os.path.exists(PEOPLE_DB):
        raw = open(FM26_PEOPLE_DAT, "rb").read()[12:]
        data = fm26_install.decompress(raw)  # before opening, or a failure leaves an empty cache
        open(PEOPLE_DB, "wb").write(data)
    return open(PEOPLE_DB, "rb").read()


def load_id_ledger(path):
    data = json.load(open(path))
    return set(data.get("used_hi", [])), set(data.get("used_lo", [])), data


def save_id_ledger(path, used_hi, used_lo, data, minted):
    data["used_hi"] = sorted(used_hi)
    data["used_lo"] = sorted(used_lo)
    data.setdefault("created", []).extend(minted)
    json.dump(data, open(path, "w", newline="\n"), indent=0, sort_keys=True)


def mint_id(ids_path, key):
    """The player's created id: the one already issued to `key`, else a fresh
    one clear of every FM26 file and of FM26's own people. A rerun keeps the
    id, so a re-import replaces the person instead of adding a second one."""
    seed_id_ledger(ids_path)
    used_hi, used_lo, data = load_id_ledger(ids_path)
    by_key = data.setdefault("by_key", {})
    if key in by_key:
        return int(by_key[key])
    uid, = rlr.free_ids(1, used_hi, used_lo, people_db(), random.Random(zlib.crc32(key.encode())))
    by_key[key] = str(uid)
    save_id_ledger(ids_path, used_hi, used_lo, data, [str(uid)])
    return uid


# ------------------------------------------------------------- shapes ------

def team_ref(dbid):
    r = ET.Element("record")
    ET.SubElement(r, "integer", id="Ttea", value=str(dbid))
    return r


def comp_ref(dbid):
    r = ET.Element("record")
    ET.SubElement(r, "integer", id="competition", value=str(dbid))
    return r


def scalar_op(uid, prop, value_el, rng, odvl_el=None, extra=None):
    rec = ET.Element("record")
    ET.SubElement(rec, "integer", id="database_table_type", value="1")
    ET.SubElement(rec, "large", id="db_unique_id", value=str(uid))
    ET.SubElement(rec, "unsigned", id="property", value=str(c.prop_id(prop)))
    value_el.set("id", "new_value")
    rec.append(value_el)
    ET.SubElement(rec, "integer", id="version", value=BUILD)
    ET.SubElement(rec, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    if odvl_el is not None:
        odvl_el.set("id", "odvl")
        rec.append(odvl_el)
    if extra:
        for tag, attrs in extra:
            ET.SubElement(rec, tag, **attrs)
    return rec


def int_op(uid, prop, value, rng, odvl=0):
    return scalar_op(uid, prop, ET.Element("integer", value=str(value)), rng,
                     ET.Element("integer", value=str(odvl)))


# the sheet's CA, PA, CR, HR and WR columns (user, 2026-10-13): written only
# when the cell holds a number. The editor's scales, as the Legends files
# carry them: CA 0-200, PA 0-200 or a negative range (-1 to -200), the three
# reputations 0-200
RATINGS = (("ca", "PCAB", 0, 200), ("pa", "PPAB", -200, 200), ("cr", "PCRP", 0, 200),
           ("hr", "PHRP", 0, 200), ("wr", "PWRP", 0, 200))


def rating_ops(uid, ratings, rng, flags):
    """(ops, written) for the sheet's ratings; an empty cell writes nothing, a
    value off the scale is flagged and not written."""
    ops, written = [], []
    for key, prop, lo, hi in RATINGS:
        v = (ratings or {}).get(key, "")
        if not v:
            continue
        if not re.fullmatch(r"-?\d+", v) or not lo <= int(v) <= hi:
            flags.append("%s %r is not a number from %d to %d - not written." % (key.upper(), v, lo, hi))
            continue
        ops.append(int_op(uid, prop, int(v), rng))
        written.append("%s %s" % (key.upper(), v))
    return ops, written


def date_op(uid, prop, d, rng, odvl=(1, 1, 1900)):
    v = ET.Element("date", day=str(d[0]), month=str(d[1]), year=str(d[2]), time="0")
    o = ET.Element("date", day=str(odvl[0]), month=str(odvl[1]), year=str(odvl[2]), time="0")
    return scalar_op(uid, prop, v, rng, o)


def ref_op(uid, prop, ref_el, key, rng, odvl_is_null=True):
    """A single-child reference (`Pcti`, `Pnti`): <record id="new_value"><...
    key.../></record>, PLAN reference shape - no VAL_ID wrapper, that is only
    for grid cells (`emit_rows`)."""
    odvl = ET.Element("null") if odvl_is_null else None
    return scalar_op(uid, prop, ref_el, rng, odvl)


PNPH_PROP = "Pnph"
ROW_ID = "1853322860"
OLVL_ID = "1869379180"
VAL_ID = "1986096245"
TEAM_COL = "1952801133"
JOIN_COL = "1785686382"
LEFT_COL = "1818584692"


def pnph_wrap(uid, new_value, rng):
    return grid_wrap(uid, PNPH_PROP, new_value, rng)


def grid_wrap(uid, prop, new_value, rng):
    rec = ET.Element("record")
    ET.SubElement(rec, "integer", id="database_table_type", value="1")
    ET.SubElement(rec, "large", id="db_unique_id", value=str(uid))
    ET.SubElement(rec, "unsigned", id="property", value=str(c.prop_id(prop)))
    rec.append(new_value)
    ET.SubElement(rec, "integer", id="version", value=BUILD)
    ET.SubElement(rec, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    return rec


def _date(d):
    return dict(day=str(d[0]), month=str(d[1]), year=str(d[2]), time="0")


def pnph_olvl(team_dbid, join, left):
    o = ET.Element("record", id="olvl")
    ET.SubElement(o, "unsigned", id="id", value=OLVL_ID)
    if team_dbid is None:
        ET.SubElement(o, "null", id="team")
    else:
        t = ET.SubElement(o, "record", id="team")
        ET.SubElement(t, "integer", id="Ttea", value=str(team_dbid))
    ET.SubElement(o, "date", id="join", **_date(join or (1, 1, 1900)))
    ET.SubElement(o, "date", id="left", **_date(left or (1, 1, 1900)))
    ET.SubElement(o, "integer", id="tjob", value="11")
    return o


def emit_pnph(uid, spells_resolved, rng, clear_first=True):
    """One insert + team + join + (left if closed) per spell, in join order -
    the shape read off `FM 26 XML Files/final_xmls/.../Italy...xml` (current
    build) and the reference Portugal extract. `spells_resolved`: list of
    dict(club=DBID, join=(d,m,y), left=(d,m,y) or None)."""
    ops = []
    if clear_first:
        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=ROW_ID)
        ET.SubElement(nv, "integer", id="lsop", value="3")
        ops.append(pnph_wrap(uid, nv, rng))
    for sp in sorted(spells_resolved, key=lambda s: s["join"][::-1]):
        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=ROW_ID)
        ET.SubElement(nv, "integer", id="lsop", value="0")
        ops.append(pnph_wrap(uid, nv, rng))
        cur_team, cur_join, cur_left = None, None, None

        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=TEAM_COL)
        v = ET.SubElement(nv, "record", id="value")
        ET.SubElement(v, "unsigned", id="id", value=VAL_ID)
        ET.SubElement(v, "integer", id="Ttea", value=str(sp["club"]))
        ET.SubElement(nv, "integer", id="lsop", value="1")
        nv.append(pnph_olvl(cur_team, cur_join, cur_left))
        ops.append(pnph_wrap(uid, nv, rng))
        cur_team = sp["club"]

        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=JOIN_COL)
        ET.SubElement(nv, "date", id="value", **_date(sp["join"]))
        ET.SubElement(nv, "integer", id="lsop", value="1")
        nv.append(pnph_olvl(cur_team, cur_join, cur_left))
        ops.append(pnph_wrap(uid, nv, rng))
        cur_join = sp["join"]

        if sp["left"] is not None:
            nv = ET.Element("record", id="new_value")
            ET.SubElement(nv, "unsigned", id="id", value=LEFT_COL)
            ET.SubElement(nv, "date", id="value", **_date(sp["left"]))
            ET.SubElement(nv, "integer", id="lsop", value="1")
            nv.append(pnph_olvl(cur_team, cur_join, cur_left))
            ops.append(pnph_wrap(uid, nv, rng))
    return ops


# ------------------------------------------------------------- days --------

DAYS_TEAM_COL = "1416914273"     # Pdcn "Ttea": a club, or a nation's DBID
DAYS_COL = "1684109683"          # Pdcn "days"


def days_at(spells, until, nation_of):
    """({club: days}, {nation: days}, unknown clubs) as of `until`, the target
    season's first day. Read off FM's own values (Gudjohnsen, 2026-10-08): a
    loan's days go to the loan club and are taken OUT of the parent spell
    (Monaco 365 - Tottenham 123 = 242), and a nation counts the days he spent
    at its clubs, the same carve-out included (France 242). His own nation
    counts too. Days are a plain date difference."""
    import datetime as dt
    D = lambda d: dt.date(d[2], d[1], d[0])
    end = D(until)
    span = lambda s: (D(s["join"]), min(D(s["left"]) if s["left"] else end, end))
    clubs, nations, unknown = {}, {}, []
    for s in spells:
        a, b = span(s)
        days = max(0, (b - a).days)
        if not s.get("loan"):
            for l in spells:
                if l.get("loan") and l is not s:
                    la, lb = span(l)
                    days -= max(0, (min(b, lb) - max(a, la)).days)
        if days <= 0:
            continue
        clubs[s["club"]] = clubs.get(s["club"], 0) + days
        nat = nation_of(s["club"])
        if nat is None:
            unknown.append(s["club"])
        else:
            nations[nat] = nations.get(nat, 0) + days
    return clubs, nations, unknown


def _days_olvl(team, days):
    o = ET.Element("record", id="olvl")
    ET.SubElement(o, "unsigned", id="id", value=OLVL_ID)
    if team is None:
        ET.SubElement(o, "null", id="Ttea")
    else:
        t = ET.SubElement(o, "record", id="Ttea")
        ET.SubElement(t, "unsigned", id="id", value=DAYS_TEAM_COL)
        ET.SubElement(t, "integer", id="Ttea", value=str(team))
    ET.SubElement(o, "integer", id="days", value=str(days))
    for b in ("0t21", "d152"):
        ET.SubElement(o, "boolean", id=b, value="false")
    ET.SubElement(o, "integer", id="mnag", value="0")
    ET.SubElement(o, "integer", id="mxag", value="0")
    for b in ("bfat", "etto"):
        ET.SubElement(o, "boolean", id=b, value="false")
    return o


def emit_pdcn(uid, entries, rng):
    """Clear the days-at-club/nation grid, then one row per (team, days): the
    author's insert shape - a fresh row reads days 1, every flag false."""
    ops = []
    nv = ET.Element("record", id="new_value")
    ET.SubElement(nv, "unsigned", id="id", value=ROW_ID)
    ET.SubElement(nv, "integer", id="lsop", value="3")
    ops.append(grid_wrap(uid, "Pdcn", nv, rng))
    for team, days in entries:
        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=ROW_ID)
        ET.SubElement(nv, "integer", id="lsop", value="0")
        ops.append(grid_wrap(uid, "Pdcn", nv, rng))

        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=DAYS_TEAM_COL)
        v = ET.SubElement(nv, "record", id="value")
        ET.SubElement(v, "unsigned", id="id", value=VAL_ID)
        ET.SubElement(v, "integer", id="Ttea", value=str(team))
        ET.SubElement(nv, "integer", id="lsop", value="1")
        nv.append(_days_olvl(None, 1))
        ops.append(grid_wrap(uid, "Pdcn", nv, rng))

        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=DAYS_COL)
        ET.SubElement(nv, "integer", id="value", value=str(days))
        ET.SubElement(nv, "integer", id="lsop", value="1")
        nv.append(_days_olvl(team, 1))
        ops.append(grid_wrap(uid, "Pdcn", nv, rng))
    return ops


def _nation_from_leagues(club):
    """A club the index files under no nation (Pauleta's 1768): the nation of
    the competition it played in most recently, from FM26's league history."""
    import fm26_leagues
    fm26_leagues.division(club, 2000)            # loads the cache
    rows = sorted(fm26_leagues._DATA.get(str(club), []), key=lambda r: -r[0])
    for year, comp, _ in rows[:3]:
        for h in search("fm_id:=%d && type_id:=competition" % comp, by="name", q="*", n=1):
            nat = (h["document"].get("nation") or {}).get("name")
            if nat:
                return nat
    return None


_NAMES = None
_CLUB_NATION = {}


def _names():
    """One offline name index for the whole run - loading it is an 8 MB read."""
    global _NAMES
    if _NAMES is None:
        _NAMES = fm_names.Names(offline=True)
    return _NAMES


def club_nation(cid):
    """A club's nation name: the index's, else that of its latest league.
    Asked once per club and date, so it is remembered."""
    if cid not in _CLUB_NATION:
        _CLUB_NATION[cid] = _names().nation(cid) or _nation_from_leagues(cid)
    return _CLUB_NATION[cid]


def is_calendar_club(cid):
    return fm_nation(club_nation(cid)) in c.CALENDAR_YEAR_NATIONS if isinstance(cid, int) else False


def nation_resolver():
    """club DBID -> its nation's DBID, or None."""
    namer = fm_names.Names(offline=False)
    cache = {}

    def of(club):
        name = namer.nation(club) or _nation_from_leagues(club)
        if not name:
            return None
        if name not in cache:
            cache[name] = rtc.nation_ids([name]).get(name)
        return cache[name]
    return of


def intl_retirement_ops(uid, rng):
    """Undo an international retirement: the date nulled, the flag off - the
    author's own pair on adapted retired players. The debut and first-goal
    dates go too (they would sit after the shifted prime); their opponents
    stay (user, 2026-10-08)."""
    return [scalar_op(uid, "Pird", ET.Element("null"), rng),
            scalar_op(uid, "Pidd", ET.Element("null"), rng),
            scalar_op(uid, "Pigd", ET.Element("null"), rng),
            # no old value: the editor fails the change when the flag is
            # already off (user, 2026-10-22: Serginho Silva, shown there as
            # "rolling contract" Yes -> No)
            scalar_op(uid, "Pirc", ET.Element("boolean", value="false"), rng)]


RET_DATE_COL = "1684108389"      # "date", the retirements grid's date column
OLVL_ID = "1869379180"           # "olvl"


def retirement_ops(uid, rng, date=None):
    """The retirements grid (PErt): a Clear, and with `date` one entry on that
    day - the shape the Legends files carry (insert a row, then its date, with
    the empty row as the old value: type 1, date 1/1/1900)."""
    nv = ET.Element("record", id="new_value")
    ET.SubElement(nv, "unsigned", id="id", value=ROW_ID)
    ET.SubElement(nv, "integer", id="lsop", value="3")
    ops = [grid_wrap(uid, "PErt", nv, rng)]
    if date:
        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=ROW_ID)
        ET.SubElement(nv, "integer", id="lsop", value="0")
        ops.append(grid_wrap(uid, "PErt", nv, rng))
        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=RET_DATE_COL)
        ET.SubElement(nv, "date", id="value", **_date(date))
        ET.SubElement(nv, "integer", id="lsop", value="1")
        olvl = ET.SubElement(nv, "record", id="olvl")
        ET.SubElement(olvl, "unsigned", id="id", value=OLVL_ID)
        ET.SubElement(olvl, "integer", id="type", value="1")
        ET.SubElement(olvl, "date", id="date", day="1", month="1", year="1900", time="0")
        ops.append(grid_wrap(uid, "PErt", nv, rng))
    return ops


def past_transfers_clear(uid, rng):
    """Clear the past transfers grid (PPsT) - the op as the editor saves it
    (user's teste.xml, 2026-10-22): lsop 3 and no row id."""
    nv = ET.Element("record", id="new_value")
    ET.SubElement(nv, "integer", id="lsop", value="3")
    return grid_wrap(uid, "PPsT", nv, rng)


# ------------------------------------------------------------- pipeline ----

NFT_LEVEL_TO_ROMAN = {"I": "I", "II": "II", "III": "III", "IV": "IV", "V": "V"}


def season_start_year(season_str):
    return int(season_str.split("/")[0])


def name_match(a, b):
    a, b = (a or "").lower(), (b or "").lower()
    return a and b and (a in b or b in a)


# a youth season counts from the one he turns 15 in: 14 on 1 July (user,
# 2026-10-08); younger seasons are dropped
YOUTH_MIN_AGE = 14


def gather_profile(name, nation, prime_season, nft_html, box, zz_data=None, calendar_of=None):
    """NFT, when the player has one, is primary for every season row (club,
    country, apps, goals, level); Wikipedia (`box`, any language, see
    `wikipedia.infobox_any`) adds youth clubs, loan markers and names, and the
    two are cross-checked. With Wikipedia alone the rows come from its stays:
    a stay's apps and goals are a TOTAL, so they are written only for a
    one-season stay and left blank otherwise (flagged)."""
    import sources.nft as nft
    import sources.wikipedia as wiki

    p = model.Profile(name)
    p.nation = nation
    box = box or {"dob": None, "nome": None, "cognome": None, "youth": [], "senior": [],
                  "full": None, "birthplace": None}
    zz_data = zz_data or {}
    p.dob = (nft.dob(nft_html) if nft_html else None) or box.get("dob") or zz_data.get("dob")
    p.position = nft.position(nft_html) if nft_html else (zz_data.get("position"), None)
    # every source's spelling, in this order: Wikipedia writes the English
    # name (Bucharest), FM26 and NFT the local one (Bucuresti) - city_id
    # takes the first FM26 knows
    p.birthplaces = list(dict.fromkeys(
        b for b in (box.get("birthplace"), nft.birthplace(nft_html) if nft_html else None,
                    zz_data.get("birthplace")) if b))
    p.birthplace = p.birthplaces[0] if p.birthplaces else None
    full = box.get("full") or zz_data.get("full")
    p.birth_country = box.get("birth_country") or zz_data.get("birth_country")
    p.height = ((nft.height(nft_html) if nft_html else None) or box.get("height")
                or zz_data.get("height"))
    if box.get("nome") and box.get("cognome"):
        p.first, p.last = box["nome"], box["cognome"]
    elif full and len(full.split()) > 1:
        p.first, p.last = full.split()[0], full.split()[-1]
    else:
        parts = name.split()
        p.first, p.last = parts[0], " ".join(parts[1:]) or parts[0]
    # common and full names only where they differ from first + last; the
    # editor builds the display name itself
    plain = "%s %s" % (p.first, p.last)
    p.common = name if name != plain else None
    p.full = full if full and full != plain else None

    def bare(years):
        return not re.search(r"\d{4}\s*[-\u2013\u2014]", years)

    is_cal = calendar_of or (lambda club, nat: False)

    def stay_years(years, club, nat):
        """A Wikipedia stay as season start years. European "2008-2012" is four
        seasons, 2008/09-2011/12; a calendar-year club's is every year 2008 to
        2012 inclusive (user, 2026-10-08)."""
        if not is_cal(club, nat):
            return wiki.season_years(years)
        m = re.match(r"\s*(\d{4})\s*(?:[-\u2013\u2014]\s*(\d{4}))?", years)
        if not m:
            return []
        return list(range(int(m.group(1)), int(m.group(2) or m.group(1)) + 1))

    # wiki senior rows -> (year, club, loan) index, for the onln flag. A
    # single-year wiki row ("|2002|-> Verona|13 (0)") for a mid-season loan
    # names the CALENDAR year the move happened in - the season's second half,
    # NFT's season-start-year + 1 (Dainelli: wiki "1999" Cavese and "2002"
    # Verona both land on NFT's 1998/99 and 2001/02). A ranged row ("1996-1998")
    # already uses the season-start convention NFT does, so only the bare,
    # single-year form gets the alias.
    wiki_senior = []
    for years, club, loan, stats, _nat in box["senior"]:
        for y in wiki.season_years(years):
            wiki_senior.append((y, club, loan))
            if bare(years):
                wiki_senior.append((y - 1, club, loan))
    wiki_youth_years = []
    for years, club, loan, stats, nat in box["youth"]:
        for y in stay_years(years, club, nat):
            wiki_youth_years.append((y, club, nat))

    rows = []
    if nft_html:
        by_season = {}
        for r in nft.clubs(nft_html):           # newest first, as the page shows it
            y = season_start_year(r["season"])
            if y >= prime_season:
                continue                        # prime season and later: dropped
            by_season.setdefault(y, []).append(r)
        for y in sorted(by_season):
            season_rows = list(reversed(by_season[y]))   # chronological within the season
            n = len(season_rows)
            for i, r in enumerate(season_rows):
                yror = (i + 1) if n > 1 else 0
                loan = any(name_match(r["club"], wc) and wy == y and wl
                           for wy, wc, wl in wiki_senior)
                flag = None
                age = rtc.age_on_1_july(p.dob, y) if p.dob else None
                if any(wy == y for wy, wc, wn in wiki_youth_years) and r["apps"] == 0:
                    if age is not None and age <= 18:
                        # a 0-app senior row in a season Wikipedia files under his
                        # youth career, at youth age: he was in the youth team
                        # (Dainelli, Empoli 1997/98). Blank, ticked, no division.
                        rows.append(model.Row(y, r["club"], apps=None, goals=None, yror=yror,
                                              onln=loan, ytht=True, nation=r["nation"]))
                        continue
                    flag = ("Wikipedia lists %d/%02d in his youth career; NFT carries a senior "
                            "row (%s, 0 apps) and he was %s on 1 July, too old for the youth "
                            "tick - kept as a 0-app senior season." % (y, (y + 1) % 100, r["club"], age))
                rows.append(model.Row(y, r["club"], apps=r["apps"], goals=r["goals"],
                                      level=r["level"], yror=yror, onln=loan, flag=flag,
                                      nation=r["nation"]))
    elif zz_data.get("rows"):
        # zerozero: one row per season and club, newest first, with no
        # division and no country. "-" is a season he was there with no
        # figures (blank, not 0); a "[Jun.A S19]" team is his youth side.
        by_season = {}
        for r in zz_data["rows"]:
            y = season_start_year(r["season"])
            if y < prime_season:
                by_season.setdefault(y, []).append(r)
        for y in sorted(by_season):
            season_rows = list(reversed(by_season[y]))
            for i, r in enumerate(season_rows):
                yror = (i + 1) if len(season_rows) > 1 else 0
                age = rtc.age_on_1_july(p.dob, y) if p.dob else None
                if r["youth"]:
                    # zerozero files a real youth side ("Benfica [Jun.A S19]")
                    if age is None or YOUTH_MIN_AGE <= age <= 18:
                        rows.append(model.Row(y, r["club"], yror=yror, ytht=True, nation=r["nation"]))
                    continue
                rows.append(model.Row(y, r["club"], apps=r["apps"], goals=r["goals"], yror=yror,
                                      onln=r.get("loan", False), nation=r["nation"],
                                      level=r.get("level")))
    else:
        # Wikipedia alone. A bare year shares the season the previous ranged
        # stay ended in (Futre: Atletico 1987-1993, then Benfica "1993" is
        # 1992/93); after another bare year it opens the next one (Marseille
        # "1993" is 1993/94).
        # the article's career statistics table, where it has one, gives a
        # row per season and club (Dalbert); the infobox stays only fill the
        # seasons it does not reach
        table = [t for t in box.get("table") or [] if t["season"] < prime_season]
        covered = {t["season"] for t in table}
        # a statistics table marks no loans: the infobox's "→" stays do
        # (Paulinho's Grosseto and Sorrento)
        loaned = [(y, club) for years, club, loan, _, nat in box["senior"] if loan
                  for y in stay_years(years, club, nat)]
        for t in table:
            loan = t["loan"] or any(y == t["season"] and same_club_name(c, t["club"])
                                    for y, c in loaned)
            rows.append(model.Row(t["season"], t["club"], apps=t["apps"], goals=t["goals"],
                                  onln=loan, nation=t["nation"]))
        last_season, last_bare = None, False
        for years, club, loan, stats, nat in box["senior"]:
            # a year next to one the table lists at this club is the same
            # stay counted another way (Paulinho's Juventude: infobox
            # "2003-2004", table 2004) - the table has it
            ys = [y for y in stay_years(years, club, nat) if y not in covered
                  and not any(abs(t["season"] - y) <= 1 and same_club_name(t["club"], club)
                              for t in table)]
            if not ys:
                continue
            if (bare(years) and not is_cal(club, nat) and last_season == ys[0] - 1
                    and not last_bare):
                ys = [ys[0] - 1]
            m = re.match(r"\s*(\d+)\s*\((\d+)\)", stats or "")
            one = len(ys) == 1 and m
            for y in ys:
                if y >= prime_season:
                    continue
                rows.append(model.Row(y, club, apps=int(m.group(1)) if one else None,
                                      goals=int(m.group(2)) if one else None, onln=loan,
                                      nation=nat))
            if ys:
                last_season, last_bare = ys[-1], bare(years)
        if table:
            p.flags.append("No NFT page: seasons %d-%d come from Wikipedia's career statistics "
                           "table (one row per season)." % (min(covered), max(covered)))
        if len(rows) > len(table):
            p.flags.append("No NFT page: seasons outside the career table come from Wikipedia's "
                           "infobox, which gives a total per stay - apps and goals are written only "
                           "for one-season stays, the rest are blank.")
        # order within a shared year: a calendar-year club's season (January)
        # comes before a European one that starts in July (Flamengo 2013, then
        # Viseu 2013/14); otherwise the order the page lists them
        order = {id(r): (0 if is_cal(r.club, r.nation) else 1, i) for i, r in enumerate(rows)}
        rows.sort(key=lambda r: (r.year, order[id(r)]))
        seen = {}
        for r in rows:
            seen.setdefault(r.year, []).append(r)
        for y, rs in seen.items():
            if len(rs) > 1:
                for i, r in enumerate(rs):
                    r.yror = i + 1

    # youth blank rows: wiki youth years with no senior row, from the season he
    # turns 15 to 18 on 1 July; the childhood clubs Wikipedia lists from age 8
    # (Futre's Montijo) are not written
    # A year can hold a youth row next to another club's row - two youth clubs
    # in one calendar year (Dalbert: Barra Mansa and Fluminense, 2012), or a
    # youth club before a European move (Flamengo 2013, Viseu from January)
    # - but never a second row at the same club.
    taken = [(r.year, r.club) for r in rows]
    youth_seen = []
    for y, club, nat in wiki_youth_years:
        if (y >= prime_season or any(ty == y and same_club_name(club, tc) for ty, tc in taken)
                or (y, club) in youth_seen):
            continue
        age = rtc.age_on_1_july(p.dob, y) if p.dob else None
        if age is not None and YOUTH_MIN_AGE <= age <= 18:
            rows.append(model.Row(y, club, apps=None, goals=None, ytht=True, nation=nat))
            youth_seen.append((y, club))
    # a season the season-by-season source skips, between his first and last,
    # comes from the Wikipedia infobox's stays (user, 2026-10-09: Merlo's
    # Savoia 1938/39, Ambrosiana-Inter 1943/44, Varese 1944/45); apps and
    # goals only for a one-season stay, as on the Wikipedia-only path
    have = {r.year for r in rows}
    if have and box["senior"] and (nft_html or zz_data.get("rows")):
        filled = set()
        for stay_years_raw, club, loan, stats, nat in box["senior"]:
            ys = stay_years(stay_years_raw, club, nat)
            m = re.match(r"\s*(\d+)\s*\((\d+)\)", stats or "")
            for y in ys:
                if min(have) < y < max(have) and y not in have and y < prime_season:
                    one = len(ys) == 1 and m
                    # the level the club had in the source a season before or
                    # after (Piana's Imperia: Serie C 1937/38, so 1938/39 too)
                    level = next((r.level for r in rows if r.level and abs(r.year - y) == 1
                                  and same_club_name(r.club, club)), None)
                    rows.append(model.Row(y, club, apps=int(m.group(1)) if one else None,
                                          goals=int(m.group(2)) if one else None, onln=loan,
                                          nation=nat, level=level))
                    p.flags.append("%d/%02d %s: a season the season-by-season source skips - "
                                   "filled from Wikipedia's infobox." % (y, (y + 1) % 100, club))
                    filled.add(y)
        have |= filled
    # a year with several rows is ordered calendar club first (it starts in
    # January), then the source's own order; the order column numbers them
    by_year = {}
    for i, r in enumerate(rows):
        by_year.setdefault(r.year, []).append((i, r))
    for y, group in by_year.items():
        if len(group) > 1 and len({r.yror for i, r in group}) < len(group):
            group.sort(key=lambda t: (0 if is_cal(t[1].club, t[1].nation) else 1, t[1].yror, t[0]))
            for k, (i, r) in enumerate(group):
                r.yror = k + 1
    # a senior season with 0 games while he is 18 or younger on 1 July (turns
    # 19 during it at the latest) is a youth season: blank, youth tick (user,
    # 2026-10-13). A blank season (no figures) is not a 0 and stays as it is.
    for r in rows:
        age = rtc.age_on_1_july(p.dob, r.year) if p.dob else None
        if not r.ytht and r.apps == 0 and age is not None and age <= 18:
            r.ytht, r.apps, r.goals = True, None, None
    rows.sort(key=lambda r: (r.year, r.yror))
    p.rows = rows
    years = sorted({r.year for r in rows})
    for y in range(years[0], years[-1]) if years else ():
        if y not in years:
            p.flags.append("Hole in the career: no source names a club for %d/%02d - left "
                           "empty, fill it by hand if you know it." % (y, (y + 1) % 100))

    # caps: NFT matches strictly before the prime season starts (1/7)
    caps = goals = 0
    for date_str, g in (nft.matches(nft_html) if nft_html else []):
        y, m, d = (int(x) for x in date_str.split("-"))
        if (y, m, d) < (prime_season, 7, 1):
            caps += 1
            goals += g
    p.caps, p.cap_goals = caps, goals
    if not nft_html:
        p.flags.append("No NFT page: international caps before the prime are unknown - Piap/Pigl unset.")
    if zz_data.get("rows") and not nft_html:
        p.flags.append("Career from zerozero/bdfutbol/carrierecalciatori/foradejogo: divisions come from FM26's league history, "
                       "each club is looked for in the country its row names.")
    return p


def build_spells(rows, club_key=None, target_club=None, prime_season=None, calendar=None):
    """Owner runs (consecutive rows sharing the last non-loan club) plus
    nested loan spells inside them - see CLAUDE.md 5c/5d and the worked
    derivation in the report. Same-season joins split on 1/1 (European
    calendar; Italy is not in CALENDAR_YEAR_NATIONS). The spell at
    `target_club` is left open; when he was elsewhere before his prime, a new
    one opens there on the prime season's first day.

    `club_key(row)` groups rows by the SAME real club even when the two
    sources spell its name differently (Wikipedia's "Empoli" vs NFT's "Empoli
    FC") - resolved FM ids, when the caller has them, else the row's own club
    string."""
    key = club_key or (lambda r: r.club)
    owning = []
    current = None
    for r in rows:
        if not r.onln:
            current = key(r)
        owning.append(current)

    # `calendar(club)` is True for a calendar-year league (Brazil: 1/1-31/12,
    # a move inside the year on 1/7); European otherwise (1/7-30/6, a move on 1/1)
    cal = calendar or (lambda club: False)

    def season_join(y, club=None):
        return (1, 1, y) if cal(club) else (1, 7, y)

    def season_leave(y, club=None):
        return (31, 12, y) if cal(club) else (30, 6, y + 1)

    def mid_join(y, club):
        """The second club of a shared season starts halfway through it."""
        return (1, 7, y) if cal(club) else (1, 1, y + 1)

    def mid_leave(y, club):
        return (30, 6, y) if cal(club) else (31, 12, y)

    owner_runs = []
    i = 0
    while i < len(rows):
        club = owning[i]
        j = i
        while j < len(rows) and owning[j] == club:
            j += 1
        owner_runs.append({"club": club, "rows": rows[i:j]})
        i = j
    def before(d):
        """The day before a join date: 1/7 -> 30/6, 1/1 -> 31/12."""
        import datetime as dt
        x = dt.date(d[2], d[1], d[0]) - dt.timedelta(days=1)
        return (x.day, x.month, x.year)

    for run in owner_runs:
        first = run["rows"][0]
        # a run that opens as the second club of a shared season starts 1/1
        run["join"] = (mid_join(first.year, run["club"]) if first.yror == 2
                       else season_join(first.year, run["club"]))
    for k, run in enumerate(owner_runs):
        last = run["rows"][-1]
        # the end of the last season it played, or the day before the next
        # club takes over, whichever comes first (a gap year leaves no spell)
        end = mid_leave(last.year, run["club"]) if last.yror == 1 else season_leave(last.year, run["club"])
        if k + 1 < len(owner_runs):
            nxt = before(owner_runs[k + 1]["join"])
            run["left"] = min(end, nxt, key=lambda d: (d[2], d[1], d[0]))
        elif target_club is None or run["club"] == target_club:
            run["left"] = None          # open: he is still there in his prime
        else:
            run["left"] = end           # he moves to the target club for his prime
    if target_club is not None and (not owner_runs or owner_runs[-1]["club"] != target_club):
        owner_runs.append({"club": target_club, "rows": [], "join": season_join(prime_season, target_club),
                           "left": None})

    loan_spells = []
    for run in owner_runs:
        rr = run["rows"]
        i = 0
        while i < len(rr):
            if not rr[i].onln:
                i += 1
                continue
            j = i
            while j < len(rr) and rr[j].onln and rr[j].club == rr[i].club:
                j += 1
            group = rr[i:j]
            y0, y1 = group[0].year, group[-1].year
            lc = key(group[0])
            if len(group) == 1 and group[0].yror == 0:
                join, left = season_join(y0, lc), season_leave(y0, lc)
            else:
                # part of a shared season: derive the mid-season split from row order
                join = mid_join(y0, lc) if group[0].yror == 2 else season_join(y0, lc)
                left = season_leave(y1, lc) if group[-1].yror != 1 else mid_leave(y1, lc)
            # a loan row that opens a shared season on yror=1 still starts the season
            if group[0].yror == 1:
                join = season_join(y0, lc)
            loan_spells.append({"club": key(group[0]), "join": join, "left": left,
                                "loan": True, "owner": run["club"]})
            i = j

    spells = []
    for run in owner_runs:
        spells.append({"club": run["club"], "join": run["join"], "left": run["left"],
                       "loan": False, "owner": None})
    spells.extend(loan_spells)
    return spells


# Ethnicity (`Peth`) from the country of BIRTH (user, 2026-10-08); any other
# country leaves it unset. FM's values, read off the author's files: 0 Northern
# European, 1 Mediterranean/Hispanic, 2 North African/Middle Eastern,
# 3 African/Caribbean, 9 Mixed Race.
MEDITERRANEAN = {"Portugal", "Spain", "France", "Italy", "Greece", "Germany", "Switzerland",
                 "Austria", "Luxembourg", "Malta", "Cyprus",
                 "Andorra", "Monaco", "San Marino", "Liechtenstein", "Croatia", "Slovenia",
                 "Serbia", "Bosnia and Herzegovina", "Montenegro", "North Macedonia", "Albania",
                 "Kosovo", "Bulgaria", "Romania", "Hungary", "Czech Republic", "Czechia", "Slovakia"}
NORTHERN = {"Sweden", "Norway", "Denmark", "Finland", "Iceland", "England", "Scotland", "Wales",
            "Northern Ireland", "Republic of Ireland", "Russia", "Ukraine", "The Netherlands",
            "Belgium", "Poland"}
NORTH_AFRICA = {"Morocco", "Algeria", "Tunisia", "Egypt", "Libya"}
AFRICA = {"Mozambique", "Angola", "Cape Verde", "Guinea-Bissau", "São Tomé e Príncipe",
          "Nigeria", "Ghana", "Cameroon", "Côte d'Ivoire", "Senegal", "Mali", "Guinea",
          "DR Congo", "Congo", "Zambia", "Zimbabwe", "South Africa", "Morocco", "Algeria",
          "Tunisia", "Egypt", "Libya", "Kenya", "Tanzania", "Uganda", "Ethiopia", "Gabon",
          "Equatorial Guinea", "Burkina Faso", "Benin", "Togo", "Niger", "Chad", "Sudan",
          "Liberia", "Sierra Leone", "Gambia", "Mauritania", "Madagascar", "Malawi", "Namibia",
          "Botswana", "Rwanda", "Burundi", "Eritrea", "Somalia", "Djibouti", "Lesotho",
          "Eswatini", "Mauritius", "Seychelles", "Comoros", "Central African Republic"}
SOUTH_AMERICA = {"Brazil", "Argentina", "Uruguay", "Paraguay", "Chile", "Bolivia", "Peru",
                 "Ecuador", "Colombia", "Venezuela", "Guyana", "Suriname", "French Guiana"}
BIRTH_COUNTRY_ALIAS = {"Brasil": "Brazil", "Moçambique": "Mozambique", "Portuguese Mozambique":
                       "Mozambique", "Portuguese Angola": "Angola", "Portuguese Cape Verde":
                       "Cape Verde", "Portuguese Guinea": "Guinea-Bissau", "Espanha": "Spain",
                       "França": "France", "Itália": "Italy", "Alemanha": "Germany",
                       "West Germany": "Germany", "East Germany": "Germany",
                       "Yugoslavia": "Serbia", "SFR Yugoslavia": "Serbia",
                       "Czechoslovakia": "Czechia", "Zaire": "DR Congo",
                       "Rhodesia": "Zimbabwe", "Netherlands": "The Netherlands"}


def ethnicity(country):
    """(value, note) for `Peth`; value None leaves the field unset."""
    c = fm_nation(BIRTH_COUNTRY_ALIAS.get(country, country)) if country else None
    if c in NORTHERN:
        return 0, "Northern European"
    if c in NORTH_AFRICA:
        return 2, "North African/Middle Eastern"
    if c in MEDITERRANEAN:
        return 1, "Mediterranean/Hispanic"
    if c in AFRICA:
        return 3, "African/Caribbean"
    if c in SOUTH_AMERICA:
        return 9, "Mixed Race"
    return None, "left empty"


# a town under its old name in the sources, its FM26 name today
CITY_ALIAS = {"Lourenço Marques": "Maputo", "Léopoldville": "Kinshasa", "Salisbury": "Harare",
              "Nova Lisboa": "Huambo", "Sá da Bandeira": "Lubango", "Vila Pery": "Chimoio",
              "João Belo": "Xai-Xai", "Porto Amélia": "Pemba", "Silva Porto": "Kuito",
              "Bombay": "Mumbai", "Leningrad": "Saint Petersburg",
              # FM26's own name for the city; a district or village under the
              # municipality FM26 has (user, 2026-10-09)
              "Buenos Aires": "Ciudad de Buenos Aires", "Puente Castro": "León",
              "San Martín de Porto": "Cariño"}


def city_id(name, country=None):
    """FM26's city DBID for a town name in the country he was born in, or the
    report line saying why not. A name matches itself or a Brazilian "Name (UF)"
    (Rio de Janeiro is "Rio de Janeiro (RJ)"), accents ignored, and only cities
    of the birth country count (Luanda is the Angolan one, not the Kenyan
    town) - the nation of each city comes from FM26 itself (fm26_world)."""
    import fm26_world
    if not name:
        return "No place of birth in any source - Pcbi left unset."
    table = fm26_world.cities()
    nat_id = None
    if country:
        c = fm_nation(BIRTH_COUNTRY_ALIAS.get(country, country))
        nat_id = rtc.nation_ids([c]).get(c)
    # the name as written first, the alias only when that finds nothing: a
    # Brazilian "Buenos Aires" is the town in Pernambuco, not the capital
    for name in dict.fromkeys([name, CITY_ALIAS.get(name, name)]):
        want = _squash(name)
        ids = [int(k) for k, v in table.items()
               if _squash(v) == want or _squash(re.sub(r"\s*\([^)]*\)\s*$", "", v)) == want]
        if nat_id is not None:
            ids = [i for i in ids if fm26_world.city_nation(i) == nat_id]
        if ids:
            break
    if not ids and nat_id is not None:
        # FM26 names a city in its own language (Bucuresti, Milano, Sevilla),
        # Wikipedia en in English: the city article's title in every language,
        # the first that is ONE city of the birth country
        import sources.wikipedia as wiki
        try:
            titles = wiki.langlinks("en", name).values()
        except Exception:
            titles = []
        for t in titles:
            want = _squash(re.sub(r"\s*\([^)]*\)\s*$", "", t).split(",")[0])
            hit = [int(k) for k, v in table.items()
                   if (_squash(v) == want or _squash(re.sub(r"\s*\([^)]*\)\s*$", "", v)) == want)
                   and fm26_world.city_nation(int(k)) == nat_id]
            if len(hit) == 1:
                return hit[0]
    if len(ids) == 1:
        return ids[0]
    where = " in %s" % country if nat_id is not None else ""
    if not ids:
        return "City of birth %r%s is not in FM26's city table - Pcbi left unset." % (name, where)
    return ("City of birth %r%s names %d FM26 cities (%s) - Pcbi left unset, pick one by hand."
            % (name, where, len(ids), ", ".join(map(str, ids))))


def city_op(uid, dbid, rng):
    """`Pcbi`, the shape fill_city_of_birth writes and FM26 imports."""
    rec = ET.Element("record")
    ET.SubElement(rec, "integer", id="database_table_type", value="1")
    ET.SubElement(rec, "large", id="db_unique_id", value=str(uid))
    ET.SubElement(rec, "unsigned", id="property", value=str(c.prop_id("Pcbi")))
    nv = ET.SubElement(rec, "record", id="new_value")
    ET.SubElement(nv, "unsigned", id="id", value=ROW_ID)
    ET.SubElement(nv, "large", id="city", value=str(dbid * 4294967297))
    ET.SubElement(nv, "integer", id="DBID", value=str(dbid))
    ET.SubElement(rec, "integer", id="version", value=BUILD)
    ET.SubElement(rec, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    return rec


def row_dates(rows, spells, club_key, calendar=None):
    """{row index: (join, leaving)} in real dates, read off the spells: the first
    row of a spell carries its join, the last its leave (CLAUDE.md, "Join and
    leave dates on a rebuilt career"). A loan nests inside the parent spell
    without breaking it, so the parent's last row before or after the loan
    still closes the parent. An open spell leaves its last row with no leave."""
    cal = calendar or (lambda club: False)

    def season_of(d, club):
        return d[2] if cal(club) or d[1] >= 7 else d[2] - 1
    out = {}
    for sp in spells:
        lo = season_of(sp["join"], sp["club"])
        hi = season_of(sp["left"], sp["club"]) if sp["left"] else 9999
        idx = [i for i, r in enumerate(rows)
               if club_key(r) == sp["club"] and bool(r.onln) == bool(sp["loan"]) and lo <= r.year <= hi]
        if not idx:
            continue
        out[idx[0]] = (sp["join"], out.get(idx[0], (None, None))[1])
        if sp["left"]:
            out[idx[-1]] = (out.get(idx[-1], (None, None))[0], sp["left"])
    return out


def date_el(d):
    return ET.Element("date", day=str(d[0]), month=str(d[1]), year=str(d[2]), time="0")


# ------------------------------------------------------------- position ----

CSV_POSITIONS = {"GK": "Pgoa", "RB": "Pdrs", "CB": "Pdce", "LB": "Pdls", "DM": "Pdmc",
                 "CM": "Pmce", "AM": "Pamc", "RW": "Pamr", "LW": "Paml", "ST": "Pace",
                 # Portuguese sheets; keys upper-case, as the readers upper-case the cell
                 "GR": "Pgoa", "DD": "Pdrs", "DC": "Pdce", "DE": "Pdls", "MDEF": "Pdmc",
                 "MD": "Pdmc", "MC": "Pmce", "MAC": "Pamc", "MO": "Pamc", "ED": "Pamr",
                 "EE": "Paml", "PL": "Pace"}

POSITION_MAP = {
    "goalkeeper": "Pgoa",
    "centre back": "Pdce",
    "left back": "Pdls",
    "right back": "Pdrs",
    "left wing back": "Pwbl",
    "right wing back": "Pwbr",
    "defensive midfielder": "Pdmc",
    "central midfielder": "Pmce",
    "left midfielder": "Pmls",
    "right midfielder": "Pmrs",
    "attacking midfielder": "Pamc",
    "left winger": "Paml",
    "right winger": "Pamr",
    "centre forward": "Pace",
    "striker": "Pace",
    "sweeper": "Pswe",
}


def position_fourcc(label, override=None):
    if override:
        return override, None
    key = (label or "").strip().lower()
    if key in POSITION_MAP:
        return POSITION_MAP[key], None
    return "Pdce", "no source position mapped for %r, defaulted to Pdce - VERIFY" % label


# ------------------------------------------------------------- full build --

def fetch_sources(urls, name):
    """(nft_html, wiki box, notes) from the row's links: one per site, the
    site told apart by its host. zerozero needs the browser (Cloudflare) and
    is not wired yet, so its link is only reported."""
    import sources.nft as nft
    import sources.wikipedia as wiki
    nft_html, box, notes, zz_data = None, None, [], None
    slug = re.sub(r"\W+", "_", name.lower()).strip("_")
    for url in urls:
        url = url.strip()
        if not url:
            continue
        if "national-football-teams.com" in url:
            nft_html = nft.fetch(url, "nft_%s.html" % slug)
        elif "wikipedia.org" in url:
            box, note = wiki.read_url(url)
            if note:
                notes.append(note)
            if not box["senior"] and not box["youth"] and not box["table"]:
                notes.append("Wikipedia (%s) has no career infobox the parser reads."
                             % wiki.from_url(url)[0])
        elif "bdfutbol" in url:
            import sources.bdfutbol as bdf
            data = bdf.load(url)
            if data is None:
                notes.append("bdfutbol page not fetched yet - run the browser step for %s "
                             "(expects %s)" % (url, bdf.cache_path(url)))
            else:
                # same row shape as zerozero; bdfutbol lists oldest first
                data["rows"] = list(reversed(data["rows"]))
                zz_data = zz_data or data
        elif "foradejogo" in url:
            import sources.foradejogo as fdj
            zz_data = zz_data or fdj.load(url)  # newest first, like zerozero
        elif "carrierecalciatori" in url:
            import sources.carrierecalciatori as cc
            zz_data = zz_data or cc.load(url)   # newest first, like zerozero
        elif "zerozero" in url:
            import sources.zerozero as zz
            data = zz.load(url)
            # the first season-by-season source that has data wins: an
            # alternate link not fetched yet must not wipe the main one (Ávalos)
            zz_data = zz_data or data
            if data is None:
                notes.append("zerozero page not fetched yet - run the browser step for %s "
                             "(expects %s)" % (url, zz.cache_path(url)))
        else:
            notes.append("Unrecognised link, not read: %s" % url)
    return nft_html, box, notes, zz_data


CLUB_OVERRIDES = os.path.join(HERE, "club_overrides.json")


def club_for(name, nation, player_nation, cache):
    """A source's club name -> FM26 club, or None. `club_overrides.json` pins
    a name once by hand ({"Olympique de Marselha|France": 866}); otherwise the
    club's own country (the source's, else the player's), then anywhere; the
    link target Wikipedia hides behind a short name is the last try."""
    import sources.wikipedia as wiki
    over = json.load(open(CLUB_OVERRIDES)) if os.path.exists(CLUB_OVERRIDES) else {}
    for nat in dict.fromkeys([fm_nation(nation), fm_nation(player_nation)]):
        k = "%s|%s" % (name, nat)
        if k in over:
            return {"id": int(over[k]), "name": "override", "weak": False}
    loose = None
    for nm in dict.fromkeys([name, wiki.ALT_NAMES.get(name)]):
        if not nm:
            continue
        # with the club's country known, only that country; without it,
        # anywhere, the player's own country preferred on a tie
        for nat in ([nation] if nation else [None]):
            hit = resolve_club(nm, nat, cache, prefer=player_nation)
            if hit and not hit.get("weak"):
                return hit
            loose = loose or hit
    return loose


def history_rows(dbid, prime_season):
    """Rows before the prime from FM26's playing history of `dbid` - a person
    the release deleted but whose history it kept (user, 2026-10-22: Kali
    7002246). Clubs come as FM ids, keyed by name with their hits preset."""
    import fm26_history
    names = _names()
    rows, clubs = [], {}
    for h in fm26_history.History().rows(dbid):
        if h["year"] >= prime_season:
            continue
        cid = h["club"] or UNKNOWN_CLUB
        key = names.get("team", cid) or "fm:%d" % cid
        if clubs.get(key, {}).get("id", cid) != cid:
            key = "%s (%d)" % (key, cid)
        clubs[key] = {"id": cid, "name": key, "weak": False}
        r = model.Row(h["year"], key, apps=h["apps"], goals=h["gols"], yror=h["yror"] or 0,
                      onln=bool(h["onln"]), ytht=bool(h["ytht"]),
                      nation=club_nation(cid) if cid != UNKNOWN_CLUB else None)
        r.divi = h["divi"]
        rows.append(r)
    rows.sort(key=lambda r: (r.year, r.yror))
    return rows, clubs


def build_changeset(row, cache_dir, ids_path, out_xml, out_report):
    """row: dict(name, nation, prime_season(int), target_club, target_season(int),
    position(override or ''), urls (list)). Fetches sources, builds the model,
    emits the changeset and a report, and verifies the written file."""
    flags = []
    name = row["name"]
    prime_season = int(row["prime_season"])
    target_season = int(row["target_season"])
    offset = target_season - prime_season
    nation = row.get("nation") or "Italy"

    nft_html, box, notes, zz_data = fetch_sources(row["urls"], name)
    flags.extend(notes)
    if nft_html and not box:
        import sources.nft as nft
        import sources.wikipedia as wiki
        lang, wt = wiki.find(name, nation, nft.dob(nft_html))
        if wt:
            box = wiki.infobox_any(wt, lang)
            flags.append("Wikipedia (%s) found by name, birth date matching NFT." % lang)
        else:
            flags.append("No Wikipedia page found with his birth date: youth clubs and loans "
                         "come from NFT only.")
    if not nft_html and not box and not zz_data and not row.get("history_id"):
        raise SystemExit("%s: no source the creator can read (NFT, Wikipedia or a fetched zerozero page)" % name)

    cache = _club_cache()
    tc = str(row["target_club"]).strip()
    # an id (the batch resolves the sheet's Team once, create_legends.target_ids)
    target_hit = ({"id": int(tc), "name": "id", "weak": False} if tc.isdigit()
                  else club_for(tc, None, nation, cache))
    if target_hit is None:
        raise SystemExit("target club %r did not resolve - cannot place the contract" % row["target_club"])
    # a row with no country (Wikipedia en) is looked for in the target club's
    # country first: the legend is placed in that league, and the player's own
    # nation (Babalito: Mozambique) says nothing about his clubs
    target_nation = club_nation(target_hit["id"])

    def calendar_of(club_name, nat):
        """Does this source club play a calendar-year league? Its country from
        the source, else the club it resolves to."""
        if not nat:
            hit = club_for(club_name, None, target_nation or nation, cache)
            nat = club_nation(hit["id"]) if hit else None
        return fm_nation(nat) in c.CALENDAR_YEAR_NATIONS

    p = gather_profile(name, nation, prime_season, nft_html, box, zz_data, calendar_of)
    if not p.dob and row.get("dob"):
        p.dob = row["dob"]
    preset_clubs = {}
    if row.get("history_id"):
        p.rows, preset_clubs = history_rows(int(row["history_id"]), prime_season)
        if not p.full:
            # the site index still files his full name under the old id
            hit = search("fm_id:=%s" % row["history_id"], by="name", q="*", n=1)
            terms = (hit[0]["document"].get("search_terms") or []) if hit else []
            full = terms[0] if terms and len(terms[0].split()) > 1 else None
            if full:
                p.full = full
                if p.first == p.last or not box:
                    p.first, p.last = full.split()[0], full.split()[-1]
                p.common = name if name != "%s %s" % (p.first, p.last) else None
        p.flags = [f for f in p.flags if "NFT page: seasons" not in f and "Career from" not in f
                   and "Hole in the career" not in f]
        p.flags.append("Career copied from FM26's playing history of %s, a person FM26 no "
                       "longer has (clubs, divisions, apps, goals, youth and loan ticks as FM26 "
                       "holds them)." % row["history_id"])
    if not p.rows:
        flags.append("NO CAREER: no source has a season before the prime - the record holds "
                     "only the open spell at the target club. Find another source.")
    if row.get("first_last"):
        # the sheet names him 'First "Common" Last': that wins over the sources
        p.first, p.last = row["first_last"]
        p.common = name
    for r in p.rows:
        if r.flag:
            flags.append(r.flag)
    flags.extend(p.flags)

    # a row with no country (Wikipedia's youth list) takes it from a row of
    # the same club that has one (user, 2026-10-09: Brito's "Barco" is NFT's
    # Portuguese "SC Barco", not Spain's Barco, which the target club's
    # country would otherwise prefer)
    for r in p.rows:
        if not r.nation:
            r.nation = next((o.nation for o in p.rows
                             if o.nation and same_club_name(r.club, o.club)), None)

    # --- club / division resolution ---------------------------------------
    club_ids = dict(preset_clubs)
    # a foreign player's rows with no country, before he first joins the
    # target club, are looked for in his own country first (user, 2026-10-09:
    # Paulinho's "Juventude" is Caxias do Sul's, not Juventude Stabia)
    home = fm_nation(p.birth_country or p.nation)
    arrival = min((r.year for r in p.rows
                   if (club_for(r.club, r.nation, target_nation or p.nation, cache) or {}).get("id")
                   == target_hit["id"]), default=None)

    def prefer(r):
        if (not r.nation and home and home != fm_nation(target_nation)
                and arrival is not None and r.year < arrival):
            return home
        return target_nation or p.nation

    for r in p.rows:
        if r.club not in club_ids:
            hit = club_for(r.club, r.nation, prefer(r), cache)
            if hit is None:
                # FM26 lacks the club: the season is kept, at Unknown Club
                # (user, 2026-10-08); a real id can be pinned in club_overrides.json
                flags.append("Club not in FM26: %r (%s) - written as Unknown Club (%d). Pin the "
                             "right id in club_overrides.json if it exists."
                             % (r.club, r.nation or target_nation or p.nation, UNKNOWN_CLUB))
                hit = {"id": UNKNOWN_CLUB, "name": "Unknown Club", "weak": False}
            elif hit.get("weak"):
                flags.append("CHECK club: %r (%s) matched only loosely to %s (FM id %d) - pin the "
                             "right one in club_overrides.json if wrong."
                             % (r.club, r.nation or p.nation, hit["name"], hit["id"]))
            club_ids[r.club] = hit
    _club_cache_save(cache)

    levels = json.load(open(os.path.join(HERE, "levels.json")))
    div_ids = {}
    for r in p.rows:
        nat = fm_nation(r.nation or p.nation)
        if r.level and (nat, r.level) not in div_ids:
            entry = levels.get(nat, {}).get(r.level)
            div_ids[(nat, r.level)] = entry["id"] if entry and entry.get("id") else None

    if target_hit.get("weak"):
        flags.append("CHECK target club: %r matched only loosely to %s (FM id %d)."
                     % (row["target_club"], target_hit["name"], target_hit["id"]))

    nation_ids_map = rtc.nation_ids([fm_nation(p.nation)])
    nation_dbid = nation_ids_map.get(fm_nation(p.nation))
    if nation_dbid is None:
        flags.append("Nation %r did not resolve via the search index." % p.nation)

    def club_key(r):
        hit = club_ids.get(r.club)
        return hit["id"] if hit else ("unresolved:" + r.club)

    spells = build_spells(p.rows, club_key=club_key, target_club=target_hit["id"],
                          prime_season=prime_season, calendar=is_calendar_club)
    # drop spells at an unresolved club - nothing to point the Pnph row at
    resolved_spells = [s for s in spells if isinstance(s["club"], int)]
    dropped_spells = [s for s in spells if not isinstance(s["club"], int)]
    for s in dropped_spells:
        flags.append("Pnph spell at unresolved club %r dropped (join %s)." % (s["club"], s["join"]))

    # --- home-grown (post playing-history, per PLAN) -----------------------
    hg_rows = [{"club": club_ids[r.club]["id"], "year": r.year}
              for r in p.rows if club_ids.get(r.club) and club_ids[r.club]["id"] != UNKNOWN_CLUB]
    # the fallback is a nation NAME (home_grown resolves names to ids later)
    hg_clubs, hg_nations, hg_fell_back = rtc.home_grown(hg_rows, p.dob, _Namer(club_ids),
                                                         fm_nation(p.nation))

    # --- ids -----------------------------------------------------------
    uid = mint_id(ids_path, "%s|%d" % (name, prime_season))
    rng = random.Random(int(uid))

    ops = []
    ops.append(rlr.addr_row(uid, rng))
    ops.append(rlr.type_change(uid, rng))

    ops.append(nrr.string_op(uid, "Pfna", p.first, rng))
    ops.append(nrr.string_op(uid, "Psna", p.last, rng))
    plain = "%s %s" % (p.first, p.last)
    if p.common and p.common != plain:
        ops.append(nrr.string_op(uid, "Pcna", p.common, rng))
    if p.full and p.full != plain:
        ops.append(nrr.string_op(uid, "Pfln", p.full, rng))

    shifted_dob = (p.dob[0], p.dob[1], p.dob[2] + offset) if p.dob else None
    if shifted_dob:
        ops.append(date_op(uid, "Pdob", shifted_dob, rng))
    else:
        flags.append("No DOB found - Pdob left unset.")

    if nation_dbid:
        ops.append(nrr.nation_op(uid, nation_dbid, rng))
    born_in = p.birth_country or p.nation
    if not p.birth_country:
        flags.append("No country of birth in the sources: ethnicity taken from his nationality (%s)."
                     % p.nation)
    eth, eth_label = ethnicity(born_in)
    if eth is not None:
        ops.append(int_op(uid, "Peth", eth, rng, odvl=-1))
    city = None
    for place in getattr(p, "birthplaces", None) or [p.birthplace]:
        found = city_id(place, born_in)
        if isinstance(found, int) or city is None:
            city = found
        if isinstance(found, int):
            p.birthplace = place
            break
    if isinstance(city, int):
        ops.append(city_op(uid, city, rng))
    else:
        flags.append(city)

    pos_fourcc, pos_flag = position_fourcc(p.position[0] if p.position else None,
                                           CSV_POSITIONS.get((row.get("position") or "").strip().upper())
                                           or (row.get("position") if (row.get("position") or "").startswith("P") else None))
    if pos_flag:
        flags.append(pos_flag)
    ops.append(int_op(uid, pos_fourcc, 20, rng, odvl=0))
    if p.height:
        ops.append(int_op(uid, "Phes", p.height, rng, odvl=0))
    else:
        flags.append("No height in any source - Phes left unset.")

    if p.caps:
        ops.append(int_op(uid, "Piap", p.caps, rng, odvl=0))
    if p.cap_goals:
        ops.append(int_op(uid, "Pigl", p.cap_goals, rng, odvl=0))
    r_ops, ratings_written = rating_ops(uid, row.get("ratings"), rng, flags)
    ops.extend(r_ops)

    # Plhs, shifted
    plhs_rows, row_divs = [], []
    dates = row_dates(p.rows, spells, club_key, calendar=is_calendar_club)
    for i, r in enumerate(p.rows):
        hit = club_ids.get(r.club)
        club_el = team_ref(hit["id"]) if hit else None
        divid = row_division(r, hit, div_ids, flags, fm_nation(p.nation))
        row_divs.append(divid)
        divi_el = comp_ref(divid) if divid else None
        pr = ci.new_row()
        pr["year"] = r.year + offset
        pr["yror"] = r.yror
        pr["club"] = club_el
        pr["divi"] = divi_el
        pr["apps"] = r.apps
        pr["gols"] = r.goals
        pr["ytht"] = r.ytht
        pr["onln"] = r.onln
        join, left = dates.get(i, (None, None))
        pr["join"] = date_el((join[0], join[1], join[2] + offset)) if join else None
        pr["leaving"] = date_el((left[0], left[1], left[2] + offset)) if left else None
        plhs_rows.append(pr)
    ops.extend(ci.emit_rows(uid, plhs_rows, BUILD))

    # Pnph, shifted
    shifted_spells = [{"club": s["club"], "join": (s["join"][0], s["join"][1], s["join"][2] + offset),
                       "left": (s["left"][0], s["left"][1], s["left"][2] + offset) if s["left"] else None,
                       "loan": s.get("loan", False)}
                      for s in resolved_spells]
    ops.extend(emit_pnph(uid, shifted_spells, rng))

    # days at club and nation, as of the target season's first day - the
    # same rules as a fix (loan days carved out of the parent spell)
    season_start = (1, 1, target_season) if is_calendar_club(target_hit["id"]) else (1, 7, target_season)

    def next_day(d):
        import datetime as dt
        x = dt.date(d[2], d[1], d[0]) + dt.timedelta(days=1)
        return (x.day, x.month, x.year)
    # a created spell ends the day BEFORE the next one begins (30/6); FM's own
    # leave date is the next join day (Gudjohnsen: Barcelona left 31/8/2009,
    # Monaco joined 31/8/2009), so the created ones are counted inclusively -
    # a full season is 365 days, as FM counts it
    days_spells = [dict(sp, left=next_day(sp["left"]) if sp["left"] else None)
                   for sp in shifted_spells]
    club_days, nation_days, unknown = days_at(
        [sp for sp in days_spells if sp["club"] != UNKNOWN_CLUB], season_start, nation_resolver())
    for cl in unknown:
        flags.append("Club %s has no nation in the index: its days count for the club only." % cl)
    days_entries = list(club_days.items()) + list(nation_days.items())
    ops.extend(emit_pdcn(uid, days_entries, rng))

    # homegrown, men's nation record
    if hg_clubs:
        ops.extend(rtc.hg_ops(str(uid), "Phgc", rtc.HG_CLUB_COL, "Cclu", hg_clubs, BUILD, rng))
    hg_nation_ids = [nation_ids_map.get(n) for n in hg_nations if nation_ids_map.get(n)]
    if not hg_nation_ids and hg_nations:
        # names not yet in nation_ids_map (e.g. the fallback nation) - resolve them
        extra = rtc.nation_ids(hg_nations)
        hg_nation_ids = [extra.get(n) for n in hg_nations if extra.get(n)]
    if hg_nation_ids:
        ops.extend(rtc.hg_ops(str(uid), "Phgn", rtc.HG_NATION_COL, "Nnat", hg_nation_ids, BUILD, rng))

    # contract, at the very end
    # forced to the open spell at the target club (build_spells always leaves one)
    open_spell = next(s for s in resolved_spells if s["left"] is None)
    target_join = (open_spell["join"][0], open_spell["join"][1], open_spell["join"][2] + offset)
    ops.append(ref_op(uid, "Pcti", team_ref(target_hit["id"]), "Ttea", rng))

    written, dropped = c.sync_contract_dates(
        str(uid), {}, ET.fromstring('<date day="%d" month="%d" year="%d" time="0"/>'
                                    % target_join), BUILD, target_season,
        seasons=c.Seasons(_names()), club=target_hit["id"])
    ops.extend(written)
    # PCNj: forced to the same join date as Pcjd (PLAN rule for this probe)
    ops.append(date_op(uid, "PCNj", target_join, rng))

    write_changeset(out_xml, ops)

    return {
        "verify": _verify_with_days(out_xml, uid, plhs_rows, shifted_spells, days_entries),
        "club_days": club_days, "nation_days": nation_days,
        "ethnicity": (born_in, eth, eth_label),
        "uid": uid, "profile": p, "offset": offset, "flags": flags,
        "club_ids": club_ids, "div_ids": div_ids, "nation_dbid": nation_dbid,
        "spells": resolved_spells, "dropped_spells": dropped_spells,
        "hg_clubs": hg_clubs, "hg_nations": hg_nations, "hg_fell_back": hg_fell_back,
        "target_hit": target_hit, "target_join": target_join, "plhs_rows": plhs_rows,
        "row_divs": row_divs,
        "shifted_spells": shifted_spells, "ops": ops, "ratings": ratings_written,
    }


def _verify_with_days(out_xml, uid, plhs_rows, spells, days_entries):
    import verify
    v = verify_output(out_xml, uid, plhs_rows, spells)
    v["problems"] += verify.check_days(out_xml, uid, c.prop_id("Pdcn"), days_entries)
    return v


def write_changeset(out_xml, ops):
    """`ops` inside the header and footer of a changeset FM26 imports."""
    # header and footer of an editor-made changeset (from the Portugal
    # rebuilt records file), kept beside the creator
    text = open(os.path.join(HERE, "template.xml"), encoding="utf-8").read()
    head = text[:text.index('<list id="db_changes">') + len('<list id="db_changes">')]
    body = "".join("\n\t\t" + ET.tostring(o, encoding="unicode") for o in ops)
    tail = text[text.rindex("</list>"):]
    open(out_xml, "w", encoding="utf-8").write(head + body + "\n\t" + tail)


PORTUGAL_REGIONAL = 55020301      # "Portuguese Regional Divisions"
ITALY_UNKNOWN = 1400399           # "Italian Lower Division": an Unknown Club season in Italy
DIVISION_PINS = os.path.join(HERE, "division_overrides.json")
_PINS = None


def _division_pins():
    global _PINS
    if _PINS is None:
        _PINS = json.load(open(DIVISION_PINS, encoding="utf-8")) if os.path.exists(DIVISION_PINS) else {}
    return _PINS

UNKNOWN_CLUB = 16027118
BRAZIL_MISSING = 19127225         # the user's pick for a Brazilian season FM26 lacks           # FM26's "Unknown Club": a club the database lacks
TOP_LEAGUES = os.path.join(HERE, "cache", "fm26_top_leagues.json")
LEAGUE_PART = re.compile(r"\b(Cup|Stage|Phase|Table|Play-?Offs?|Torneo|Apertura|Clausura|"
                         r"Round|Group|Grp)\b", re.I)
_TOP_LEAGUE = None


def top_league(nation):
    """(id, name) of the men's league with the highest reputation in
    `nation`, or None. Read once from the whole index - every men's league,
    reputation first - and cached: a text search for the country's name
    missed the top flight (Romania's First League, rep 127, lost to a Third
    League group, rep 58)."""
    global _TOP_LEAGUE
    if _TOP_LEAGUE is None:
        if os.path.exists(TOP_LEAGUES):
            _TOP_LEAGUE = json.load(open(TOP_LEAGUES, encoding="utf-8"))
        else:
            _TOP_LEAGUE, page, found = {}, 1, 1
            while (page - 1) * 250 < found:
                url = (fm_names.HOST + "/collections/detailed_game_items/documents/search?q=*"
                       "&query_by=name&filter_by=%s&sort_by=reputation:desc&per_page=250&page=%d"
                       "&x-typesense-api-key=%s" % (urllib.parse.quote(
                           "type_id:=competition && classification_id:=league && gender:=mens"),
                           page, fm_names.KEY))
                req = urllib.request.Request(url, headers={"User-Agent": "fmpt-legends/1.0"})
                data = json.load(urllib.request.urlopen(req, timeout=30))
                found = data["found"]
                for h in data["hits"]:
                    d = h["document"]
                    nat = (d.get("nation") or {}).get("name")
                    # a split season's stages and tables, and a league cup,
                    # carry the league's reputation or more (Argentine League
                    # Cup 146 over the Premier Division)
                    if LEAGUE_PART.search(d["name"]):
                        continue
                    if nat and nat not in _TOP_LEAGUE:
                        _TOP_LEAGUE[nat] = [int(d["fm_id"]), d["name"]]
                page += 1
            json.dump(_TOP_LEAGUE, open(TOP_LEAGUES, "w", encoding="utf-8"), indent=0,
                      sort_keys=True, ensure_ascii=False)
    top = _TOP_LEAGUE.get(nation)
    return tuple(top) if top else None


def missing_division(club_nation_name):
    """(division, how) for a season FM26's league history does not cover:
    Portugal's regional divisions, an African country's top league, else
    nothing."""
    n = fm_nation(club_nation_name)
    if n == "Portugal":
        return PORTUGAL_REGIONAL, "Portuguese Regional Divisions"
    if n == "Brazil":
        return BRAZIL_MISSING, "competition %d (Brazil)" % BRAZIL_MISSING
    # Africa and El Salvador (user, 2026-10-08) - and any other country: its
    # highest-reputation men's league
    if n:
        top = top_league(n)
        if top:
            return top[0], "%s's top league, %s" % (n, top[1])
    return None, None


def row_division(r, hit, div_ids, flags, nation=None):
    """The competition the club played in THAT season, from FM26's own team
    league history (user, 2026-10-08: levels change by era, the top flight
    does not). The source's level mapped to today's competition is only the
    fallback, and is flagged. A blank youth row carries no division."""
    import fm26_leagues
    if getattr(r, "divi", None):
        # a row copied from FM26's playing history carries its own division
        return r.divi
    key = (fm_nation(r.nation) or nation, r.level)
    if not hit:
        return div_ids.get(key) if r.level and not r.ytht else None
    # Unknown Club has neither a real league history nor a country of its own
    # (FM26 files it under Albania): the season's own country stands in
    unknown = hit["id"] == UNKNOWN_CLUB
    home = (r.nation or nation) if unknown else (club_nation(hit["id"]) or r.nation)
    # a season pinned by hand (division_overrides.json: "Savoia|1938")
    # (by the source's club name, or by the club's FM26 id: Estrela da
    # Amadora's 2000030636 has no league history and three spellings)
    pinned = (_division_pins().get("%s|%d" % (r.club, r.year))
              or _division_pins().get("%s|%d" % (hit["id"], r.year)))
    if pinned:
        flags.append("%d/%02d %s: division pinned by hand to %s." % (r.year, (r.year + 1) % 100,
                                                                    r.club, pinned))
        return int(pinned)
    # an Unknown Club season in Italy with no level in the source: Italian
    # Lower Division (user, 2026-10-09)
    if unknown and fm_nation(home) == "Italy" and not (r.level and div_ids.get(key)):
        return ITALY_UNKNOWN
    if r.ytht:
        # a youth row carries the competition the club's SENIOR team played
        # that season (user, 2026-10-08: Babalito's Benfica juniors 1972/73 ->
        # Primeira Liga); no source level to fall back on
        divid = None if unknown else fm26_leagues.division(hit["id"], r.year,
                                                           is_calendar_club(hit["id"]))[0]
        return divid or missing_division(home)[0]
    divid, note = ((None, "Unknown Club") if unknown else
                   fm26_leagues.division(hit["id"], r.year, is_calendar_club(hit["id"])))
    if note and divid:
        flags.append(note)
    if divid:
        return divid
    # a season FM26 keeps no league row for, that the source puts in the top
    # flight: the country's top league (user, 2026-10-09: Stelea's Steaua 1995/96)
    if r.level == "I":
        top = top_league(fm_nation(home))
        if top:
            flags.append("%d/%02d %s: no league history row, top flight in the source - "
                         "division set to %s." % (r.year, (r.year + 1) % 100, r.club, top[1]))
            return top[0]
    # a lower level the source names (carrierecalciatori's Serie B/C/D) maps
    # to today's league at that level (levels.json): Montevarchi's Serie C
    # 1929/30 is not the top flight the country default below would give
    lower = div_ids.get(key) if r.level else None
    if lower:
        flags.append("%d/%02d %s: no league history row - division from the source's level %s."
                     % (r.year, (r.year + 1) % 100, r.club, r.level))
        return lower
    # otherwise Portugal's regional divisions, an African country's top league
    # (user, 2026-10-08)
    divid, how = missing_division(home)
    if divid:
        flags.append("%d/%02d %s: no league history row - division set to %s."
                     % (r.year, (r.year + 1) % 100, r.club, how))
        return divid
    fallback = div_ids.get(key) if r.level else None
    flags.append("%d/%02d %s: %s - division %s from the source's level %s."
                 % (r.year, (r.year + 1) % 100, r.club, note,
                    fallback or "left blank", r.level or "(none)"))
    return fallback


def verify_output(path, uid, plhs_rows, spells):
    """Replay the written file: Plhs through probe_editor_replay (the
    editor-faithful reader), Pnph through verify.replay_spells. Every replayed
    row must equal the model's; any op whose snapshot misses is a failure."""
    import probe_editor_replay as per
    import verify
    problems = []
    rows, dropped = per.replay(per.grid(path, [str(uid)], "Plhs"))
    problems += ["Plhs op dropped: %s" % (d,) for d in dropped]
    key = lambda r: (r["year"], r["yror"], r["apps"], r["gols"], bool(r["ytht"]), bool(r["onln"]),
                     fm_names.dbid(_ref_id(r["club"])), _ref_id(r["divi"]),
                     c.dtup(r["join"]) if r["join"] is not None else None,
                     c.dtup(r["leaving"]) if r["leaving"] is not None else None)
    got, want = [key(r) for r in rows], [key(r) for r in plhs_rows]
    # compared as a set: each row carries its year and order, which is all the
    # editor sorts by - two rows FM26 itself numbers alike (Adriano's 2022,
    # both order 0) may replay in either sequence
    if sorted(got, key=repr) != sorted(want, key=repr):
        problems.append("Plhs replay differs from the model:\n  got  %s\n  want %s" % (got, want))
    problems += verify.check_spells(path, uid, c.prop_id("Pnph"), spells)
    lst = ET.parse(path).getroot().find(".//list[@id='db_changes']")
    missing = sum(1 for r in lst if r.find("integer[@id='db_random_id']") is None)
    if missing:
        problems.append("%d changes carry no db_random_id" % missing)
    return {"plhs_rows": len(rows), "spells": len(spells), "changes": len(lst), "problems": problems}


def _ref_id(el):
    """The id inside a club/competition reference element, or None."""
    if el is None:
        return None
    for k in el:
        if k.get("id") in ("Ttea", "competition"):
            return int(k.get("value"))
    return None


class _Namer:
    """Minimal stand-in for fm_names.Names, for repair_type_change.home_grown:
    it only needs `.parent_of` (B-team folding) and `.nation` (a club's own
    country) - the created player's own clubs already carry a resolved id."""
    def __init__(self, club_ids):
        self._n = fm_names.Names(offline=False)

    def parent_of(self, cid):
        return self._n.parent_of(cid)

    def nation(self, cid):
        return self._n.nation(cid)
