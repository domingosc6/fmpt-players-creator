"""Take the youth tick off a season the player was too old to be a youth in.

The author's rule: a season with no appearances and no goals, after the player
turned 19, is not a youth season. The existing untick in convert_edition.py only
catches a ticked season that HAS figures, so a blank one - Quim's 2021/22 at
Vitoria, sitting between two full seasons - kept its tick.

A tick is removed the way the editor removes one: the op that set it is copied,
its value flipped to false, and its `olvl` snapshot updated to say the row now
carries the tick, because that is the state the copy has to match. Appended at
the end, where the last change on a cell wins.
"""
import argparse, copy, os, random, sys
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repair_type_change as R

PLHS = str(int.from_bytes(b"Plhs", "big"))
YTHT = "2037672052"
BUILD = "3733"
CUTOFF = 19


def age_on_1_july(dob, season):
    day, month, year = dob
    return season - year - (1 if (month, day) > (7, 1) else 0)


def wanted(path):
    """(uid, season) for every tick the rule takes off."""
    last, careers, _ = R.scan(path, {"Pdob"})
    out, no_dob = set(), 0
    for uid, rows in careers.items():
        d = last.get(uid, {}).get("Pdob")
        el = d[1].find('date[@id="new_value"]') if d else None
        if el is None:
            no_dob += 1
            continue
        dob = (int(el.get("day")), int(el.get("month")), int(el.get("year")))
        for r in rows:
            if r.get("year") and r.get("ytht") and not r.get("apps") and not r.get("gols") \
               and age_on_1_july(dob, int(r["year"])) > CUTOFF:
                out.add((uid, int(r["year"])))
    return out, no_dob


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--report", metavar="FILE.md")
    a = ap.parse_args()
    rng = random.Random(20260916)

    want, no_dob = wanted(a.input)
    print("seasons the rule unticks: %d (careers with no date of birth, rule skipped: %d)"
          % (len(want), no_dob))

    found = {}
    for _, el in ET.iterparse(a.input, events=("end",)):
        if el.tag != "record" or el.get("id") is not None:
            continue
        p = el.find('unsigned[@id="property"]')
        u = el.find('large[@id="db_unique_id"]')
        if p is None or u is None or p.get("value") != PLHS:
            el.clear(); continue
        nv = el.find('record[@id="new_value"]')
        cid = nv.find('unsigned[@id="id"]') if nv is not None else None
        v = nv.find('boolean[@id="value"]') if nv is not None else None
        olvl = nv.find('record[@id="olvl"]') if nv is not None else None
        if cid is not None and cid.get("value") == YTHT and v is not None \
           and v.get("value") == "true" and olvl is not None:
            y = olvl.find('integer[@id="year"]')
            if y is not None and (u.get("value"), int(y.get("value"))) in want:
                found[(u.get("value"), int(y.get("value")))] = copy.deepcopy(el)  # last wins
        el.clear()

    ops, lines = [], []
    for (uid, year) in sorted(want):
        src = found.get((uid, year))
        if src is None:
            lines.append((uid, year, "NO TICK OP FOUND - left alone"))
            continue
        rec = copy.deepcopy(src)
        nv = rec.find('record[@id="new_value"]')
        nv.find('boolean[@id="value"]').set("value", "false")
        o = nv.find('record[@id="olvl"]').find('boolean[@id="ytht"]')
        if o is not None:
            o.set("value", "true")          # the row carries the tick now
        for tag, attr in (("integer", "version"), ("integer", "db_random_id")):
            e = rec.find('%s[@id="%s"]' % (tag, attr))
            if e is not None:
                e.set("value", BUILD if attr == "version" else str(rng.randint(1, 2 ** 31 - 1)))
        ops.append(rec)
        lines.append((uid, year, "unticked"))

    text = open(a.input, encoding="utf-8").read()
    open_tag = '<list id="db_changes">'
    head = text[:text.index(open_tag) + len(open_tag)]
    tail = text[text.rindex("</list>"):]
    body = "".join("\n\t\t" + ET.tostring(r, encoding="unicode") for r in ops)
    open(a.output, "w", encoding="utf-8").write(head + body + "\n\t" + tail)
    print("untick changes written: %d -> %s" % (len(ops), a.output))

    if a.report:
        md = ["# Youth ticks removed\n",
              "\nA season with no appearances and no goals, after the player turned %d, is not a "
              "youth season. Source: `%s`.\n" % (CUTOFF, os.path.basename(a.input)),
              "\n| Record | Season | Result |", "|---|---|---|"]
        for r in sorted(lines):
            md.append("| %s | %d | %s |" % r)
        open(a.report, "w", encoding="utf-8").write("\n".join(md) + "\n")
        print("report ->", a.report)


if __name__ == "__main__":
    main()
