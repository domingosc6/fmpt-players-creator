"""Absolute quality check on club-spell grids, not a diff.

`diff_spells.py` compares two builds row by row, which is useless once the
spells are REBUILT from the career - every row legitimately changes. This asks
the question that actually matters: how many spells does the editor draw as `0`,
and do the spells name the same clubs the career does.

A date is UNUSABLE when the editor shows it as 0: absent, a sentinel year, or
year-only (`0/0/2024`).
"""
import sys, os, glob, collections, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import convert_edition as ce, clean_import as ci, probe_editor_replay as pr, fm_names, extract_squad as ex

nm = fm_names.Names(offline=True)


def usable(el):
    if el is None:
        return False
    y = el.get("year")
    if not y or not y.isdigit() or int(y) in ce.SENTINELS:
        return False
    return el.get("day") not in (None, "0") and el.get("month") not in (None, "0")


def scan(path):
    ix = ex.people_index(ce, nm, ET.parse(path).getroot())
    bad_dates = people_bad = spells = 0
    club_mismatch = []
    for p in ix["members"]:
        rows = ce.replay_spells_ops(ix["groups"].get((p, "Pnph"), []))
        if not rows:
            continue
        hit = False
        for r in rows:
            spells += 1
            if not usable(r["join"]):
                bad_dates += 1
                hit = True
            # a leave the author left blank is the current club and is fine
            if r["left"] is not None and not usable(r["left"]):
                bad_dates += 1
                hit = True
        people_bad += hit
        career, _ = pr.replay(ix["groups"].get((p, "Plhs"), []))
        if career:
            cc = {ci.club_key(r) for r in career if r["club"] is not None}
            sc = {r["team"][1] for r in rows if r["team"]}
            if sc - cc:
                n = ix["names"].get(p) or nm.person(ix["members"][p][0]) or ix["members"][p][0]
                club_mismatch.append((n, sorted(sc - cc)))
    return spells, bad_dates, people_bad, club_mismatch


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NEW, X = sys.argv[1], os.path.join(ROOT, "FM 26 XML Files/converted_xmls")
tot = collections.Counter()
for np_ in sorted(glob.glob(f"{NEW}/*.xml")):
    c = os.path.basename(np_)[:-4]
    base = (f"{X}/FMPT Legends - Portugal FM18 - target2025 - clean.xml" if c == "Portugal FM18"
            else f"{X}/FMPT Legends - {c} - target2025 - clean.xml")
    sa, ba, pa, ma = scan(base)
    sb, bb, pb, mb = scan(np_)
    tot["spells_before"] += sa; tot["bad_before"] += ba; tot["people_before"] += pa
    tot["spells_after"] += sb; tot["bad_after"] += bb; tot["people_after"] += pb
    tot["mismatch_before"] += len(ma); tot["mismatch_after"] += len(mb)
    if ba != bb or len(ma) != len(mb):
        print(f"{c:22} spells {sa}->{sb}   dates shown as 0: {ba}->{bb}"
              f"   spells naming a club the career does not: {len(ma)}->{len(mb)}")
        for n, extra in mb[:3]:
            print(f"     ! {n}: {extra}")
print("\nTOTAL  spells %d -> %d" % (tot["spells_before"], tot["spells_after"]))
print("       dates the editor draws as 0: %d -> %d   (on %d -> %d people)"
      % (tot["bad_before"], tot["bad_after"], tot["people_before"], tot["people_after"]))
print("       spells naming a club the career does not: %d -> %d"
      % (tot["mismatch_before"], tot["mismatch_after"]))
