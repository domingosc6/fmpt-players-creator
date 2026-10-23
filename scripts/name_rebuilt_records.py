"""Give the rebuilt records a name and a nationality.

A record that adapts a person FM ships needs neither: the name and the passport
are the database's. Copy that record onto a created id and both are gone, so
they have to be written.

The name comes from the FM search index behind fmref, which holds the person's
common name and, among its search terms, his full one - "Beto" and "Antonio
Alberto Bastos Pimparel". The nationality comes from the SHEET, because the
index's `nation` on a person is the country of the club he plays in today, not
his passport: it calls Modou Sougou French for playing at Amiens.
"""
import argparse, json, os, random, re, sys, unicodedata, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm_names

S = fm_names.UID_SCALE
BUILD = "3733"
ROW_COL = "1853322860"
REF_ID = "1986096245"
P = {k: str(int.from_bytes(k.encode(), "big"))
     for k in ("Pfna", "Psna", "Pcna", "Pfln", "Pnti", "P2ni")}


def search(filt, by="", q="*", n=50):
    url = (fm_names.HOST + "/collections/detailed_game_items/documents/search?q=%s&query_by=%s"
           "&filter_by=%s&per_page=%d&x-typesense-api-key=%s"
           % (urllib.parse.quote(q), by, urllib.parse.quote(filt), n, fm_names.KEY))
    req = urllib.request.Request(url, headers={"User-Agent": "fmpt-legends/1.0"})
    try:
        return [h["document"] for h in json.load(urllib.request.urlopen(req, timeout=30)).get("hits") or []]
    except Exception:
        return []


def people(dbids):
    out = {}
    ids = sorted(set(int(d) for d in dbids))
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        for d in search("type_id:=person && fm_id:=[%s]" % ",".join(map(str, chunk))):
            out[int(d["fm_id"])] = d
    return out


def nations(codes):
    """A three-letter country code is one of the nation's own search terms."""
    out = {}
    for c in sorted(set(codes)):
        hits = search("type_id:=nation && gender:=mens", by="search_terms", q=c.lower(), n=5)
        for d in hits:
            if c.lower() in [t.lower() for t in d.get("search_terms") or []] and d["fm_id"].isdigit():
                out[c] = (int(d["fm_id"]), d["name"])
                break
    return out


def split_name(doc):
    """Common name, and the full name the index keeps among its search terms."""
    common = doc.get("name") or ""
    # the index keeps lowercased duplicates of every term; they are for searching,
    # not for writing into a name field
    terms = [t for t in doc.get("search_terms") or [] if " " in t and t != t.lower()]
    full = max(terms, key=len) if terms else common
    parts = full.split()
    return (parts[0] if parts else common), (" ".join(parts[1:]) if len(parts) > 1 else ""), common


def string_op(uid, prop, value, rng):
    rec = ET.Element("record")
    ET.SubElement(rec, "integer", id="database_table_type", value="1")
    ET.SubElement(rec, "large", id="db_unique_id", value=str(uid))
    ET.SubElement(rec, "unsigned", id="property", value=P[prop])
    ET.SubElement(rec, "string", id="new_value", value=value)
    ET.SubElement(rec, "integer", id="version", value=BUILD)
    ET.SubElement(rec, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    ET.SubElement(rec, "string", id="odvl", value="")
    ET.SubElement(rec, "boolean", id="is_language_field", value="true")
    return rec


def nation_op(uid, dbid, rng):
    rec = ET.Element("record")
    ET.SubElement(rec, "integer", id="database_table_type", value="1")
    ET.SubElement(rec, "large", id="db_unique_id", value=str(uid))
    ET.SubElement(rec, "unsigned", id="property", value=P["Pnti"])
    nv = ET.SubElement(rec, "record", id="new_value")
    ET.SubElement(nv, "unsigned", id="id", value=ROW_COL)
    ET.SubElement(nv, "large", id="Nnat", value=str(dbid * S))
    ET.SubElement(nv, "integer", id="DBID", value=str(dbid))
    ET.SubElement(rec, "integer", id="version", value=BUILD)
    ET.SubElement(rec, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    return rec


def second_nation_op(uid, dbid, rng):
    rec = ET.Element("record")
    ET.SubElement(rec, "integer", id="database_table_type", value="1")
    ET.SubElement(rec, "large", id="db_unique_id", value=str(uid))
    ET.SubElement(rec, "unsigned", id="property", value=P["P2ni"])
    nv = ET.SubElement(rec, "record", id="new_value")
    ET.SubElement(nv, "unsigned", id="id", value=ROW_COL)
    ET.SubElement(nv, "integer", id="lsop", value="0")
    v = ET.SubElement(nv, "record", id="value")
    ET.SubElement(v, "unsigned", id="id", value=REF_ID)
    ET.SubElement(v, "integer", id="Nnat", value=str(dbid))
    ET.SubElement(rec, "integer", id="version", value=BUILD)
    ET.SubElement(rec, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    return rec


def rows_of(path):
    for line in open(path, encoding="utf-8"):
        if line.startswith("| ") and not line.startswith("|---"):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) >= 5 and c[2].isdigit():
                yield c


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--report", required=True)     # the rebuild report: player, club, old, new
    ap.add_argument("--sheet", required=True)      # the typed sheet list, for Pais
    ap.add_argument("--out", required=True)
    ap.add_argument("--log")
    a = ap.parse_args()
    rng = random.Random(20260916)

    built = [(c[0], c[1], c[2], c[3]) for c in rows_of(a.report)]   # name, club, old, new
    pais, club = {}, None
    for line in open(a.sheet, encoding="utf-8"):
        if line.startswith("## "):
            club = re.sub(r"\s*\(\d+\)\s*$", "", line[3:]).strip()
        elif line.startswith("| ") and not line.startswith(("|---", "| Club")):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) >= 3:
                pais[(c[0], c[2])] = None          # club, player - filled from the squad sheet below
    squad, club = {}, None
    for line in open("FM 26 XML Files/explanations/Primeira Liga Historica - non-bold main team.md",
                     encoding="utf-8"):
        if line.startswith("## "):
            club = re.sub(r"\s*_\(.*", "", line[3:]).strip()
        elif line.startswith("| ") and not line.startswith(("|---", "| Posição")):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) == 3:
                squad[(club, c[1])] = c[2]

    # what the file already says, so nothing is written twice
    tree = ET.parse(a.file)
    changes = tree.getroot().find('list[@id="db_changes"]')
    has = {}
    for r in changes:
        tt = r.find('integer[@id="database_table_type"]')
        if tt is None or tt.get("value") != "1":
            continue
        u = r.find('large[@id="db_unique_id"]').get("value")
        has.setdefault(u, set()).add(r.find('unsigned[@id="property"]').get("value"))

    created = [b for b in built if b[2] != b[3]]
    docs = people(int(o) >> 32 for _, _, o, _ in created)
    codes = [p for b in created for p in (squad.get((b[1], b[0])) or "").split("/") if p]
    nat = nations(codes)

    new_ops, log = [], []
    for name, cl, old, new in created:
        dbid = int(old) >> 32
        d = docs.get(dbid)
        got = has.get(new, set())
        wrote = []
        if d:
            first, last, common = split_name(d)
            # each field on its own: a record may carry a common name from the
            # old file and still have no first or second name of its own
            for prop, value in (("Pfna", first), ("Psna", last), ("Pcna", common),
                                ("Pfln", (first + " " + last).strip())):
                if value and P[prop] not in got:
                    new_ops.append(string_op(new, prop, value, rng))
                    wrote.append({"Pfna": "first", "Psna": "second",
                                  "Pcna": "common", "Pfln": "full"}[prop])
            shown = "%s %s%s" % (first, last, " (%s)" % common if common else "")
        else:
            shown = "NOT IN THE INDEX"
        cs = [c for c in (squad.get((cl, name)) or "").split("/") if c in nat]
        if cs and P["Pnti"] not in got:
            new_ops.append(nation_op(new, nat[cs[0]][0], rng)); wrote.append("nation")
            for extra in cs[1:]:
                new_ops.append(second_nation_op(new, nat[extra][0], rng)); wrote.append("2nd nation")
        log.append((name, cl, new, shown, " / ".join(nat[c][1] for c in cs) or "-",
                    ", ".join(wrote) or "already had them"))

    for op in new_ops:
        changes.append(op)
    tree.write(a.out, encoding="unicode", xml_declaration=False)
    print("name and nationality changes added: %d -> %s" % (len(new_ops), a.out))
    if a.log:
        md = ["# Names and nationalities for the rebuilt records\n",
              "\nA created record carries no name and no passport of its own. The name comes from the "
              "FM search index, the nationality from the sheet's `Pais` column - the index's `nation` "
              "on a person is the country of his current club, not his passport.\n",
              "\n| Player | Club | Record | Name written | Nationality | Fields |", "|---|---|---|---|---|---|"]
        for r in sorted(log):
            md.append("| %s | %s | %s | %s | %s | %s |" % r)
        open(a.log, "w", encoding="utf-8").write("\n".join(md) + "\n")
        print("log ->", a.log)


if __name__ == "__main__":
    main()
