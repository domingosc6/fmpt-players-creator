"""Repair the records whose person-type change lands after everything else.

Changing a person's TYPE in the FM26 editor resets his ability and attributes.
The change sits at the end of the file, so every value written earlier - CA, PA,
the attribute block - is lost on import, exactly as a club change resets Date
Joined. The cure is the same one: write those values AGAIN, after it.

The same pass sets home-grown status, which the type change also clears: a club
counts when the player spent three seasons there aged 15 to 21 on 1 July, a B
team counting as its parent, and a nation when three such seasons were spent at
its clubs. A player the rule leaves without a nation takes the one on his record,
or failing that the nation of his first club.
"""
import argparse
import copy
import json
import os
import random
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm_names

PERSON = "1"
ROW_COL = "1853322860"
HG_CLUB_COL = "1668052322"      # "club"
HG_NATION_COL = "1851880553"    # "nati"
HG_ROW_ID = "1869379180"        # the row image an insert starts from
REF_ID = "1986096245"           # a reference payload
HGTY = 1                        # what the author writes on every home-grown row
PLHS_COLS = {"2036687218": "year", "1668049252": "club", "1869507694": "onln",
             "2037672052": "ytht", "1634758771": "apps", "1735355507": "gols"}
PLAYER_TYPE = "2"               # Ptyp: 2 is a player, 1 is not
WINDOW = (15, 21)
SEASONS = 3


def prop_id(name):
    return int.from_bytes(name.encode("latin1"), "big")


def fourcc(n):
    return n.to_bytes(4, "big").decode("latin1")


def is_grid(op):
    """A grid change carries an lsop; a scalar one carries a plain value."""
    nv = op.find('record[@id="new_value"]')
    return nv is not None and nv.find('integer[@id="lsop"]') is not None


def age_on_1_july(dob, season):
    day, month, year = dob
    return season - year - (1 if (month, day) > (7, 1) else 0)


def scan(path, props_wanted):
    """One pass: the last write of every property per record, the career, and
    which records already carry home-grown rows of their own."""
    last = {}          # uid -> prop -> (position, op element)
    career = {}        # uid -> rows as the file finally leaves them
    had = {}           # uid -> {"Phgc","Phgn"} already present
    pos = 0
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag != "record" or el.get("id") is not None:
            continue
        tt = el.find('integer[@id="database_table_type"]')
        uid = el.find('large[@id="db_unique_id"]')
        pid = el.find('unsigned[@id="property"]')
        if tt is None or uid is None or pid is None or tt.get("value") != PERSON:
            el.clear()
            continue
        pos += 1
        u, name = uid.get("value"), fourcc(int(pid.get("value")))
        if name == "Plhs":
            st = career.setdefault(u, {"rows": [], "cur": None})
            nv = el.find('record[@id="new_value"]')
            if nv is not None:
                cid = nv.find('unsigned[@id="id"]')
                ls = nv.find('integer[@id="lsop"]')
                cid = cid.get("value") if cid is not None else None
                ls = ls.get("value") if ls is not None else None
                if ls == "3":
                    st["rows"], st["cur"] = [], None
                elif ls == "0":
                    if st["cur"]:
                        st["rows"].append(st["cur"])
                    st["cur"] = {}
                elif ls == "1" and st["cur"] is not None:
                    v = nv.find('*[@id="value"]')
                    col = PLHS_COLS.get(cid)
                    if col and v is not None:
                        if v.tag == "record":
                            t = v.find('*[@id="Ttea"]')
                            if t is not None:
                                st["cur"][col] = t.get("value")
                        else:
                            st["cur"][col] = v.get("value")
        if name in ("Phgc", "Phgn"):
            nv = el.find('record[@id="new_value"]')
            ls = nv.find('integer[@id="lsop"]') if nv is not None else None
            if ls is not None and ls.get("value") == "0":
                had.setdefault(u, set()).add(name)
        if name in props_wanted or name == "Ptyp":
            last.setdefault(u, {})[name] = (pos, copy.deepcopy(el))
        el.clear()
    for st in career.values():
        if st["cur"]:
            st["rows"].append(st["cur"])
            st["cur"] = None
    return last, {u: st["rows"] for u, st in career.items()}, had


def wrap(uid, name, new_value, build, rng):
    rec = ET.Element("record")
    ET.SubElement(rec, "integer", id="database_table_type", value=PERSON)
    ET.SubElement(rec, "large", id="db_unique_id", value=uid)
    ET.SubElement(rec, "unsigned", id="property", value=str(prop_id(name)))
    rec.append(new_value)
    ET.SubElement(rec, "integer", id="version", value=str(build))
    ET.SubElement(rec, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    return rec


def hg_ops(uid, grid, col, ref_key, refs, build, rng):
    """Clear the grid and write one row per club (or nation). Nothing to write
    means nothing to say: an empty rule result leaves the record's own grid
    alone rather than emptying it."""
    if not refs:
        return []
    ops = []
    nv = ET.Element("record", id="new_value")
    ET.SubElement(nv, "unsigned", id="id", value=ROW_COL)
    ET.SubElement(nv, "integer", id="lsop", value="3")
    ops.append(wrap(uid, grid, nv, build, rng))
    for dbid in refs:
        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=ROW_COL)
        ET.SubElement(nv, "integer", id="lsop", value="0")
        ops.append(wrap(uid, grid, nv, build, rng))

        nv = ET.Element("record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=col)
        v = ET.SubElement(nv, "record", id="value")
        ET.SubElement(v, "unsigned", id="id", value=REF_ID)
        ET.SubElement(v, "large", id=ref_key, value=str(int(dbid) * fm_names.UID_SCALE))
        ET.SubElement(v, "integer", id="DBID", value=str(dbid))
        ET.SubElement(nv, "integer", id="lsop", value="1")
        o = ET.SubElement(nv, "record", id="olvl")
        ET.SubElement(o, "unsigned", id="id", value=HG_ROW_ID)
        ET.SubElement(o, "integer", id="hgty", value=str(HGTY))
        ET.SubElement(o, "null", id="club" if ref_key == "Cclu" else "nation")
        ops.append(wrap(uid, grid, nv, build, rng))
    return ops


def home_grown(rows, dob, namer, fallback):
    """(club DBIDs, nation NAMES, fell_back) the career earns."""
    if not rows or not dob:
        return [], ([fallback] if fallback else []), bool(fallback)
    clubs, nations = {}, {}
    for r in rows:
        if not r.get("club"):
            continue
        if not WINDOW[0] <= age_on_1_july(dob, int(r["year"])) <= WINDOW[1]:
            continue
        # A B team is the club itself for this purpose. Both sides have to be
        # the same KIND of id first: the rows carry DBIDs and parent_of answers
        # with a unique id, so Porto B and Porto never met.
        k = fm_names.dbid(namer.parent_of(r["club"]) or r["club"]) or r["club"]
        clubs[str(k)] = clubs.get(str(k), 0) + 1
        nat = namer.nation(r["club"])
        if nat:
            nations[nat] = nations.get(nat, 0) + 1
    ok_clubs = [int(c) for c, n in sorted(clubs.items()) if n >= SEASONS and c.isdigit()]
    ok_nations = sorted(n for n, k in nations.items() if k >= SEASONS)
    fell_back = not ok_nations and bool(fallback)
    if fell_back:
        ok_nations = [fallback]
    return [c for c in ok_clubs if c], ok_nations, fell_back


def nation_name_of(dbid_):
    """The nation's name, for a report line that only has its id."""
    import urllib.request
    url = (fm_names.HOST + "/collections/detailed_game_items/documents/search"
           "?q=*&query_by=&filter_by=type_id:=nation%%20%%26%%26%%20fm_id:=%d"
           "&x-typesense-api-key=%s" % (dbid_, fm_names.KEY))
    req = urllib.request.Request(url, headers={"User-Agent": "fmpt-legends/1.0"})
    try:
        hits = json.load(urllib.request.urlopen(req, timeout=30)).get("hits") or []
    except Exception:
        return None
    return hits[0]["document"]["name"] if hits else None


def nation_ids(names):
    """nation name -> DBID. The cache keeps nations by name, the grid needs the
    id, and there are only a handful per file.

    The index holds two nations per name, a men's and a women's, and only the
    men's one is the nation FM's clubs and players point at: Portugal is 788,
    not the 2000169644 the women's record carries. Ask for the men's, and for
    the name as written."""
    import urllib.parse
    import urllib.request
    out = {}
    for name in sorted(set(n for n in names if n)):
        url = (fm_names.HOST + "/collections/detailed_game_items/documents/search"
               "?q=%s&query_by=name&filter_by=type_id:=nation%%20%%26%%26%%20gender:=mens"
               "&per_page=5&x-typesense-api-key=%s"
               % (urllib.parse.quote(name), fm_names.KEY))
        req = urllib.request.Request(url, headers={"User-Agent": "fmpt-legends/1.0"})
        try:
            hits = json.load(urllib.request.urlopen(req, timeout=30)).get("hits") or []
        except Exception:
            hits = []
        for h in hits:
            d = h["document"]
            if d.get("name") == name and d.get("fm_id", "").isdigit():
                out[name] = int(d["fm_id"])
                break
    return out


def insert_before_close(text, block):
    """Put the new changes at the very end of db_changes - the last write wins."""
    open_tag = '<list id="db_changes">'
    i = text.index(open_tag) + len(open_tag)
    depth = 1
    while depth:
        o, c = text.find("<list", i), text.find("</list>", i)
        if c < 0:
            raise ValueError("db_changes is not closed")
        if 0 <= o < c:
            end = text.index(">", o)
            i = end + 1
            if text[end - 1] != "/":      # a self-closing list opens nothing
                depth += 1
            continue
        depth -= 1
        if depth == 0:
            return text[:c] + block + text[c:]
        i = c + len("</list>")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--report", metavar="FILE.md")
    ap.add_argument("--no-home-grown", action="store_true")
    args = ap.parse_args(argv)

    namer = fm_names.Names()
    # Every scalar the file writes - those are what a type change resets. A
    # property that appears ONCE as a grid op is a grid whatever else it looks
    # like: re-emitting a single row op would graft a stray row onto a career.
    scalar, grid = set(), set()
    for _, el in ET.iterparse(args.input, events=("end",)):
        if el.tag != "record" or el.get("id") is not None:
            continue                      # a nested record is part of its parent
        pid = el.find('unsigned[@id="property"]')
        tt = el.find('integer[@id="database_table_type"]')
        if pid is not None and tt is not None and tt.get("value") == PERSON:
            (grid if is_grid(el) else scalar).add(fourcc(int(pid.get("value"))))
        el.clear()
    props = scalar - grid
    print("scalar properties re-emitted: %d (grid properties skipped: %d)" % (len(props), len(grid)))
    last, careers, had = scan(args.input, props)

    def final_type(d):
        v = d["Ptyp"][1].find('*[@id="new_value"]')
        return v.get("value") if v is not None else None

    at_risk = {u: d for u, d in last.items()
               if "Ptyp" in d and any(p != "Ptyp" and v[0] < d["Ptyp"][0] for p, v in d.items())}
    # Ptyp 2 is a player, 1 is not. A record the author turns INTO a non-player
    # has no ability, no player attributes and no home-grown status to lose, so
    # it is left alone (Mario Wilson, Candido Rego, Vitor Manuel are coaches).
    victims = {u: d for u, d in at_risk.items() if final_type(d) == PLAYER_TYPE}
    print("records whose type change lands after other changes: %d (%d of them end as "
          "non-players and are left alone)" % (len(victims), len(at_risk) - len(victims)))

    clubs = {r["club"] for u in victims for r in careers.get(u, []) if r.get("club")}
    namer.fetch([("team", fm_names.dbid(c)) for c in clubs])
    namer.fetch([("person", fm_names.dbid(u)) for u in victims])
    nat_id = {} if args.no_home_grown else nation_ids(
        [namer.nation(c) for c in clubs] + [namer.person_nation(u) for u in victims])
    nat_by_id = {}                       # ids the file names directly, resolved below
    nat_name = {"#%s" % i: n for n, i in nat_id.items()}

    def nation_label(tag):
        """'#788' is a nation the FILE names by id; give it its real name."""
        if not tag.startswith("#") or tag in nat_name:
            return nat_name.get(tag, tag)
        name = fm_names.Names.__module__ and None
        got = nation_name_of(int(tag[1:]))
        nat_name[tag] = got or tag
        return nat_name[tag]

    def label(uid, d):
        """The index knows the real records; a created one is named in the file."""
        known = namer.person(uid)
        if known:
            return known
        parts = []
        for prop in ("Pfna", "Psna"):
            if prop in d:
                v = d[prop][1].find('string[@id="new_value"]')
                if v is not None and v.get("value"):
                    parts.append(v.get("value"))
        if not parts and "Pcna" in d:
            v = d["Pcna"][1].find('string[@id="new_value"]')
            if v is not None and v.get("value"):
                parts.append(v.get("value"))
        return " ".join(parts) or uid

    rng = random.Random(20260916)
    build = 3733
    new_ops, lines = [], []
    for u, d in sorted(victims.items(), key=lambda kv: label(kv[0], kv[1])):
        cut = d["Ptyp"][0]
        redo = [(p, v[1]) for p, v in sorted(d.items()) if p != "Ptyp" and v[0] < cut]
        for name, op in redo:
            nv = op.find('*[@id="new_value"]')
            if nv is not None:
                new_ops.append(wrap(u, name, copy.deepcopy(nv), build, rng))
        row = [label(u, d), u, str(len(redo)), "-", "-", "-", "-"]
        rows = careers.get(u, [])
        if not args.no_home_grown and rows:
            dob = None
            if "Pdob" in d:
                v = d["Pdob"][1].find('date[@id="new_value"]')
                if v is not None:
                    dob = (int(v.get("day")), int(v.get("month")), int(v.get("year")))
            # his own nation: what the file says, else what the index knows, else
            # the nation of the first club he played for
            born, src = None, ""
            if "Pnti" in d:                       # the file states his nation
                v = d["Pnti"][1].find('*[@id="new_value"]')
                t = v.find('*[@id="Nnat"]') if v is not None and v.tag == "record" else None
                if t is not None and fm_names.dbid(t.get("value")):
                    nat_by_id.setdefault(fm_names.dbid(t.get("value")), None)
                    born, src = ("#%s" % fm_names.dbid(t.get("value"))), "file"
            # Then the career. The index's nationality for a record describes
            # whoever FM has there NOW, not the legend written over him: it calls
            # Cassio Portuguese because the record it sits on plays in the
            # Portuguese third division, while his career is entirely Brazilian.
            first = sorted([r for r in rows if r.get("club")], key=lambda r: int(r["year"]))
            if born is None and first:
                born = namer.nation(first[0]["club"])
                src = "first club" if born else ""
            if born is None:
                born = namer.person_nation(u)     # last resort: the record itself
                src = "record" if born else ""
            cl, na, fell_back = home_grown(rows, dob, namer, born)
            ids = [int(n[1:]) if n.startswith("#") else nat_id[n] for n in na
                   if n.startswith("#") or n in nat_id]
            new_ops += hg_ops(u, "Phgc", HG_CLUB_COL, "Cclu", cl, build, rng)
            new_ops += hg_ops(u, "Phgn", HG_NATION_COL, "Nnat", ids, build, rng)
            row[3] = ", ".join(namer.club(str(int(c) * fm_names.UID_SCALE)) or str(c) for c in cl) or "-"
            row[4] = ", ".join(nation_label(n) for n in na) or "-"
            row[5] = (src or "-") if fell_back else "rule"
            mine_before = had.get(u, set())
            fresh = [g for g, got in (("club", cl), ("nation", ids))
                     if got and ("Phgc" if g == "club" else "Phgn") not in mine_before]
            row[6] = " + ".join(fresh) or "-"
        lines.append(row)

    block = "".join("\n\t\t" + ET.tostring(o, encoding="unicode") for o in new_ops) + "\n\t"
    text = open(args.input, encoding="utf-8").read()
    open(args.output, "w", encoding="utf-8").write(insert_before_close(text, block))
    print("changes appended: %d -> %s" % (len(new_ops), args.output))

    if args.report:
        out = ["# Repair after a person-type change\n",
               "\nSource: `%s`\n" % os.path.basename(args.input),
               "\nA type change resets a person's ability and attributes, and it sits at the end of "
               "the file, so everything written earlier is lost on import. Those values are written "
               "again after it, and the home-grown grids are rebuilt from the career: three seasons "
               "at a club aged 15 to 21 on 1 July, a B team counting as its parent; three such "
               "seasons at a nation's clubs for the nation. A player the rule leaves without a "
               "nation takes the one on his record, else the nation of his first club.\n",
               "\n| Player | Record id | Values rewritten | Home grown club | Home grown nation | Nation from | New |",
               "|---|---|---|---|---|---|---|"]
        for r in lines:
            out.append("| %s | %s | %s | %s | %s | %s | %s |" % tuple(r))
        open(args.report, "w", encoding="utf-8").write("\n".join(out) + "\n")
        print("report -> %s" % args.report)


if __name__ == "__main__":
    main()
