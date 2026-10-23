"""Rebuild the records whose person FM26 no longer has, into a file of their own.

Three things happen here, and only these:

  new     the person is gone from FM26's database, so his changes are copied
          onto a FRESH created id and an ADDR row registers that person. The
          old id is left alone - it imports against nothing either way.
  reemit  the person is still in FM26 but the record was lost from the project
          files, so his changes go back on his OWN id, unchanged.
  type    one re-emit also needs a non-player -> player change, which the
          author asked for by hand.

The FM18-sourced records go through convert_edition.py first, the same way
every other record in the deliverable did, so their years land on the same
season. The output is a standalone changeset, meant to be merged in the editor.
"""
import argparse, copy, json, os, random, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fm_names

S = fm_names.UID_SCALE
ADDR_PROP = "1094992978"
ROW_COL = "1853322860"
BUILD = "3733"
PTYP = str(int.from_bytes(b"Ptyp", "big"))
PLAYER, NON_PLAYER = "2", "1"
TARGET_SEASON = "2025"


def records_for(path, uids):
    """Every change in a file that belongs to one of these people."""
    out = {u: [] for u in uids}
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag != "record" or el.get("id") is not None:
            continue
        u = el.find('large[@id="db_unique_id"]')
        if u is not None and u.get("value") in out:
            out[u.get("value")].append(copy.deepcopy(el))
        el.clear()
    return out


def convert(src_path, uids, workdir):
    """Pull these people out of an older file and run them to the target season."""
    text = open(src_path, encoding="utf-8").read()
    head = text[:text.index("<list id=\"db_changes\">") + len("<list id=\"db_changes\">")]
    tail = text[text.rindex("</list>"):]
    recs = records_for(src_path, uids)
    body = "".join("\n\t\t" + ET.tostring(r, encoding="unicode")
                   for u in uids for r in recs[u])
    mini = os.path.join(workdir, "mini.xml")
    done = os.path.join(workdir, "mini-converted.xml")
    open(mini, "w", encoding="utf-8").write(head + body + "\n\t" + tail)
    r = subprocess.run([sys.executable, os.path.join(HERE, "convert_edition.py"),
                        mini, done, "--target-season", TARGET_SEASON,
                        # these records edit a career the created person will not have:
                        # replay them into a clear-and-insert the empty grid can accept
                        "--rebuild-real-history"],
                       capture_output=True, text=True)
    if r.returncode or not os.path.exists(done):
        raise SystemExit("convert_edition failed:\n" + r.stdout + r.stderr)
    print(r.stdout.strip())
    return records_for(done, uids)


def addr_row(uid, rng):
    """Register a created person. The working file writes dcty 2 and no nwui."""
    rec = ET.Element("record")
    ET.SubElement(rec, "integer", id="database_table_type", value="55")
    ET.SubElement(rec, "large", id="db_unique_id", value=str(S))
    ET.SubElement(rec, "unsigned", id="property", value=ADDR_PROP)
    nv = ET.SubElement(rec, "record", id="new_value")
    ET.SubElement(nv, "unsigned", id="id", value=ROW_COL)
    ET.SubElement(nv, "integer", id="database_table_type", value="1")
    ET.SubElement(nv, "unsigned", id="dcty", value="2")
    ET.SubElement(nv, "large", id="db_unique_id", value=str(uid))
    ET.SubElement(rec, "integer", id="version", value=BUILD)
    ET.SubElement(rec, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    ET.SubElement(rec, "boolean", id="is_client_field", value="true")
    return rec


def type_change(uid, rng):
    rec = ET.Element("record")
    ET.SubElement(rec, "integer", id="database_table_type", value="1")
    ET.SubElement(rec, "large", id="db_unique_id", value=str(uid))
    ET.SubElement(rec, "unsigned", id="property", value=PTYP)
    ET.SubElement(rec, "integer", id="new_value", value=PLAYER)
    ET.SubElement(rec, "integer", id="version", value=BUILD)
    ET.SubElement(rec, "integer", id="db_random_id", value=str(rng.randint(1, 2 ** 31 - 1)))
    ET.SubElement(rec, "integer", id="odvl", value=NON_PLAYER)
    return rec


def free_ids(count, used_hi, used_lo, db, rng):
    """New created ids. The high word must not name a person FM26 already has,
    and neither half may repeat one the working file uses. nwui stays under the
    signed boundary - past it, records break outright."""
    import struct
    hi, lo, out = 900_000_001, 2_002_100_000, []
    while len(out) < count:
        while hi in used_hi or db.find(struct.pack("<II", hi, hi)) >= 0:
            hi += 1
        while lo in used_lo:
            lo += 1
        if lo >= 2 ** 31:
            raise SystemExit("ran out of nwui room below the signed boundary")
        out.append((hi << 32) | lo)
        used_hi.add(hi); used_lo.add(lo)
        hi += 1; lo += 1
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True)
    ap.add_argument("--fm26", required=True)
    ap.add_argument("--fm18", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    a = ap.parse_args()

    work = json.load(open(a.work, encoding="utf-8"))
    db = open(os.path.join(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work"), "basic_people_db.dat.bin"), "rb").read()
    rng = random.Random(20260916)

    fm26_uids = [w["uid"] for w in work if w["src"] == "fm26"]
    fm18_uids = [w["uid"] for w in work if w["src"] == "fm18"]
    src = records_for(a.fm26, fm26_uids)
    tmp = os.path.join(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work"), "conv")
    os.makedirs(tmp, exist_ok=True)
    src.update(convert(a.fm18, fm18_uids, tmp))

    used_hi, used_lo = set(), set()
    for _, el in ET.iterparse(a.fm26, events=("end",)):
        if el.tag == "record" and el.get("id") is None:
            u = el.find('large[@id="db_unique_id"]')
            if u is not None:
                n = int(u.get("value"))
                used_hi.add(n >> 32); used_lo.add(n & 0xffffffff)
        el.clear()
    fresh = free_ids(sum(1 for w in work if w["action"] == "new"), used_hi, used_lo, db, rng)

    out, lines, i = [], [], 0
    for w in sorted(work, key=lambda w: (w["club"], w["name"])):
        got = src.get(w["uid"]) or []
        if not got:
            lines.append((w["name"], w["club"], w["uid"], "-", 0, "NO CHANGES FOUND"))
            continue
        if w["action"] == "new":
            uid = fresh[i]; i += 1
            out.append(addr_row(uid, rng))
        else:
            uid = int(w["uid"])
        for r in got:
            r = copy.deepcopy(r)
            r.find('large[@id="db_unique_id"]').set("value", str(uid))
            out.append(r)
        if w.get("type_change"):
            out.append(type_change(uid, rng))
        lines.append((w["name"], w["club"], w["uid"], str(uid), len(got),
                      "new record" + (" + type change" if w.get("type_change") else "")
                      if w["action"] == "new" else
                      "re-emitted on his own id" + (" + type change" if w.get("type_change") else "")))

    text = open(a.fm26, encoding="utf-8").read()
    open_tag = '<list id="db_changes">'
    head = text[:text.index(open_tag) + len(open_tag)]
    tail = text[text.rindex("</list>"):]
    body = "".join("\n\t\t" + ET.tostring(r, encoding="unicode") for r in out)
    open(a.out, "w", encoding="utf-8").write(head + body + "\n\t" + tail)
    print("records written: %d for %d people -> %s" % (len(out), len(lines), a.out))

    if a.report:
        md = ["# Rebuilt records\n",
              "\nOne file, nothing else in it: the people whose FM26 person is gone got their changes "
              "copied onto a fresh created id with an ADDR row to register them; the two whose person "
              "is still there got theirs back on their own id. FM18-sourced records were run through "
              "`convert_edition.py --target-season %s` first.\n" % TARGET_SEASON,
              "\n| Player | Club | Old record | New record | Changes | What happened |", "|---|---|---|---|---|---|"]
        for r in sorted(lines):
            md.append("| %s | %s | %s | %s | %d | %s |" % r)
        open(a.report, "w", encoding="utf-8").write("\n".join(md) + "\n")
        print("report ->", a.report)


if __name__ == "__main__":
    main()
