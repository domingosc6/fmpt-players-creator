"""Give the rebuilt records the attributes their person had in FM18.

A record that adapts a person FM ships only carries the attributes the author
CHANGED; the rest were the database's and are lost the moment the record is
copied onto a created id. Those values still exist in the release database, so
read them from there and write the ones the record does not already state.

The FourCC for each attribute is not assumed. It is learned from the author's
own file: for every PD** change, the FIRST `odvl` on that person and property
is the value FM18 shipped, and the decoded attribute that keeps agreeing with
it is the one that FourCC names. That resolves all 62 one to one, including the
three that are easy to guess wrong - PDcs is corners, PDcy consistency, PDlf
and PDri the feet, not loyalty and rushing out.

Values are written in whatever shape the source file uses for that property,
integer or string, rather than a shape of our choosing.
"""
import argparse, collections, json, os, random, sys
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fm_db_people import PeopleDB

BUILD = "3733"
S = 4294967297


def fourcc(n):
    return n.to_bytes(4, "big").decode("latin1")


def prop_id(name):
    return str(int.from_bytes(name.encode("latin1"), "big"))


def learn_shapes(path, wanted):
    """How the file writes each property's value: <integer> or <string>."""
    shape = {}
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == "record" and el.get("id") is None:
            p = el.find('unsigned[@id="property"]')
            if p is not None and p.get("value") in wanted and p.get("value") not in shape:
                nv = el.find('*[@id="new_value"]')
                if nv is not None and nv.tag in ("integer", "string"):
                    shape[p.get("value")] = nv.tag
        el.clear()
    return shape


def op(uid, pid, value, tag, rng):
    rec = ET.Element("record")
    ET.SubElement(rec, "integer", id="database_table_type", value="1")
    ET.SubElement(rec, "large", id="db_unique_id", value=str(uid))
    ET.SubElement(rec, "unsigned", id="property", value=pid)
    ET.SubElement(rec, tag, id="new_value", value=str(value))
    ET.SubElement(rec, "integer", id="version", value=BUILD)
    ET.SubElement(rec, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--report", required=True)      # rebuild report: name, club, old id, new id
    ap.add_argument("--map", required=True)         # FourCC -> attribute name
    ap.add_argument("--db", required=True)          # the FM18 1800_fm directory
    ap.add_argument("--source", required=True)      # a file that shows each property's shape
    ap.add_argument("--out", required=True)
    ap.add_argument("--log")
    a = ap.parse_args()
    rng = random.Random(20260916)

    names = json.load(open(a.map))
    pid_of = {n: prop_id(f) for f, n in names.items()}
    shape = learn_shapes(a.source, set(pid_of.values()))
    db = PeopleDB(a.db, cache=os.environ.get("FM_PEOPLE_CACHE"))

    built = []
    for line in open(a.report, encoding="utf-8"):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 5 and c[2].isdigit() and c[3].isdigit() and c[2] != c[3]:
            built.append((c[0], c[1], int(c[2]) >> 32, c[3]))   # name, club, old DBID, new uid

    tree = ET.parse(a.file)
    changes = tree.getroot().find('list[@id="db_changes"]')
    has = collections.defaultdict(set)
    for r in changes:
        tt = r.find('integer[@id="database_table_type"]')
        if tt is not None and tt.get("value") == "1":
            has[r.find('large[@id="db_unique_id"]').get("value")].add(
                r.find('unsigned[@id="property"]').get("value"))

    ops, log = [], []
    for who, club, dbid, uid in built:
        rec = db.get(dbid)
        if not rec:
            log.append((who, club, uid, 0, 0, "not in the FM18 database"))
            continue
        vals = dict(rec.get("attributes") or {})
        vals.update(rec.get("personality") or {})
        before = len([p for p in has[uid] if fourcc(int(p)) in names])
        n = 0
        for name, v in sorted(vals.items()):
            pid = pid_of.get(name)
            if not pid or pid in has[uid] or v is None:
                continue
            ops.append(op(uid, pid, v, shape.get(pid, "integer"), rng))
            n += 1
        log.append((who, club, uid, before, n, "filled" if n else "already complete"))

    for o in ops:
        changes.append(o)
    tree.write(a.out, encoding="unicode", xml_declaration=False)
    print("attribute changes added: %d across %d records -> %s" % (len(ops), len(built), a.out))

    if a.log:
        md = ["# Attributes filled from the FM18 database\n",
              "\nA created record keeps only the attributes the author changed. The rest are read "
              "back from FM18's own `people_db.dat` and written, so the person arrives whole. "
              "Nothing the record already states is touched.\n",
              "\n| Player | Club | Record | Had | Filled | Result |", "|---|---|---|---|---|---|"]
        for r in sorted(log):
            md.append("| %s | %s | %s | %d | %d | %s |" % r)
        open(a.log, "w", encoding="utf-8").write("\n".join(md) + "\n")
        print("log ->", a.log)


if __name__ == "__main__":
    main()
