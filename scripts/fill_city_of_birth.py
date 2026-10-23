"""Write each rebuilt record's city of birth, read from the release database.

A created record carries no city: the person's own is in FM18's `people_db`,
as a row index into the city table. City DBIDs are stable between editions -
47,524 ids appear in both FM18 and FM26 and Lisboa is 819 in each - so the id
read from FM18 is the id FM26 wants. It is checked against FM26's own table
before it is written, and a city FM26 does not have is skipped rather than
guessed.
"""
import argparse, json, os, random, sys
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fm_db_people import PeopleDB
from fm_db_world import WorldDB, sections, _row_count

PCBI = str(int.from_bytes(b"Pcbi", "big"))
ROW_COL = "1853322860"
BUILD = "3733"
S = 4294967297


def fm26_cities(path):
    """FM26 lays its tables end to end inside one chunked stream, so the city
    names are found by their own row shape rather than by a section boundary."""
    import struct
    buf = b"".join(sections(path))
    def row(p):
        if p + 8 > len(buf):
            return None
        dbid, n = struct.unpack_from("<II", buf, p)
        if not (0 < n <= 64) or p + 10 + n > len(buf) or buf[p + 8 + n:p + 10 + n] != b"\x00\x00":
            return None
        try:
            return dbid, buf[p + 8:p + 8 + n].decode("utf-8"), p + 10 + n
        except UnicodeDecodeError:
            return None
    i = buf.find(b"\x06\x00\x00\x00Lisboa\x00\x00")
    start = i - 4
    while True:
        back = next((b for b in range(9, 80) if (r := row(start - b)) and r[2] == start), None)
        if back is None:
            break
        start -= back
    count = struct.unpack_from("<I", buf, start - 4)[0]
    out, p = {}, start
    for _ in range(count):
        r = row(p)
        if not r:
            break
        out[r[0]] = r[1]
        p = r[2]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--db18", required=True)
    ap.add_argument("--lang26", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log")
    a = ap.parse_args()
    rng = random.Random(20260916)

    people = PeopleDB(a.db18, cache=os.environ.get("FM_PEOPLE_CACHE"))
    world = WorldDB(a.db18)
    known = fm26_cities(a.lang26)
    print("cities FM26 knows: %d" % len(known))

    tree = ET.parse(a.file)
    changes = tree.getroot().find('list[@id="db_changes"]')
    has = set()
    for r in changes:
        if r.find('unsigned[@id="property"]') is not None \
           and r.find('unsigned[@id="property"]').get("value") == PCBI:
            has.add(r.find('large[@id="db_unique_id"]').get("value"))

    ops, log = [], []
    for line in open(a.report, encoding="utf-8"):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) != 6 or not c[2].isdigit() or not c[3].isdigit() or c[2] == c[3]:
            continue
        who, club, old, new = c[0], c[1], int(c[2]) >> 32, c[3]
        rec = people.get(old)
        city = world.city(rec["city_of_birth"]) if rec and rec.get("city_of_birth") is not None else None
        if new in has:
            log.append((who, club, "-", "already stated")); continue
        if not city:
            log.append((who, club, "-", "no city in the database")); continue
        if city["dbid"] not in known:
            log.append((who, club, city["name"], "FM26 does not have that city")); continue
        r = ET.Element("record")
        ET.SubElement(r, "integer", id="database_table_type", value="1")
        ET.SubElement(r, "large", id="db_unique_id", value=new)
        ET.SubElement(r, "unsigned", id="property", value=PCBI)
        nv = ET.SubElement(r, "record", id="new_value")
        ET.SubElement(nv, "unsigned", id="id", value=ROW_COL)
        ET.SubElement(nv, "large", id="city", value=str(city["dbid"] * S))
        ET.SubElement(nv, "integer", id="DBID", value=str(city["dbid"]))
        ET.SubElement(r, "integer", id="version", value=BUILD)
        ET.SubElement(r, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
        ops.append(r)
        log.append((who, club, "%s (%d)" % (city["name"], city["dbid"]), "written"))

    for o in ops:
        changes.append(o)
    tree.write(a.out, encoding="unicode", xml_declaration=False)
    print("cities of birth written: %d of %d records" % (len(ops), len(log)))
    if a.log:
        md = ["# City of birth\n",
              "\nRead from FM18's `people_db` - a row index into the city table - and checked "
              "against FM26's own city table before writing. City ids are stable between "
              "editions: Lisboa is 819 in both.\n",
              "\n| Player | Club | City | Result |", "|---|---|---|---|"]
        for r in sorted(log):
            md.append("| %s | %s | %s | %s |" % r)
        open(a.log, "w", encoding="utf-8").write("\n".join(md) + "\n")
        print("log ->", a.log)


if __name__ == "__main__":
    main()
