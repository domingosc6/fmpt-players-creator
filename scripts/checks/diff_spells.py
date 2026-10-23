"""Spell-level diff of two converted builds.

`diff_careers.py` reads `Plhs` and would pass a build that wrecked every club
spell. This reads `Pnph`: for each person it replays the spells grid in both
builds and compares club, join and leave.

A date is UNUSABLE when the editor shows it as 0 - absent, a sentinel year, or
year-only (`0/0/2024`) - which is the whole point of the calendar fill. So a
spell going from unusable to a real date is a GAIN, the reverse is a REGRESSION,
and a real date changing to a different real date is reported for an eye.
"""
import sys, os, glob, collections, xml.etree.ElementTree as ET
sys.path.insert(0, "/Users/domingos.costa/Documents/FMPT-Legends/scripts")
import convert_edition as ce, fm_names, extract_squad as ex

nm = fm_names.Names(offline=True)
NEW, X = sys.argv[1], "FM 26 XML Files/converted_xmls"


def spells(ops):
    out = []
    for row in ce.replay_spells_ops(ops):
        def d(el):
            if el is None:
                return None
            y = el.get("year")
            if not y or not y.isdigit() or int(y) in ce.SENTINELS:
                return None
            if el.get("day") in (None, "0") or el.get("month") in (None, "0"):
                return None            # year-only: the editor shows 0
            return (el.get("day"), el.get("month"), y)
        out.append((row["team"][1] if row["team"] else None, d(row["join"]), d(row["left"])))
    return out


def index(p):
    return ex.people_index(ce, nm, ET.parse(p).getroot())


gain = lost = moved = 0
per_file = collections.Counter()
examples = []
for np_ in sorted(glob.glob(f"{NEW}/*.xml")):
    c = os.path.basename(np_)[:-4]
    base = (f"{X}/FMPT Legends - Portugal FM18 - target2025 - clean.xml" if c == "Portugal FM18"
            else f"{X}/FMPT Legends - {c} - target2025 - clean.xml")
    ixa, ixb = index(base), index(np_)
    ka = {frozenset(ixa["members"][q]): q for q in ixa["members"]}
    kb = {frozenset(ixb["members"][q]): q for q in ixb["members"]}
    for k in set(ka) & set(kb):
        sa = spells(ixa["groups"].get((ka[k], "Pnph"), []))
        sb = spells(ixb["groups"].get((kb[k], "Pnph"), []))
        if sa == sb:
            continue
        n = ixb["names"].get(kb[k]) or nm.person(sorted(k)[0]) or "(existing DB record)"
        if len(sa) != len(sb):
            examples.append((c, n, "ROW COUNT %d -> %d" % (len(sa), len(sb))))
            per_file[c] += 1
            continue
        for (cla, ja, la), (clb, jb, lb) in zip(sa, sb):
            for old, new_ in ((ja, jb), (la, lb)):
                if old == new_:
                    continue
                if old is None and new_ is not None:
                    gain += 1
                elif old is not None and new_ is None:
                    lost += 1
                    examples.append((c, n, "LOST a date: %s -> none" % (old,)))
                else:
                    moved += 1
                    examples.append((c, n, "date moved %s -> %s" % (old, new_)))
            if cla != clb:
                examples.append((c, n, "CLUB changed %s -> %s" % (cla, clb)))
        per_file[c] += 1
print("spell dates gained (were shown as 0): %d" % gain)
print("spell dates LOST (regression):        %d" % lost)
print("real dates moved to another date:     %d" % moved)
print("\npeople with any spell change, by file:")
for c, n in per_file.most_common():
    print("   %-24s %d" % (c, n))
if examples:
    print("\nevery non-gain change (%d):" % len(examples))
    for c, n, why in examples:
        print("   %-14s %-34s %s" % (c, n, why))
